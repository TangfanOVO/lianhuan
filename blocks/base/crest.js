/*!
 * crest.js —— 家徽。默认是枫叶，能换。
 *
 * 一个界面上应该有一个属于它自己的记号。默认给的是枫叶
 * （Font Awesome Free 6 的 canadian-maple-leaf，CC BY 4.0 —— 用了要署名，见 UPSTREAM.md）。
 * 备选还有几个，也可以整段贴自己的 SVG path 进来。
 *
 *   Crest.mount(el);              // 把徽画进这个元素
 *   Crest.set('paper');           // 换一个
 *   Crest.set({ viewBox:'0 0 24 24', path:'M…', fill:true });   // 用自己的
 *   Crest.list();                 // 有哪些内置的
 *
 * ★ 为什么枫叶用**实心**：26px 以下线条版必糊，试过两版都像星星。
 *   而且它是全屏唯一的实心重点色块 —— 实心才立得住。
 */
(function (global) {
  'use strict';

  var CRESTS = {
    maple: {                       /* 默认 */
      /* ★ 这一份 path 跟原项目 call.html 的 #crest、字云的 D_MAPLE **是同一份**（786 字节逐字相同）。
         0902 之前这儿放的是 FA 的另一个 384×512 变体，柄脚位置差 32.4 ——
         那条线找叶柄的锚点是照 512 这份量的，于是叶子一片都写不出来。
         **全仓库只有这一片枫叶。要换，改这一处。**
         Font Awesome Free 6 · canadian-maple-leaf · Icons CC BY 4.0（署名见 UPSTREAM.md） */
      name: '枫叶', fill: true, viewBox: '0 0 512 512',
      path: 'M383.8 351.7c2.5-2.5 105.2-92.4 105.2-92.4l-17.5-7.5c-10-4.9-7.4-11.5-5-17.4 2.4-7.6 20.1-67.3 20.1-67.3s-47.7 10-57.7 12.5c-7.5 2.4-10-2.5-12.5-7.5s-15-32.4-15-32.4-52.6 59.9-55.1 62.3c-10 7.5-20.1 0-17.6-10 0-10 27.6-129.6 27.6-129.6s-30.1 17.4-40.1 22.4c-7.5 5-12.6 5-17.6-5C293.5 72.3 255.9 0 255.9 0s-37.5 72.3-42.5 79.8c-5 10-10 10-17.6 5-10-5-40.1-22.4-40.1-22.4S183.3 182 183.3 192c2.5 10-7.5 17.5-17.6 10-2.5-2.5-55.1-62.3-55.1-62.3S98.1 167 95.6 172s-5 9.9-12.5 7.5C73 177 25.4 167 25.4 167s17.6 59.7 20.1 67.3c2.4 6 5 12.5-5 17.4L23 259.3s102.6 89.9 105.2 92.4c5.1 5 10 7.5 5.1 22.5-5.1 15-10.1 35.1-10.1 35.1s95.2-20.1 105.3-22.6c8.7-.9 18.3 2.5 18.3 12.5S241 512 241 512h30s-5.8-102.7-5.8-112.8 9.5-13.4 18.4-12.5c10 2.5 105.2 22.6 105.2 22.6s-5-20.1-10-35.1 0-17.5 5-22.5z'
    },
    paper:  { name: '一张纸', viewBox: '0 0 24 24',
      path: 'M5.5 3h8.2L18.5 8v13H5.5z M13.7 3v5h4.8 M8.6 12.5h6.8 M8.6 16h4.4' },
    moon:   { name: '月亮', viewBox: '0 0 24 24',
      path: 'M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z' },
    house:  { name: '屋子', viewBox: '0 0 24 24',
      path: 'M3.5 11.5 12 4l8.5 7.5 M5.5 10v10h13V10' },
    knot:   { name: '结', viewBox: '0 0 24 24',
      path: 'M8 8a4 4 0 1 1 8 0c0 3-8 5-8 8a4 4 0 1 0 8 0' },
    leafy:  { name: '叶', viewBox: '0 0 24 24',
      path: 'M5 19c0-8 5-14 14-14 0 9-5 14-14 14z M9 15c2-3 5-5 8-6' }
  };

  var current = 'maple';
  var mounted = [];

  function def(c) { return typeof c === 'string' ? (CRESTS[c] || CRESTS.maple) : c; }

  function svg(c) {
    c = def(c);
    var t = c.transform ? ' transform="' + c.transform + '"' : '';
    var paint = c.fill
      ? 'fill="currentColor"'
      : 'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"';
    return '<svg viewBox="' + c.viewBox + '" ' + paint + ' aria-hidden="true">'
         + '<path d="' + c.path + '"' + t + '/></svg>';
  }

  function paint() { mounted.forEach(function (el) { el.innerHTML = svg(current); }); }

  global.Crest = {
    mount: function (el) { if (el && mounted.indexOf(el) < 0) mounted.push(el); paint(); },
    set: function (c) { current = c; paint(); try { localStorage.setItem('crest', typeof c === 'string' ? c : ''); } catch (e) {} },
    get: function () { return current; },
    svg: svg,
    list: function () { return Object.keys(CRESTS).map(function (k) { return { key: k, name: CRESTS[k].name }; }); },
    /* ★ 取原始定义 {name, viewBox, path, fill?, transform?}。
       别的积木要拿这几片形状去用（记忆星图换形状、通话那条线编叶子），
       靠 svg() 拿到的是一串 HTML，还得再解析一遍 —— 那不合适。 */
    def: function (k) { var c = CRESTS[k] || CRESTS.maple; return {
      key: CRESTS[k] ? k : 'maple', name: c.name, viewBox: c.viewBox, path: c.path,
      fill: !!c.fill, transform: c.transform || '' }; },
    add: function (key, c) { CRESTS[key] = c; }
  };
  try { var s = localStorage.getItem('crest'); if (s && CRESTS[s]) current = s; } catch (e) {}
})(typeof window !== 'undefined' ? window : this);
