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
 * ⚠ sheet 的三档吸附拖动没在这儿。见 README。
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

  if (typeof module === 'object' && module.exports) module.exports = Parts;
  global.Parts = Parts;
})(typeof window !== 'undefined' ? window : this);
