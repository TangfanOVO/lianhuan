/*!
 * home.js —— 主页的**六种排法**切换 ＋「排一排主页」
 *
 *   方块 tiles · 垂丝 drape · 横渡 blinds · 灯串 lantern · 纸夹 paper · 散摞 stack
 *
 * 这一份只干两件事：
 *   ① 换排法 —— 谁显示、.body 上该挂哪几个 class、底纸墙跟谁走、画布什么时候重量一次
 *   ② 排一排 —— 方块那一版的板块顺序，按住拖、松手落位、存本机、下次进来还原
 *
 * ★ **物理一行都不在这儿。** 会飘的那三块在 ../physics/：
 *     silk-rope.js（垂丝/横渡/灯串，三种共用一个舞台，差别只在 mode）
 *     paper-clip.js（纸夹）· stack.js（散摞）
 *   这一份只负责把它们接上宿主，不重写任何一段几何。
 *
 * 接法（demo.html 就是这么接的）：
 *   <script>window.__paperStageHost='[data-home="paper"]';
 *           window.__stackStageHost='[data-home="stack"]';</script>
 *   <script src="../physics/silk-rope.js"></script>
 *   <script src="../physics/paper-clip.js"></script>
 *   <script src="../physics/stack.js"></script>
 *   <script src="home.js"></script>
 *
 * 页面要给的东西（少哪个就少哪种排法，不报错）：
 *   .app（壳，position:relative）· #body（滚动容器）· .app > .top（顶栏）· .tabbar（底栏）
 *   #p-home 里四个排法容器：[data-home="tiles"|"silk"|"paper"|"stack"]
 *   .app 上两层底纸墙：[data-wall-paper] [data-wall-stack]
 *   开关：任意多个 [data-home-style="…"]
 *   排一排：[data-sort] 那颗按钮、#sortpage、#sortlist、[data-close="sortpage"]
 *
 * 对外：window.Home = {layout, setLayout, rebuild, repaint, applyOrder}
 * 事件：切完排法在 document 上派一个 'home:layout'（detail.layout）
 *
 * 逻辑整段搬自应用那半边跑了几个月的原型（proto.html）：
 *   applyHome / syncPad  ← proto.html:12497-12574
 *   排一排的拖拽和落位   ← proto.html:5478-5595
 * 只有两处跟原件不一样，都在下面注释里写清了为什么（灯串的暗色由谁管、fakenote 不算一行）。
 *
 * 零依赖、零网络。MIT（见同目录 LICENSE）。
 */
