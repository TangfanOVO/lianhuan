/* 连环 · 浏览器版起点。
   ════════════════════════════════════════════════════════════════
   这一份站里没有服务器：同一份 Python 后端（core/ optional/ seed/）解压到页面里的 Pyodide 跑，
   数据落在 IndexedDB（/lh），也就是「家在这台设备的浏览器里」。

   它做的事，按顺序：
     1. 立刻把 window.fetch 换成一个会排队的代理 —— 页面脚本一开就会 fetch('/api/…')，那时后端还没起来，先排着
     2. 盖一层「起来中」，去 CDN 拿 Pyodide、装 sqlite3/httpx，挂 IndexedDB 持久盘
     3. 拿 backend.zip 解到 /app，装 fastapi 那四个纯 Python 轮子（同目录 wheels/，Service Worker 会缓存）
     4. core.browser.boot() → lifespan() → 之后每条同源请求都直接喂给 ASGI，流式回复接成 ReadableStream
     5. 每次请求后延时把 /lh 同步回 IndexedDB；页面切后台、关掉前也同步一次

   ★ 不是这份站自己带的静态文件（index/manifest/sw/icons/wheels/backend.zip…）的同源请求，一律算后端的。
   ★ /api/… 这种站根绝对路径由这个代理接（它不经过 Service Worker）；<img src="/uploads/…"> 那类浏览器自己发的，
     由 sw.js 转回页面来问（bridge）。 */
