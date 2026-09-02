/* 换重点色 —— 底座的一部分。
   一个界面只有一个重点色，所以换肤就是改这几个变量。

   ★ 关键在 onAccent()：重点色上面那层字是白是深，**要算不能猜**。
     第一版写死白字，结果暗色主题下用户自己说的话对比度只有 2.17。 */
(function (g) {
  'use strict';

  function srgb(c) { c /= 255; return c <= .03928 ? c / 12.92 : Math.pow((c + .055) / 1.055, 2.4); }

  function luminance(hex) {
    var m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (!m) return 1;
    return .2126 * srgb(parseInt(m[1], 16)) + .7152 * srgb(parseInt(m[2], 16)) + .0722 * srgb(parseInt(m[3], 16));
  }

  /* 白字和深字，谁对比度高用谁。
     ★ 0.071 是深字 #2b2724 的相对亮度 0.021 加 0.05（WCAG 公式里的常数）。
       写大了会系统性低估深字，结果永远挑白的 —— 第一版就栽在这个常数上，
       12 个色全选白字才发现不对。                                   */
  function onAccent(hex, dark) {
    dark = dark || '#2b2724';
    var L = luminance(hex);
    var withWhite = 1.05 / (L + .05);
    var withDark  = (L + .05) / 0.071;
    return withDark > withWhite ? dark : '#fff';
  }

  function setAccent(hex) {
    var r = document.documentElement.style;
    r.setProperty('--accent', hex);
    r.setProperty('--accent-soft', 'color-mix(in srgb, ' + hex + ' 18%, transparent)');
    r.setProperty('--on-accent', onAccent(hex));   /* ★ 这行别漏，漏了字就看不清 */
  }

  /* 都验过在纸底和夜色底上都立得住 */
  var PALETTE = [
    { name: '枫叶红', hex: '#b5533a' }, { name: '琥珀', hex: '#b9884f' },
    { name: '青竹',   hex: '#6f8f6a' }, { name: '远山', hex: '#5a7d99' },
    { name: '藕紫',   hex: '#8a6a86' }, { name: '墨',   hex: '#4a4441' }
  ];

  g.Accent = { set: setAccent, onAccent: onAccent, luminance: luminance, PALETTE: PALETTE };
})(window);