(function (global) {
  'use strict';

  var doc = global.document;
  if (!doc) return;

  /* 排法名就这六个。存本机的值要是被人改花了，退回方块，别让页面空着。 */
  var LAYOUTS = ['tiles', 'drape', 'blinds', 'lantern', 'paper', 'stack'];
  var KEY_LAYOUT = 'silk.home';    /* 跟原件同名：风力那个键 silk.wind 也是这一族的 */
  var KEY_ORDER = 'home.order';    /* 方块的板块顺序。原件那边带着应用自己的前缀，这儿去掉了 */
  var KEY_HIDE  = 'home.hidden';   /* (0904) 收起来的板块。她的原话：「有人不需要健康什么的，让他们自己关」 */

  function LSget(k, d) {
    try { var v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); }
    catch (e) { return d; }
  }
  function LSset(k, v) {
    try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {}
  }

  var shell    = doc.querySelector('.app');
  var bodyEl   = doc.getElementById('body');
  var homePage = doc.getElementById('p-home');
  var head     = doc.querySelector('.app > .top');
  var nav      = doc.querySelector('.tabbar');

  var boxTiles = doc.querySelector('[data-home="tiles"]');
  var boxSilk  = doc.querySelector('[data-home="silk"]');
  var boxPaper = doc.querySelector('[data-home="paper"]');
  var boxStack = doc.querySelector('[data-home="stack"]');

  var home = LSget(KEY_LAYOUT, 'tiles');
  if (LAYOUTS.indexOf(home) < 0) home = 'tiles';

  function isPaper() { return home === 'paper'; }
  function isStack() { return home === 'stack'; }
  /* 纸夹和散摞都不吃绳子物理 —— 它们的位置是钉死的几何，不是挂在线上的 */
  function silkOn()  { return home !== 'tiles' && home !== 'paper' && home !== 'stack'; }
  function onHome()  { return !!(homePage && homePage.classList.contains('on')); }

  /* ── .body 上那几个 class ── 原件 proto.html:12502-12516 ────────────────
     ★ nopad 是给主页画布用的（去掉左右 16px 好让 440 的画布铺满、并且不翻页），
       可它加在 .body 上 —— 而 .body 是所有页共用的。真机上逮到过：
       切到聊天页它还赖着，气泡贴到最左边、连上下滚都被 overflow 锁死了。
       所以开关要同时看两件事：**在不在主页** ＋ **是不是那两种排法**。
     ★ fullbleed（上下内边距归零）和 homefull（顶栏浮起）必须同开同关：
       只归零不浮顶栏＝画布仍被顶栏顶掉一条；只浮顶栏不归零＝别的页滚动时
       内容会从顶栏后面穿过去。
     ⚠ 换页也要重算，所以宿主的换页函数里也要调一次（对外挂在 Home.syncPad）。 */
  function syncPad() {
    if (!bodyEl) return;
    bodyEl.classList.toggle('nopad', onHome() && (isPaper() || isStack()));
    var full = onHome() && silkOn();
    bodyEl.classList.toggle('fullbleed', full);
    if (shell) shell.classList.toggle('homefull', full);
  }

  /* ── 丝线 ── 三种排法共用一个实例，切排法只是 setMode ───────────────────
     chrome 那四个是**几何的一部分，不是装饰**：
       body   给的是滚动容器 —— rebuild() 拿它的净高当画布高，还靠
              `classList.contains('fullbleed')` 决定要不要把卡片收进安全区。
              不给就退回「顶栏＋底栏＋26」的估算，比一屏多出十几个像素。
       footer 给的是真实底沿 —— 卡片下界 bot = footer.offsetTop - 12 是从它量的。
              这一页的底栏是 absolute 贴在 .app 上的，offsetParent 正好是 .app，
              而铺满时 .body 的顶就是 .app 的顶，两边坐标对得上。
       header 顶栏高（卡片上界 = 它 + 12）；顺带聚焦某根线时把它和底栏淡下去。
       shell  壳高，短屏那条 540 的下限用得上。
     isActive：切走了就停算（省电）。 */
  var silk = null;
  if (global.SilkRope && boxSilk) {
    silk = SilkRope(boxSilk.querySelector('[data-stage]'), {
      chrome: { header: head, footer: nav, shell: shell, body: bodyEl },
      mode: silkOn() ? home : 'drape',
      isActive: function () { return silkOn() && onHome() && !boxSilk.hidden; },
      onOpen: function (el) {
        /* 点第二下才到这儿。走宿主的 openEntry —— 纸夹和散摞那两块也是先找它，
           三种排法进同一个去处，宿主只用接一个函数。 */
        var b = el.querySelector('b');
        var t = el.getAttribute('data-sub') || el.getAttribute('data-open')
                || (b ? b.textContent : '');
        if (typeof global.openEntry === 'function') {
          try { global.openEntry(t); } catch (e) {}
        }
      }
    });
  }

  /* ── 换排法 ── 原件 proto.html:12517-12574 ─────────────────────────────── */
  function applyHome() {
    /* 用 hidden 属性，别用 style.display —— 两个一起使会打架：
       DOM 上写着 hidden、style.display='' 只是把内联样式清掉，hidden 照样赢，
       于是舞台的 clientWidth 是 0，线和卡片全渲染到画外。栽过一次。 */
    if (boxTiles) boxTiles.hidden = (home !== 'tiles');
    if (boxSilk)  boxSilk.hidden  = !silkOn();
    if (boxPaper) {
      boxPaper.hidden = !isPaper();
      /* 显示出来才量得到宽。fit() 量的是画布的父容器（.hstage），k = min(1, W/440)。 */
      if (isPaper() && global.paperFit) setTimeout(global.paperFit, 0);
    }
    if (boxStack) {
      boxStack.hidden = !isStack();
      if (isStack() && global.stackFit) setTimeout(global.stackFit, 0);
    }
    /* 底纸墙：跟着排法走，顶到顶垫到底。别的排法下收起来。 */
    var wS = doc.querySelector('[data-wall-stack]'), wP = doc.querySelector('[data-wall-paper]');
    if (wS) wS.hidden = !isStack();
    if (wP) wP.hidden = !isPaper();

    syncPad();

    [].forEach.call(doc.querySelectorAll('[data-home-style]'), function (b) {
      b.classList.toggle('on', b.getAttribute('data-home-style') === home);
    });

    /* ※ 跟原件不一样的第一处：**灯串强制暗色那一段不在这儿**。
       原件的 applyHome 自己记 themeBefore、自己换 data-theme；这一版的丝线是
       ../physics/silk-rope.js，它的 applyMode() 里已经有一份同样的逻辑
       （进灯串记下原来那套、切暗色，出来还回去）。
       两处各记一份 themeBefore 会打架：先由这儿切成暗色、丝线那边就把「暗色」
       当成了原来那套，等于再也还不回去。所以让丝线一个人管，这儿不碰主题；
       代价是**离开丝线时也得叫一次 setMode**，它才有机会把主题还回去。 */
    if (silk) {
      silk.setMode(silkOn() ? home : 'drape');
    }
    if (!silkOn()) {
      /* 退回不挂线的排法：把丝线借走的东西还回去（聚焦某根线时顶栏底栏是淡的）。 */
      if (head) head.style.opacity = '1';
      if (nav)  nav.style.opacity = '1';
    }

    try {
      doc.dispatchEvent(new CustomEvent('home:layout', { detail: { layout: home } }));
    } catch (e) {}
  }

  doc.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-home-style]');
    if (!b) return;
    var v = b.getAttribute('data-home-style');
    if (LAYOUTS.indexOf(v) < 0) return;
    home = v;
    LSset(KEY_LAYOUT, home);
    applyHome();
  });

  /* ══════════════════ 排一排主页 ══════════════════ 原件 proto.html:5478-5595
     ★ 拖的是**行**，不是单张卡：一个大纸条、一张独占的卡、或者并排两块的 grid 各算一行，
       每行连同它后面那根 thread 连线一起搬。这样版式一点不散，只是先后变了。
     ★ 存本机，不走接口。
     ★ 只动方块这一版；另外五种排法各有各的坐标，不参与。 */
  var sortPage = doc.getElementById('sortpage');
  var list = doc.getElementById('sortlist');

  /* 名字取 data-sub（那才是这一格叫什么）—— 拿 h3 里的内容当名字会出现
     「白墙」「纸上的河」这种，看不出是哪一格。
     data-open 指的是覆盖层的 id，那是给代码看的，得翻成人话。 */
  var PAGE_CN = {
    moodpage: '心情', fishpage: '鱼篓', memepage: '梗库',
    calpage: '日历', tripspage: '出门走走', histpage: '聊天记录',
    starpage: '收藏', searchpage: '搜全部'
  };
  function one(el) {
    var op = el.getAttribute('data-open');
    if (op && PAGE_CN[op]) return PAGE_CN[op];
    return (el.getAttribute('data-sub') || op || '').split(' · ')[0]
        || (el.querySelector('h3') ? el.querySelector('h3').textContent.trim() : '');
  }
  function rowName(el) {
    if (el.id === 'leftnote') return '我给你留的话';
    if (el.id === 'todaynote') return '今天的安排';
    if (el.classList.contains('grid')) {
      var ns = [].slice.call(el.children).map(one).filter(Boolean);
      return ns.slice(0, 2).join(' · ') || '一组';
    }
    if (el.classList.contains('pills')) {
      var ps = [].slice.call(el.querySelectorAll('.pill')).map(one).filter(Boolean);
      return ps.length > 2 ? ps.slice(0, 2).join(' · ') + ' 等 ' + ps.length + ' 个' : ps.join(' · ');
    }
    return one(el) || '一块';
  }
  /* 认行：跳过顶上的大数字和最底下那颗「排一排」按钮，其余每个直接子元素算一行。
     ※ 跟原件不一样的第二处：多滤掉一个 .fakenote —— 页面底下那行
       「这些字都是编的」是开源积木自己加的（原件那一页装的是真数据，用不着这句），
       它不是一个板块，不该出现在清单里、也不该被拖走。 */
  function rows() {
    if (!boxTiles) return [];
    return [].slice.call(boxTiles.children).filter(function (el) {
      if (el.classList.contains('daycount')) return false;
      if (el.hasAttribute('data-sort')) return false;
      if (el.classList.contains('thread')) return false;   /* 线跟着前面那行走 */
      if (el.classList.contains('fakenote')) return false;
      return true;
    });
  }
  function ensureBlk() {
    rows().forEach(function (el, i) {
      if (!el.dataset.blk) el.dataset.blk = el.id || ('blk' + i);
    });
  }
  function saveOrder() {
    if (!list) return;
    var ids = [].slice.call(list.children).map(function (x) { return x.dataset.blk; }).filter(Boolean);
    if (!ids.length) return;
    LSset(KEY_ORDER, ids);
    applyOrder();
  }
  /* (0904) 收起来的那些。★ 用 `hidden` 属性，不用 display:none ——
     垂丝/横渡/灯串那三种排法的绳子是照 DOM 里挂着的卡算的，
     `../physics/silk-rope.js` 认的正是 `hidden`：认得出来才不会在绳上留一个空尖角。 */
  function hiddenSet() {
    var a = LSget(KEY_HIDE, []);
    return Array.isArray(a) ? a : [];
  }
  function applyHide() {
    if (!boxTiles) return;
    ensureBlk();
    var off = hiddenSet();
    rows().forEach(function (el) {
      var gone = off.indexOf(el.dataset.blk) >= 0;
      el.hidden = gone;
      var line = el.nextElementSibling;              /* 它后面那根线跟着一起收 */
      if (line && line.classList.contains('thread')) line.hidden = gone;
    });
    /* 收起来之后卡少了，会飘的那几种要重新量一次几何 */
    if (silk) { try { silk.rebuild(); } catch (e) {} }
    if (global.paperFit) { try { global.paperFit(); } catch (e) {} }
    if (global.stackFit) { try { global.stackFit(); } catch (e) {} }
  }
  function toggleHide(id) {
    var off = hiddenSet();
    var i = off.indexOf(id);
    if (i >= 0) off.splice(i, 1); else off.push(id);
    LSset(KEY_HIDE, off);
    applyHide();
  }

  function applyOrder() {
    if (!boxTiles) return;
    var ids = LSget(KEY_ORDER, null);
    if (!ids || !ids.length) return;
    ensureBlk();
    var byId = {}; rows().forEach(function (el) { byId[el.dataset.blk] = el; });
    var anchor = boxTiles.querySelector('[data-sort]');   /* 一律插在「排一排」按钮之前 */
    if (!anchor) return;
    ids.forEach(function (id) {
      var el = byId[id]; if (!el) return;
      var line = el.nextElementSibling;                   /* 它后面那根线，跟着一起搬 */
      boxTiles.insertBefore(el, anchor);
      if (line && line.classList.contains('thread')) boxTiles.insertBefore(line, anchor);
    });
  }
  /* 打开「排一排」时，照主页此刻的真实样子现生成清单 —— 以后加了新格子它自己会出现，
     不用再手写死一份。 */
  function buildSortList() {
    if (!list) return;
    ensureBlk();
    var off = hiddenSet();
    list.innerHTML = rows().map(function (el) {
      var id = el.dataset.blk, gone = off.indexOf(id) >= 0;
      /* ★ 眼睛这颗要 type="button"：<button> 不写 type 默认是 submit，
         塞在表单里会把整页提交掉（这坑咬过人）。 */
      return '<div class="sortitem' + (gone ? ' off' : '') + '" data-blk="' + id + '">'
        + '<div class="ic"><svg class="i" viewBox="0 0 24 24">'
        + '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/></svg></div>'
        + '<span>' + rowName(el).replace(/[&<>]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }) + '</span>'
        + '<button class="eye" type="button" data-hide="' + id + '" '
        + 'aria-pressed="' + (gone ? 'true' : 'false') + '" '
        + 'aria-label="' + (gone ? '放回主页' : '从主页收起') + '">'
        + (gone
            ? '<svg class="i" viewBox="0 0 24 24"><path d="M3 3l18 18"/>'
              + '<path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"/>'
              + '<path d="M9.4 5.2A9 9 0 0 1 12 5c4 0 7.3 2.3 9 7a15 15 0 0 1-2.2 3.3"/>'
              + '<path d="M6.6 6.6A15 15 0 0 0 3 12c1.7 4.7 5 7 9 7a9 9 0 0 0 3.4-.6"/></svg>'
            : '<svg class="i" viewBox="0 0 24 24"><path d="M3 12c1.7-4.7 5-7 9-7s7.3 2.3 9 7c-1.7 4.7-5 7-9 7s-7.3-2.3-9-7z"/>'
              + '<path d="M12 9a3 3 0 1 0 0 6a3 3 0 0 0 0-6"/></svg>')
        + '</button>'
        + '<span class="grip"><i></i><i></i><i></i></span></div>';
    }).join('');
  }

  /* (0904) 眼睛：收起 / 放回。她的原话：「有人不需要健康什么的，让他们自己关」。
     ★ 只藏不删 —— 随时点回来，数据一个字没动。 */
  if (list) {
    list.addEventListener('click', function (e) {
      var b = e.target.closest('[data-hide]');
      if (!b) return;
      e.preventDefault(); e.stopPropagation();
      toggleHide(b.getAttribute('data-hide'));
      buildSortList();                 /* 重画清单，眼睛跟着变 */
    });
  }

  /* 按住拖 ── 原件 proto.html:5479-5509，一行没改。
     松手就存，不用再点「保存」。 */
  if (list) {
    var dragEl = null, startY = 0, baseY = 0;
    list.addEventListener('pointerdown', function (e) {
      if (e.target.closest('[data-hide]')) return;   /* (0904) 点的是眼睛，不是要拖 */
      var it = e.target.closest('.sortitem'); if (!it) return;
      dragEl = it; startY = e.clientY; baseY = 0;
      it.classList.add('drag'); it.setPointerCapture(e.pointerId);
    });
    list.addEventListener('pointermove', function (e) {
      if (!dragEl) return;
      baseY = e.clientY - startY;
      dragEl.style.transform = 'translateY(' + baseY + 'px) scale(1.025)';
      var sibs = Array.prototype.slice.call(list.children);
      var me = sibs.indexOf(dragEl);
      var over = sibs.filter(function (s) {
        if (s === dragEl) return false;
        var r = s.getBoundingClientRect();
        return e.clientY > r.top && e.clientY < r.bottom;
      })[0];
      if (over) {
        var oi = sibs.indexOf(over);
        dragEl.style.transform = ''; dragEl.style.transition = 'none';
        list.insertBefore(dragEl, oi > me ? over.nextSibling : over);
        startY = e.clientY;
        requestAnimationFrame(function () { if (dragEl) dragEl.style.transition = ''; });
      }
    });
    var endDrag = function () {
      if (!dragEl) return;
      dragEl.style.transform = ''; dragEl.classList.remove('drag'); dragEl = null;
      saveOrder();
    };
    list.addEventListener('pointerup', endDrag);
    list.addEventListener('pointercancel', endDrag);
  }

  /* 进出「排一排」那一页。原件那边走的是全站通用的二级页开关，这儿只有这一页。 */
  doc.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    if (e.target.closest('[data-sort]')) {
      buildSortList();
      if (sortPage) sortPage.classList.add('on');
      return;
    }
    if (e.target.closest('[data-close="sortpage"]')) {
      if (sortPage) sortPage.classList.remove('on');
    }
  });

  applyOrder();      /* 开页面就按上次排的来 */
  applyHide();       /* (0904) 上次收起来的，继续收着 */
  applyHome();       /* 开页面就是上次那种排法 */

  global.Home = {
    get layout() { return home; },
    setLayout: function (m) {
      if (LAYOUTS.indexOf(m) < 0) return;
      home = m; LSset(KEY_LAYOUT, home); applyHome();
    },
    syncPad: syncPad,
    applyOrder: applyOrder,
    applyHide: applyHide,
    /* 壳的尺寸变了（换页、开关条换行、旋屏）叫一次：三种画布都重新量。 */
    rebuild: function () {
      if (silk) silk.rebuild();
      if (global.paperFit) global.paperFit();
      if (global.stackFit) global.stackFit();
    },
    /* 换了重点色叫一次 —— 线的颜色是建线那会儿钉在 path 上的，不重刷不跟着走。 */
    repaint: function () { if (silk) silk.repaint(); }
  };
})(typeof window !== 'undefined' ? window : this);
