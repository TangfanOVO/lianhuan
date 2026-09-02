/* 连环 · 积木预览 —— 外壳。
   ════════════════════════════════════════════════════════════════
   零依赖，一个 <script> 就是全部。

   ★ 关键决定：**每一块用它自己那份真的 demo，套在 iframe 里跑。**
     不在这一页里照着重画一遍 —— 重画出来的迟早跟真的漂开，
     而且「你看到的不是你拿走的」是这类预览站最容易犯的谎。
     换肤靠往 iframe 的 document 上盖 data-theme 和 --accent（同源，够得着），
     所以积木本身一行都不用改。

   ★ 0902 重来：这一页原来有两块是**手写的仿制品**（聊天＝六个泡泡、配色＝两张示意卡），
     别的块也各自重画了一个小 demo —— 那就是重复造轮子：源码里已经写好的东西，
     在预览层又照着原创了一遍，两份迟早漂开。
     现在**每一块都是原项目那份前端整段搬过来的**，只把私人数据换成编的。
     这一页自己不画任何一块的样子，只负责：分区导航 → 一台假手机 → 取件说明。 */
(function () {
  "use strict";

  /* ── 公开仓库地址 ─────────────────────────────────────────────
     ★ 还没定。定了填这一行 —— 只有这一处。
     空着的时候「看源码」那个入口会照实说还没定，**不给一个假链接**，
     也绝不指向 localhost 或本机路径。 */
  var REPO = "https://github.com/TangfanOVO/lianhuan";

  var BLOCKS = "assets/blocks/";

  /* 每块：id / 名字 / 眉毛 / 分组 / 真 demo 在哪 / 取件命令 / 能引什么 / 一句实话
     ★ 0902 重来：这一页原来每块都是「照着原项目的样子在预览站里重画一个小 demo」——
       书目是编的、机器人画成了一本书、聊天只有几个泡泡、打电话只有一根线。
       现在每一块都是**原项目那份前端整段搬过来**的，只把私人数据换成编的。 */
  var GROUPS = [
    ["底子", "look"],
    ["手感", "feel"],
    ["整页", "page"],
  ];

  var PANELS = [
    { id: "home", name: "主页", eyebrow: "Home", group: "look", kind: "real", demo: "home/demo.html",
      pack: "frontend/home", imports: ["blocks/home/home.css", "blocks/home/home.js"],
      truth: "整屏主页，六种排法：方块／垂丝／横渡／灯串／纸夹／散摞 —— 上面那排按钮切。" +
             "方块底下那颗「排一排主页」能按住拖着换板块顺序，刷新还在。" +
             "换配色和明暗时六种排法都跟着变，顶栏、便签、缝线、卡片、底栏一个不落 —— " +
             "配色好不好使，看的就是这一屏。另外五种的物理直接引「丝线叠卡」那一块，没有复制第二份。" },

    { id: "ambience", name: "漂浮物", eyebrow: "Ambience", group: "look", kind: "real", demo: "ambience/demo.html",
      pack: "frontend/ambience", imports: ["blocks/ambience/ambience.js", "blocks/ambience/ambience.css"],
      truth: "页面底噪那一层。十种、能多选、能调密和快。纯前端、不发任何请求。" },

    { id: "paper", name: "纸的材质", eyebrow: "Paper", group: "look", kind: "real", demo: "paper/demo.html",
      pack: "frontend/paper", imports: ["blocks/paper/paper.css"],
      truth: "撕口、折角、铁夹。纯 CSS，滤镜定义自带。" },

    { id: "physics", name: "丝线叠卡", eyebrow: "Physics", group: "feel", kind: "real", demo: "physics/demo.html",
      pack: "frontend/physics", imports: ["blocks/physics/silk-rope.js"],
      more: [["纸夹", "physics/demo-paper.html"], ["散摞", "physics/demo-stack.html"]],
      truth: "卡片挂在会飘的丝线上。三种排法，都是原项目主页真在用的那三种。卡是两段式点击。" },

    { id: "shelf", name: "书房", eyebrow: "Study", group: "feel", kind: "real", demo: "shelf/demo.html",
      pack: "frontend/shelf", imports: ["blocks/shelf/shelf.js", "blocks/shelf/shelf.css"],
      truth: "原项目那一架，四组：「一起做的」（梗典横躺在右端）、「我一个人」、「工具」（里头站着" +
             "机器人，那是个摆件不是书，戳一下会歪一下）、「捡到的」。书名换成了编的，架子的排法和尺寸是原样。" },

    { id: "glyphcloud", name: "记忆星图", eyebrow: "Memory", group: "feel", kind: "real", demo: "glyphcloud/demo.html",
      pack: "frontend/glyphcloud", imports: ["blocks/glyphcloud/glyph-cloud.js", "blocks/glyphcloud/glyph-ui.js"],
      truth: "一个字符 ＝ 一条记忆。点画布本身就换形状（三片轮着来）；切到「选记忆」" +
             "就锁住形状、点字看那条记忆和跟它说同一件事的几条。字是重点色的，底是 card2。" +
             "原项目那三片其中两片是模型厂商的标 —— 开源版不预置任何厂商商标，换成了中性的三片。" },

    { id: "robot", name: "机器人面板", eyebrow: "Robot", group: "feel", kind: "real", demo: "robot/demo.html",
      pack: "frontend/robot", imports: ["blocks/robot/robot.js", "blocks/robot/robot.css"],
      truth: "朝向、视场、盲区。只有前端 —— 数字是占位的，这一页不会去问任何设备。" },

    { id: "water", name: "水面待机", eyebrow: "Water", group: "feel", kind: "real-cdn", demo: "water/demo.html",
      pack: "frontend/water", imports: ["blocks/water/maple-water.js"],
      truth: "待机时那一层水面，本项目原创。★ 它运行时要 p5.js（LGPL，块自己定的是「只走 CDN 不打包」）" +
             "—— 所以只有这一块会发一次外部请求，点开才加载。不想要外部请求就别用它。" },

    { id: "chat", name: "聊天页", eyebrow: "Chat", group: "page", kind: "real", demo: "chat/demo.html",
      pack: "frontend/chat", imports: ["blocks/chat/chat.js", "blocks/chat/chat.css"],
      truth: "整页搬的：思考链（点开是能拖的三档抽屉）、工具调用（状态条＋那颗会转的星＋" +
             "「翻了翻记忆 ›」点开看给出/看到）、左下角加号那十五项、发送键那下回弹。" +
             "不连模型、不读任何记忆，对话是编的剧本。" },

    { id: "call", name: "打电话", eyebrow: "Call", group: "page", kind: "real", demo: "call/demo.html",
      pack: "frontend/call", imports: ["blocks/call/call.js", "blocks/call/call.css", "blocks/thread/thread.js"],
      truth: "整页搬的：拨号、通话中两张皮（对话转写 / 瞥一眼）、顶栏状态点和「在想」那颗星、" +
             "那根线、静音挂断贴耳那排键、打字条、贴耳黑屏。" +
             "不申请麦克风、不连任何服务、不伪造接通，下面这通是编的剧本。" },

    { id: "thread", name: "通话那条线", eyebrow: "Thread", group: "page", kind: "real", demo: "thread/demo.html",
      pack: "frontend/thread", imports: ["blocks/thread/thread.js", "blocks/thread/thread.css"],
      truth: "打电话页里那根线，能单独拿走。谁在说，线就往谁那头写 —— 两个人的波形长得不一样" +
             "（一头连着的一道涌，另一头一串小齿），这个区别本身就是「现在轮到谁」。" +
             "AI 那一头在想的时候，线就在那头一笔写出一片叶子，笔走到哪儿＝想了多久。" +
             "不碰麦克风、不发请求：音量喂进来就用，不喂就走合成包络。" },
  ];

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var el = function (tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  };

  /* ── 换肤：盖在根上，也盖进每个 iframe ───────────────────────── */
  var mode = "light", accent = (window.Accent && Accent.PALETTE[0].hex) || "#b5533a";

  function paintFrames() {
    var frames = document.querySelectorAll("iframe.demo");
    for (var i = 0; i < frames.length; i++) {
      var d = null;
      try { d = frames[i].contentDocument; } catch (e) { /* 跨域就算了 */ }
      if (!d || !d.documentElement) continue;
      d.documentElement.setAttribute("data-theme", mode);
      d.documentElement.style.setProperty("--accent", accent);
      if (frames[i].contentWindow && frames[i].contentWindow.Accent) {
        frames[i].contentWindow.Accent.set(accent);       /* 顺带把对比度那层算对 */
      }
    }
  }
  function applySkin() {
    document.documentElement.setAttribute("data-theme", mode);
    if (window.Accent) Accent.set(accent);
    paintFrames();
  }

  function buildSkin() {
    var themes = $("#themes"), modes = $("#modes");
    (window.Accent ? Accent.PALETTE : []).forEach(function (p) {
      var b = el("button", "pill dot");
      b.style.setProperty("--sw", p.hex);
      b.title = p.name;
      b.setAttribute("aria-label", "重点色：" + p.name);
      b.onclick = function () {
        accent = p.hex; applySkin();
        themes.querySelectorAll(".pill").forEach(function (x) { x.classList.toggle("on", x === b); });
      };
      if (p.hex === accent) b.classList.add("on");
      themes.appendChild(b);
    });
    [["light", "纸"], ["dark", "夜"]].forEach(function (m) {
      var b = el("button", "pill", m[1]);
      b.onclick = function () {
        mode = m[0]; applySkin();
        modes.querySelectorAll(".pill").forEach(function (x) { x.classList.toggle("on", x === b); });
      };
      if (m[0] === mode) b.classList.add("on");
      modes.appendChild(b);
    });
  }

  /* ── 「拿走这一块」──────────────────────────────────────────── */
  function takeCard(p) {
    var box = el("aside", "take");
    box.appendChild(el("p", "take-h", "拿走这一块"));

    var cmd = "npm run pack:take -- " + p.pack + " /absolute/new-folder";
    var pre = el("pre", "cmd"); pre.appendChild(el("code", null, cmd));
    box.appendChild(pre);
    box.appendChild(copyBtn(cmd, "复制命令"));

    if (p.imports.length) {
      box.appendChild(el("p", "take-h2", "能直接引"));
      var ul = el("ul", "paths");
      p.imports.forEach(function (i) {
        var li = el("li"); li.appendChild(el("code", null, i)); ul.appendChild(li);
      });
      box.appendChild(ul);
    } else {
      box.appendChild(el("p", "note", "这一块是应用切片，没有「一行 import 就能接通」那种入口 —— 别装作有。"));
    }

    var src = el("p", "src");
    if (REPO) {
      var a = el("a", null, "看源码 ↗");
      a.href = REPO + "/tree/main/blocks";
      a.rel = "noopener"; a.target = "_blank";
      src.appendChild(a);
    } else {
      src.textContent = "公开仓库地址还没定 —— 定了填 apps/showcase/showcase.js 顶上那一行（只有那一处）。";
      src.className = "src none";
    }
    box.appendChild(src);
    return box;
  }

  function copyBtn(text, label) {
    var b = el("button", "copy", label);
    b.onclick = function () {
      var done = function () { b.textContent = "复制好了"; setTimeout(function () { b.textContent = label; }, 1400); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { window.prompt("手动复制：", text); });
      } else { window.prompt("手动复制：", text); }
    };
    return b;
  }

  /* ★ 0902：这儿原来有一段手写的「假聊天骨架」（六个泡泡＋一个输入框）。
     几个泡泡不叫聊天界面 —— 思考链、工具调用的显示、左下角加号展开的那一列，一样都没有，
     也不是照手机画的。
     现在聊天是 blocks/chat/ 里整段搬来的真页面，走跟别块一样的 iframe。
     **这一页不再手写任何一块的仿制品。** */

  /* ── 假手机的缩放 ───────────────────────────────────────────
     屏幕**恒定 393×852**（真机的逻辑分辨率），整机缩放去适应可用空间。
     ★ 缩的是外面那台机器，不是 iframe —— iframe 一缩，它内部的 CSS 视口跟着变，
       demo 的媒体查询和 dvh 就走到别的分支去了，那等于把手机改小了。
     ★ transform 不占布局空间，所以要把缩完的高度写回占位容器，
       不然下面的内容会被这台 852 高的手机压在底下。 */
  var PHONE_W = 393 + 22, PHONE_H = 852 + 22;   /* 含 11px 边框 ×2 */

  function fitPhone(fit, phone) {
    if (!fit || !phone) return;
    if (window.matchMedia && window.matchMedia("(max-width: 860px)").matches) {
      fit.style.height = ""; phone.style.setProperty("--scale", 1);
      return;
    }
    var avail = fit.clientWidth || PHONE_W;
    /* 上下各留一点，别顶满一屏 */
    var room = Math.max(420, (window.innerHeight || 900) - 210);
    var k = Math.min(1, avail / PHONE_W, room / PHONE_H);
    k = Math.max(.42, k);
    phone.style.setProperty("--scale", k.toFixed(4));
    fit.style.height = Math.round(PHONE_H * k) + "px";
  }

  function refitPhones() {
    var fits = document.querySelectorAll(".phone-fit");
    for (var i = 0; i < fits.length; i++) fitPhone(fits[i], fits[i].firstChild);
  }
  var refitTimer = 0;
  window.addEventListener("resize", function () {
    clearTimeout(refitTimer); refitTimer = setTimeout(refitPhones, 120);
  });

  /* ── 一块的完整面板 ─────────────────────────────────────────── */
  function renderPanel(p) {
    var stage = $("#stage");
    stage.innerHTML = "";
    var wrap = el("section", "panel");

    var head = el("header", "panel-head");
    head.appendChild(el("h2", null, p.name));
    /* ★ 标签只在**有事要提醒**的时候才挂。
       每一块都挂一个「真积木」等于什么都没说 —— 那是在替自己解释，不是在给人信息。 */
    if (p.kind !== "real") {
      var tag = el("span", "kind " + p.kind);
      tag.textContent = "会发一次外部请求";
      head.appendChild(tag);
    }
    wrap.appendChild(head);
    wrap.appendChild(el("p", "truth", p.truth));

    var body = el("div", "panel-body");
    var view = el("div", "view");

    {
      /* ★ 别叫 stage —— 外面那个 `var stage = $("#stage")` 是同一个函数作用域，
         var 不是块级的，重名会把它覆盖掉，最后把面板塞进它自己里面
         （HierarchyRequestError，整页空白）。真机上一开就撞见了。 */
      var deck = el("div", "stage-phone");
      var fit = el("div", "phone-fit");
      var phone = el("div", "phone");
      var screen = el("div", "phone-screen");
      var frame = el("iframe", "demo");
      frame.setAttribute("title", p.name + " 的真实 demo");
      frame.setAttribute("loading", "lazy");
      frame.src = BLOCKS + p.demo;
      frame.onload = paintFrames;
      screen.appendChild(frame);
      phone.appendChild(screen);
      phone.appendChild(el("div", "phone-island"));
      phone.appendChild(el("div", "phone-bar"));
      ["key-act", "key-up", "key-down", "key-pwr"].forEach(function (k) {
        phone.appendChild(el("i", k));
      });
      fit.appendChild(phone);
      deck.appendChild(fit);
      view.appendChild(deck);
      fitPhone(fit, phone);
      if (p.more) {
        var row = el("div", "more");
        row.appendChild(el("span", "lab", "同一块的另外几个"));
        [[p.name, p.demo]].concat(p.more).forEach(function (m, i) {
          var b = el("button", "pill" + (i === 0 ? " on" : ""), m[0]);
          b.onclick = function () {
            frame.src = BLOCKS + m[1];
            row.querySelectorAll(".pill").forEach(function (x) { x.classList.toggle("on", x === b); });
          };
          row.appendChild(b);
        });
        view.appendChild(row);
      }
    }

    body.appendChild(view);
    body.appendChild(takeCard(p));
    wrap.appendChild(body);
    stage.appendChild(wrap);
    applySkin();
  }

  /* ── 起 ─────────────────────────────────────────────────────── */
  function boot() {
    buildSkin();
    var tabs = $("#tabs");
    GROUPS.forEach(function (g) {
      var mine = PANELS.filter(function (p) { return p.group === g[1]; });
      if (!mine.length) return;
      var wrap = el("div", "tabgroup");
      wrap.appendChild(el("span", "glab", g[0]));
      var items = el("div", "gitems");
      mine.forEach(function (p) {
        var b = el("button", "tab");
        b.appendChild(el("small", null, p.eyebrow));
        b.appendChild(el("strong", null, p.name));
        b.dataset.id = p.id;
        b.onclick = function () {
          /* 只改 hash —— 上面那个 hashchange 会把画面切过去。
             两处各切一遍的话，迟早有一处忘了改。 */
          if ((location.hash || "").slice(1) === p.id) { renderPanel(p); return; }
          location.hash = p.id;
        };
        items.appendChild(b);
      });
      wrap.appendChild(items);
      tabs.appendChild(wrap);
    });
    function indexOfHash() {
      var want = (location.hash || "").slice(1), i = 0;
      PANELS.forEach(function (p, k) { if (p.id === want) i = k; });
      return i;
    }
    function show(i) {
      var id = PANELS[i].id;
      tabs.querySelectorAll(".tab").forEach(function (x) { x.classList.toggle("on", x.dataset.id === id); });
      renderPanel(PANELS[i]);
    }
    /* ★ 浏览器的前进/后退改的是 hash，不重新加载页面 ——
       只在启动时读一次 hash 的话，按返回键地址变了、页面不变，
       看着就像返回键坏了。（真机验的时候当场撞上。） */
    window.addEventListener("hashchange", function () { show(indexOfHash()); });
    show(indexOfHash());
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  /* ── 顶上那排去处：应用预览（同一站的 app/）· 安卓壳（Releases）· 仓库。
     ★ 链接全从 REPO 拼，不在这儿写第二个地址；REPO 没定就只留应用预览。 */
  (function () {
    var box = document.getElementById("links");
    if (!box) return;
    function go(text, href) {
      var a = el("a", null, text); a.href = href;
      if (href.indexOf("http") === 0) { a.rel = "noopener"; a.target = "_blank"; }
      box.appendChild(a);
    }
    go("打开应用预览 ↗", "app/");
    if (REPO) {
      go("下载安卓壳 APK ↗", REPO + "/releases/tag/apk");
      go("仓库 ↗", REPO);
      go("一键部署 ↗", REPO + "#一键部署");
    }
  })();
})();
