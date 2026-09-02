/* 连环 · 浏览器版的 Service Worker。
   · 自己带的静态文件：装的时候整套缓存，之后先缓存后网络（离线也能开）
   · Pyodide 那些大文件（CDN）：第一次用到就存下来，之后离线也有
   · 其余同源请求（浏览器自己发的 <img src="/uploads/…"> 那类）：转回页面，让页面里的后端答（bridge）
   · 绝不缓存后端的回答 —— 缓存过的对话和记忆是最坏的一种错误 */
const VER = "__VER__";
const STATIC = __STATIC__;
const CACHE = "lh-local-" + VER;
const CDN = "lh-local-cdn";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE)
    .then((c) => Promise.allSettled(STATIC.map((u) => c.add(new URL(u, self.registration.scope).href))))
    .then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== CACHE && k !== CDN).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function viaPage(req) {
  const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  const scope = self.registration.scope;
  const page = clients.find((c) => c.url.indexOf(scope) === 0) || clients[0];
  if (!page) return new Response("连环还没起来（没有打开的页面）", { status: 503, headers: { "content-type": "text/plain; charset=utf-8" } });
  const body = (req.method === "GET" || req.method === "HEAD") ? null : await req.arrayBuffer();
  const headers = []; req.headers.forEach((v, k) => headers.push([k, v]));
  const ch = new MessageChannel();
  const reply = new Promise((res) => {
    ch.port1.onmessage = (e) => res(e.data);
    setTimeout(() => res({ status: 504, headers: [["content-type", "text/plain; charset=utf-8"]], body: null }), 20000);
  });
  page.postMessage({ lh: "asgi", method: req.method, url: req.url, headers, body }, body ? [ch.port2, body] : [ch.port2]);
  const r = await reply;
  return new Response(r.body, { status: r.status, headers: r.headers });
}

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  const scope = new URL(self.registration.scope);
  if (url.origin === location.origin && url.pathname.indexOf(scope.pathname) === 0) {
    const rel = url.pathname.slice(scope.pathname.length);
    if (rel === "" || rel === "index.html" || STATIC.includes(rel)) {
      e.respondWith(caches.match(e.request, { ignoreSearch: true }).then((hit) => hit || fetch(e.request)));
      return;
    }
    e.respondWith(viaPage(e.request));
    return;
  }
  if (url.hostname === "cdn.jsdelivr.net" && url.pathname.indexOf("/pyodide/") === 0) {
    e.respondWith(caches.open(CDN).then(async (c) => {
      const hit = await c.match(e.request);
      if (hit) return hit;
      const r = await fetch(e.request);
      if (r.ok) c.put(e.request, r.clone());
      return r;
    }));
  }
});
