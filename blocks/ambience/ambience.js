/* 漂浮物 —— 背景里飘着的那些小东西
   ════════════════════════════════════════════════════════════════════
   零依赖。十种图标，可以多选，密度和速度各一个把手。

   ★ 图标**没有一个是手画的**（除了萤火那一点光 —— 图标库里没有「一点光」）：
     枫叶来自 Font Awesome Free 6（CC BY 4.0，**要署名**），
     其余来自 Tabler Icons（MIT）。出处和许可正文在仓库根的 THIRD_PARTY_NOTICES.md。

   ★ 多选时**轮着来，不是随机** —— 随机会出现某一种一片都没落下的情况。
   ════════════════════════════════════════════════════════════════════ */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Ambience = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

var SHAPES = {
  /* Font Awesome Free 6 · canadian-maple-leaf（实心） */
  maple:['solid','0 0 512 512','<path d="M383.8 351.7c2.5-2.5 105.2-92.4 105.2-92.4l-17.5-7.5c-10-4.9-7.4-11.5-5-17.4 2.4-7.6 20.1-67.3 20.1-67.3s-47.7 10-57.7 12.5c-7.5 2.4-10-2.5-12.5-7.5s-15-32.4-15-32.4-52.6 59.9-55.1 62.3c-10 7.5-20.1 0-17.6-10 0-10 27.6-129.6 27.6-129.6s-30.1 17.4-40.1 22.4c-7.5 5-12.6 5-17.6-5C293.5 72.3 255.9 0 255.9 0s-37.5 72.3-42.5 79.8c-5 10-10 10-17.6 5-10-5-40.1-22.4-40.1-22.4S183.3 182 183.3 192c2.5 10-7.5 17.5-17.6 10-2.5-2.5-55.1-62.3-55.1-62.3S98.1 167 95.6 172s-5 9.9-12.5 7.5C73 177 25.4 167 25.4 167s17.6 59.7 20.1 67.3c2.4 6 5 12.5-5 17.4L23 259.3s102.6 89.9 105.2 92.4c5.1 5 10 7.5 5.1 22.5-5.1 15-10.1 35.1-10.1 35.1s95.2-20.1 105.3-22.6c8.7-.9 18.3 2.5 18.3 12.5S241 512 241 512h30s-5.8-102.7-5.8-112.8 9.5-13.4 18.4-12.5c10 2.5 105.2 22.6 105.2 22.6s-5-20.1-10-35.1 0-17.5 5-22.5z"/>'],
  /* 以下四个 · Tabler Icons（MIT） */
  flower:['line','0 0 24 24','<path d="M9 12a3 3 0 1 0 6 0a3 3 0 1 0 -6 0"/><path d="M12 2a3 3 0 0 1 3 3c0 .562 -.259 1.442 -.776 2.64l-.724 1.36l1.76 -1.893c.499 -.6 .922 -1 1.27 -1.205a2.968 2.968 0 0 1 4.07 1.099a3.011 3.011 0 0 1 -1.09 4.098c-.374 .217 -.99 .396 -1.846 .535l-2.664 .366l2.4 .326c1 .145 1.698 .337 2.11 .576a3.011 3.011 0 0 1 1.09 4.098a2.968 2.968 0 0 1 -4.07 1.098c-.348 -.202 -.771 -.604 -1.27 -1.205l-1.76 -1.893l.724 1.36c.516 1.199 .776 2.079 .776 2.64a3 3 0 0 1 -6 0c0 -.562 .259 -1.442 .776 -2.64l.724 -1.36l-1.76 1.893c-.499 .601 -.922 1 -1.27 1.205a2.968 2.968 0 0 1 -4.07 -1.098a3.011 3.011 0 0 1 1.09 -4.098c.374 -.218 .99 -.396 1.846 -.536l2.664 -.366l-2.4 -.325c-1 -.145 -1.698 -.337 -2.11 -.576a3.011 3.011 0 0 1 -1.09 -4.099a2.968 2.968 0 0 1 4.07 -1.099c.348 .203 .771 .604 1.27 1.205l1.76 1.894c-1 -2.292 -1.5 -3.625 -1.5 -4a3 3 0 0 1 3 -3"/>'],
  heart:['line','0 0 24 24','<path d="M19.5 12.572l-7.5 7.428l-7.5 -7.428a5 5 0 1 1 7.5 -6.566a5 5 0 1 1 7.5 6.572"/>'],
  bubble:['line','0 0 24 24','<path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0"/><path d="M8 8.5a2.4 2.4 0 0 1 2 -1.4"/>'],
  rain:['line','0 0 24 24','<path d="M7.502 19.423c2.602 2.105 6.395 2.105 8.996 0c2.602 -2.105 3.262 -5.708 1.566 -8.546l-4.89 -7.26c-.42 -.625 -1.287 -.803 -1.936 -.397a1.376 1.376 0 0 0 -.41 .397l-4.893 7.26c-1.695 2.838 -1.035 6.441 1.567 8.546"/>'],
  /* 0805 补的另外几种，样子更有意思一点。还是 Tabler（MIT），一样的 24×24 线条规格；
     萤火是自己画的一个圆点 —— 图标库里没有「一点光」这种东西。 */
  snow:['line','0 0 24 24','<path d="M10 4l2 1l2 -1"/><path d="M12 2v6.5l3 1.72"/><path d="M17.928 6.268l.134 2.232l1.866 1.232"/><path d="M20.66 7l-5.629 3.25l.01 3.458"/><path d="M19.928 14.268l-1.866 1.232l-.134 2.232"/><path d="M20.66 17l-5.629 -3.25l-2.99 1.738"/><path d="M14 20l-2 -1l-2 1"/><path d="M12 22v-6.5l-3 -1.72"/><path d="M6.072 17.732l-.134 -2.232l-1.866 -1.232"/><path d="M3.34 17l5.629 -3.25l-.01 -3.458"/><path d="M4.072 9.732l1.866 -1.232l.134 -2.232"/><path d="M3.34 7l5.629 3.25l2.99 -1.738"/>'],
  star:['line','0 0 24 24','<path d="M12 17.75l-6.172 3.245l1.179 -6.873l-5 -4.867l6.9 -1l3.086 -6.253l3.086 6.253l6.9 1l-5 4.867l1.179 6.873z"/>'],
  note:['line','0 0 24 24','<path d="M3 17a3 3 0 1 0 6 0a3 3 0 0 0 -6 0"/><path d="M13 17a3 3 0 1 0 6 0a3 3 0 0 0 -6 0"/><path d="M9 17v-13h10v13"/><path d="M9 8h10"/>'],
  fish:['line','0 0 24 24','<path d="M16.69 7.44a6.973 6.973 0 0 0 -1.69 4.56c0 1.747 .64 3.345 1.699 4.571"/><path d="M2 9.504c7.715 8.647 14.75 10.265 20 2.498c-5.25 -7.761 -12.285 -6.142 -20 2.504"/><path d="M18 11v.01"/><path d="M11.5 10.5c-.667 1 -.667 2 0 3"/>'],
  firefly:['solid','0 0 24 24','<circle cx="12" cy="12" r="5"/>']
};  var KINDS = [['maple','枫叶'],['flower','花瓣'],['heart','爱心'],['bubble','泡泡'],
                   ['rain','雨'],['snow','雪'],['star','星'],['note','音符'],
                   ['fish','小鱼'],['firefly','萤火']];

  return function Ambience(host, opts) {
    opts = opts || {};
    var state = {
      kinds: (opts.kinds || ['maple']).slice(),
      count: opts.count == null ? 9 : opts.count,
      speed: opts.speed == null ? 1 : opts.speed,
    };
    host.classList.add('floaty');
    host.setAttribute('aria-hidden', 'true');   /* 纯装饰，读屏跳过 */

    function render() {
      host.innerHTML = '';
      var kinds = state.kinds.filter(function (k) { return SHAPES[k]; });
      if (!kinds.length || !state.count) return;
      for (var k = 0; k < state.count; k++) {
        var s = SHAPES[kinds[k % kinds.length]];          /* 轮着来，不随机 */
        var el = document.createElement('i'), sz = 13 + Math.random() * 15;
        el.style.left    = (Math.random() * 96) + '%';
        el.style.width   = sz + 'px';
        el.style.height  = sz + 'px';
        el.style.opacity = (0.1 + Math.random() * 0.16).toFixed(2);
        /* 速度＝时长除以倍率。往右拉＝飘得快＝时长短。
           ★ 延迟也要跟着缩，不然拉快之后前几秒画面是空的。 */
        var dur = (13 + Math.random() * 15) / Math.max(0.1, state.speed);
        el.style.animationDuration = dur.toFixed(1) + 's';
        el.style.animationDelay    = (-Math.random() * dur).toFixed(1) + 's';
        el.style.setProperty('--drift', (Math.random() * 80 - 40).toFixed(0) + 'px');
        el.style.setProperty('--spin',  (Math.random() * 520 - 200).toFixed(0) + 'deg');
        el.innerHTML = '<svg data-' + s[0] + ' viewBox="' + s[1] + '">' + s[2] + '</svg>';
        host.appendChild(el);
      }
    }
    render();
    return {
      kinds: KINDS,                                  /* [[key, 中文名], …] 给你长选择器用 */
      set: function (patch) { Object.assign(state, patch || {}); render(); },
      get: function () { return Object.assign({}, state); },
      clear: function () { state.kinds = []; render(); },
    };
  };
});