(function () {
  "use strict";
  /* ★ 自己家里的 Pyodide，不连任何 CDN —— 这个源下面存着 key 和整份家，
     在这儿执行别人服务器发来的脚本，等于把那道边界让出去。构建时整套拷进 pyodide/。 */
  var PYODIDE = new URL("pyodide/", new URL(".", location.href)).href;
  var BASE = new URL(".", location.href);
  /* 这一份站自己带的东西。★ 下面那行是占位，构建时按 dist/ 的真实内容填 ——
     **手写这张名单栽过一次**：自托管 Pyodide 之后忘了加 `pyodide/`，
     于是 wasm 被当成后端请求排进队里，而后端正等着这个 wasm 起来 —— 页面永远停在「起来中…」。 */
  var STATIC_PREFIXES = __STATIC__;
  function isStatic(rel) {
    for (var i = 0; i < STATIC_PREFIXES.length; i++) {
      var p = STATIC_PREFIXES[i];
      if (p.slice(-1) === "/" ? rel.indexOf(p) === 0 : rel === p) return true;
    }
    return false;
  }

  var realFetch = window.fetch.bind(window);
  var queue = [];
  var asgi = null;          // (Request, {path, query}) → Promise<Response>
  var py = null;

  function route(u) {
    var url; try { url = new URL(u, location.href); } catch (e) { return null; }
    if (url.origin !== location.origin) return null;
    var p = url.pathname;
    if (p.indexOf(BASE.pathname) === 0) {
      var rel = p.slice(BASE.pathname.length);
      if (rel === "" || isStatic(rel)) return null;
      p = "/" + rel;
    }
    return { path: p, query: url.search.replace(/^\?/, "") };
  }

  window.fetch = function (input, init) {
    var u = typeof input === "string" ? input : (input && input.url) || String(input);
    var t = route(u);
    if (!t) return realFetch(input, init);
    var run = function () { return asgi(new Request(input, init), t); };
    if (asgi) return run();
    return new Promise(function (res, rej) { queue.push(function () { run().then(res, rej); }); });
  };

  /* ── 盖层 ── */
  var cover = document.createElement("div");
  cover.id = "lh-boot";
  cover.setAttribute("style", "position:fixed;inset:0;z-index:2147483000;background:#f7f2ea;color:#6b5f57;" +
    "font:15px/1.7 -apple-system,system-ui,sans-serif;display:flex;align-items:center;justify-content:center;text-align:center;padding:24px");
  cover.innerHTML = "<div><div style='font-size:22px;color:#a8412f;margin-bottom:8px'>连环</div>" +
    "<div id='lh-boot-msg'>起来中…</div><div id='lh-boot-sub' style='font-size:12px;opacity:.7;margin-top:6px'>第一次要多等一会儿（十几秒），之后就快了</div></div>";
  /* ★ 盖层是等 DOMContentLoaded 才挂上的，而这段脚本在 head 里就开跑了。
     所以 say() 不能只往文档里找元素 —— 找不到就把话丢了，**出错信息也一起丢**（栽过）。
     改成直接对着 cover 这棵树写，挂没挂上都不影响。 */
  function say(m, sub) {
    var el = cover.querySelector("#lh-boot-msg"); if (el) el.textContent = m;
    if (sub !== undefined) { var s = cover.querySelector("#lh-boot-sub"); if (s) s.textContent = sub; }
  }
  function mount() { if (document.body && !cover.parentNode) document.body.appendChild(cover); }
  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);

  function loadScript(src) {
    return new Promise(function (res, rej) {
      var s = document.createElement("script"); s.src = src; s.onload = res; s.onerror = function () { rej(new Error("拿不到 " + src)); };
      document.head.appendChild(s);
    });
  }
  function syncfs(populate) {
    return new Promise(function (res, rej) { py.FS.syncfs(populate, function (e) { e ? rej(e) : res(); }); });
  }
  var syncTimer = null, syncing = false, dirty = false;
  function touch() {
    dirty = true;
    clearTimeout(syncTimer);
    syncTimer = setTimeout(flush, 700);
  }
  function flush() {
    if (!py || syncing || !dirty) return;
    syncing = true; dirty = false;
    syncfs(false).catch(function () {}).then(function () { syncing = false; if (dirty) touch(); });
  }
  document.addEventListener("visibilitychange", function () { if (document.hidden) { clearTimeout(syncTimer); flush(); } });
  window.addEventListener("pagehide", function () { clearTimeout(syncTimer); flush(); });

  /* ── 浏览器自己发的那些（<img src="/uploads/…">）：拿到后换成 blob 地址 ── */
  function swapSrc(img) {
    var src = img.getAttribute("src");
    if (!src || img.dataset.lhSwapped || !/^\/(uploads|files)\//.test(src)) return;
    img.dataset.lhSwapped = "1";
    window.fetch(src).then(function (r) { return r.ok ? r.blob() : null; })
      .then(function (b) { if (b) img.src = URL.createObjectURL(b); }).catch(function () {});
  }
  new MutationObserver(function (ms) {
    ms.forEach(function (m) {
      if (m.type === "attributes") { if (m.target.tagName === "IMG") swapSrc(m.target); return; }
      m.addedNodes.forEach(function (n) {
        if (n.nodeType !== 1) return;
        if (n.tagName === "IMG") swapSrc(n);
        else if (n.querySelectorAll) n.querySelectorAll("img").forEach(swapSrc);
      });
    });
  }).observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["src"] });

  /* ── Service Worker 转回来问的（bridge） ── */
  if (navigator.serviceWorker) {
    navigator.serviceWorker.addEventListener("message", function (e) {
      var d = e.data; if (!d || d.lh !== "asgi" || !e.ports[0]) return;
      var port = e.ports[0];
      var t = route(d.url);
      if (!t || !asgi) { port.postMessage({ status: 503, headers: [["content-type", "text/plain; charset=utf-8"]], body: null }); return; }
      asgi(new Request(d.url, { method: d.method, headers: d.headers, body: d.body }), t).then(function (resp) {
        return resp.arrayBuffer().then(function (buf) {
          var h = []; resp.headers.forEach(function (v, k) { h.push([k, v]); });
          port.postMessage({ status: resp.status, headers: h, body: buf }, [buf]);
        });
      }).catch(function (err) {
        port.postMessage({ status: 500, headers: [["content-type", "text/plain; charset=utf-8"]], body: new TextEncoder().encode(String(err)).buffer });
      });
    });
  }

  /* ── 主流程 ── */
  (async function () {
    try {
      say("装 Python…");
      await loadScript(PYODIDE + "pyodide.js");
      py = await loadPyodide({ indexURL: PYODIDE });
      say("装数据库和网络…");
      await py.loadPackage(["sqlite3", "httpx", "micropip", "anyio", "sniffio", "typing-extensions", "ssl"]);
      say("接上这台设备的存储…");
      py.FS.mkdir("/lh");
      py.FS.mount(py.FS.filesystems.IDBFS, {}, "/lh");
      await syncfs(true);
      say("解开后端…");
      var zip = await (await realFetch(new URL("backend.zip", BASE).href)).arrayBuffer();
      py.unpackArchive(zip, "zip", { extractDir: "/app" });
      say("装最后几个包…");
      var wheels = JSON.parse(document.getElementById("lh-wheels").textContent).map(function (w) { return new URL("wheels/" + w, BASE).href; });
      py.globals.set("_lh_wheels", py.toPy(wheels));
      await py.runPythonAsync("import micropip\nawait micropip.install(list(_lh_wheels))");
      say("起后端…");
      var info = await py.runPythonAsync("import sys\nsys.path.insert(0, '/app')\nfrom core import browser\nimport json\njson.dumps(browser.boot('/lh/data'))");
      var browser = py.pyimport("core.browser");
      await browser.lifespan();
      var handle = browser.handle;

      asgi = async function (req, t) {
        var body = (req.method === "GET" || req.method === "HEAD") ? null : new Uint8Array(await req.arrayBuffer());
        var headers = []; req.headers.forEach(function (v, k) { headers.push([k, v]); });
        var ctrl, status = 200, hdrs = [], startResolve;
        var started = new Promise(function (r) { startResolve = r; });
        var stream = new ReadableStream({ start: function (c) { ctrl = c; } });
        var closed = false;
        var sink = {
          start: function (st, hjson) { status = st; hdrs = JSON.parse(hjson); startResolve(); },
          chunk: function (u8) { if (!closed) try { ctrl.enqueue(u8 instanceof Uint8Array ? u8 : new Uint8Array(u8)); } catch (e) {} },
          end: function () { if (!closed) { closed = true; try { ctrl.close(); } catch (e) {} } startResolve(); }
        };
        handle(req.method, t.path, t.query, headers, body, sink).catch(function (err) {
          if (!closed) { status = 500; hdrs = [["content-type", "text/plain; charset=utf-8"]]; sink.chunk(new TextEncoder().encode(String(err))); sink.end(); }
        }).finally(touch);
        await started;
        return new Response(stream, { status: status, headers: hdrs });
      };
      window.__lianhuanLocal = { pyodide: py, info: JSON.parse(info), flush: flush };
      queue.splice(0).forEach(function (f) { f(); });
      cover.remove();
    } catch (err) {
      console.error(err);
      say("没起来：" + (err && err.message ? err.message : err),
          "刷新再试一次。要是一直这样，把这句话截图发给作者。");
      var b = document.createElement("button"); b.textContent = "重试";
      b.setAttribute("style", "margin-top:14px;padding:8px 18px;border:1px solid #a8412f;background:#fff;color:#a8412f;border-radius:8px;font:inherit");
      b.onclick = function () { location.reload(); };
      cover.firstChild.appendChild(b);
    }
  })();
})();
