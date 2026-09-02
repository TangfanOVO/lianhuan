/*!
 * parts.js —— 零件的开关逻辑。**只做开和关**，一共不到 100 行。
 *
 * 管三样：滑上来的二级页、抽屉、遮罩。
 * 一次挂上，之后靠 data 属性驱动，不用为每个页面写 JS：
 *
 *   <button data-open="settings">设置</button>     点它 → 打开 #settings
 *   <div class="sub" id="settings"> … </div>
 *   <button data-close>返回</button>               点它 → 关掉最上面那层
 *
 *   <button data-drawer>菜单</button>              点它 → 开抽屉
 *   <div class="drawer" id="drawer"> … </div>
 *   <div class="scrim" id="scrim"></div>           点遮罩 → 关掉最上面那层
 *
 * ★ 二级页是**一摞**，不是一个。层层往上叠，返回一次退一层 ——
 *   不这么做的话，从二级页里再点进三级页，返回会一次退到底。
 *
 * sheet 的三档吸附拖动在下面的 Parts.sheet() 里，demo.html 能试。
 */
(function (global) {
  'use strict';

  function Parts(root, opts) {
    root = root || document;
    opts = opts || {};
    var scrim = root.querySelector('.scrim');
    var stack = [];                      /* 开着的那一摞，后进先出 */

    /* ★ 遮罩只给**盖不满屏**的东西（抽屉、sheet）。
       全屏的二级页（.sub）自己就盖住了一切，再压一层遮罩 = 整页发灰。
       这个真栽过：记忆页做出来第一眼是灰的，还以为是配色写错了。 */
    function needsScrim(el) { return el && !el.classList.contains('sub'); }

    function paintScrim() {
      if (!scrim) return;
      var on = stack.some(needsScrim);
      scrim.style.opacity = on ? '1' : '0';
      scrim.style.pointerEvents = on ? 'auto' : 'none';
    }

    function open(el) {
      if (!el || stack.indexOf(el) >= 0) return;
      el.classList.add('on');
      stack.push(el);
      paintScrim();
      if (opts.onOpen) opts.onOpen(el);
    }

    /* 关掉最上面那一层。★ 只关一层 —— 从三级页返回该回到二级页，不是回到主页。 */
    function close() {
      var el = stack.pop();
      if (!el) return;
      el.classList.remove('on');
      paintScrim();
      if (opts.onClose) opts.onClose(el);
    }

    function closeAll() { while (stack.length) close(); }

    root.addEventListener('click', function (e) {
      var t = e.target;
      if (!t.closest) return;

      var o = t.closest('[data-open]');
      if (o) { e.preventDefault(); return open(root.querySelector('#' + o.getAttribute('data-open'))); }

      if (t.closest('[data-close]')) { e.preventDefault(); return close(); }

      var d = t.closest('[data-drawer]');
      if (d) { e.preventDefault(); return open(root.querySelector(d.getAttribute('data-drawer') || '.drawer')); }

      /* 点遮罩本身＝关一层。★ 用 === 不用 closest：
         点在遮罩「上面」的面板里也会冒泡到这儿，closest 会误判成点了遮罩。 */
      if (scrim && t === scrim) return close();
    });

    /* 手机上没有 Esc，但外接键盘和桌面浏览器有。给了不亏。 */
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && stack.length) { e.preventDefault(); close(); }
    });

    return { open: open, close: close, closeAll: closeAll, depth: function () { return stack.length; } };
  }


  /* ── 可拖的 bottom sheet：跟手，三档吸附 ──
     档位是 translateY 的百分比：0=拉满、40=一半、72=只露个头、100=关掉。打开落在 40。
     只有头部可拖，正文照常滚，两者不打架。
     ★ 这段是从应用的思考链面板整段平移的（写死的 id 换成传进来的元素），别照 README 重做。

       var s = Parts.sheet({ sheet: el, head: el.querySelector('.sheethead'), scrim: scrimEl });
       s.open(true);  s.open(false);  s.set(72, true);  s.pct()
  */
  function sheet(o) {
    var el = o.sheet, head = o.head || el.querySelector('.sheethead'), scrim = o.scrim || null, chev = o.chevron || null;
    var SNAP = o.snap || [0, 40, 72], CLOSED = 100, sy = CLOSED;

    function set(pct, smooth) {
      sy = pct;
      el.classList.toggle('dragging', !smooth);
      el.style.transform = 'translateY(' + pct + '%)';
      /* 遮罩跟着高度深浅走，拖到一半就该透一半 */
      if (scrim) {
        scrim.style.transition = smooth ? '' : 'none';
        scrim.style.opacity = Math.max(0, (CLOSED - pct) / CLOSED * 0.92).toFixed(3);
        scrim.style.pointerEvents = pct >= CLOSED ? 'none' : 'auto';
      }
      if (chev) chev.style.transform = pct >= CLOSED ? '' : 'rotate(90deg)';
      if (o.onChange) o.onChange(pct, smooth);
    }
    function open(v) { set(v ? SNAP[1] : CLOSED, true); }

    var dragging = false, y0 = 0, sy0 = 0, lastY = 0, lastT = 0, vel = 0;
    head.addEventListener('pointerdown', function (e) {
      dragging = true; y0 = e.clientY; sy0 = sy;
      lastY = e.clientY; lastT = e.timeStamp; vel = 0;
      head.setPointerCapture(e.pointerId);
      el.classList.add('dragging');
    });
    head.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      var h = el.offsetHeight || 1;
      var pct = sy0 + (e.clientY - y0) / h * 100;
      if (pct < 0) pct = pct / 3;              // 顶到头给点阻尼，不让它翻上去
      var dt = e.timeStamp - lastT;
      if (dt > 0) { vel = (e.clientY - lastY) / dt; lastY = e.clientY; lastT = e.timeStamp; }
      set(Math.min(pct, CLOSED), false);
    });
    function end() {
      if (!dragging) return;
      dragging = false;
      /* 甩得快就顺着方向走一档，慢就吸最近的 */
      var targets = SNAP.concat([CLOSED]), t;
      if (vel > 0.6)       t = targets.find(function (v) { return v > sy + 1; }) ?? CLOSED;
      else if (vel < -0.6) t = targets.slice().reverse().find(function (v) { return v < sy - 1; }) ?? 0;
      else t = targets.reduce(function (a, b) { return Math.abs(b - sy) < Math.abs(a - sy) ? b : a; });
      set(t, true);
    }
    head.addEventListener('pointerup', end);
    head.addEventListener('pointercancel', end);
    if (scrim) scrim.addEventListener('click', function () { open(false); });

    return { open: open, set: set, pct: function () { return sy; }, snap: SNAP.slice() };
  }
  Parts.sheet = sheet;

  if (typeof module === 'object' && module.exports) module.exports = Parts;
  global.Parts = Parts;
})(typeof window !== 'undefined' ? window : this);
