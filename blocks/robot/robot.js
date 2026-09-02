/* 机器人 · 那一页的渲染层
   ════════════════════════════════════════════════════════════════════
   零依赖。一行 fetch 都没有 —— 取数全在 `robot-data.js`，换后端只改那一个文件。

   ★ 这块**只有前端**。为什么见 README。

   最值钱的是下面那两张示意图：头的角度是这一页唯一一个**有空间感**的数据，
   一个俯视、一个侧视，比两行数字好懂得多。几何原样照搬设计稿：
     俯视：圆心 (120,122) R=100，指针角 = yaw − 90°，水平视场 66°
     侧视：圆心 (56,118)，抬角 el = pitch + 20，指针 R=108，扇形 R=94 ± 视场/2
   ════════════════════════════════════════════════════════════════════ */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.RobotPage = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var FOV = { h: 66, v: 49.5 };
  var LIM = { yaw: [-85, 85], pitch: [-20, 88], home: { yaw: -3, pitch: -8 } };

  function pt(cx, cy, r, deg) {
    var a = deg * Math.PI / 180;
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  }
  function svg(tag, attrs) {
    var e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  var clamp = function (v, lo, hi) { return Math.max(lo, Math.min(hi, v)); };

  /* ── 俯视：它往左往右看 ───────────────────────────────── */
  function topView(yaw) {
    var R = 100, cx = 120, cy = 122;
    var s = svg('svg', { viewBox: '0 0 240 150', class: 'rb-view' });
    var half = FOV.h / 2;
    var fa = pt(cx, cy, R, -90 - half), fb = pt(cx, cy, R, -90 + half);
    var home = pt(cx, cy, R * 0.66, -93);
    var tip = pt(cx, cy, R, yaw - 90);
    /* 半圆的底盘 */
    s.appendChild(svg('path', { class: 'rb-dial',
      d: 'M' + (cx - R) + ' ' + cy + ' A' + R + ' ' + R + ' 0 0 1 ' + (cx + R) + ' ' + cy }));
    /* 视场：它此刻真能看见的那一扇（跟着头转） */
    var g = svg('g', { transform: 'rotate(' + yaw + ' ' + cx + ' ' + cy + ')' });
    g.appendChild(svg('path', { class: 'rb-fov',
      d: 'M' + cx + ' ' + cy + ' L' + fa.x.toFixed(1) + ' ' + fa.y.toFixed(1)
       + ' A' + R + ' ' + R + ' 0 0 1 ' + fb.x.toFixed(1) + ' ' + fb.y.toFixed(1) + ' Z' }));
    s.appendChild(g);
    /* 刻度：每 15 度一根 */
    for (var d = -90; d <= 90; d += 15) {
      var a = pt(cx, cy, R * 0.9, d - 90), b = pt(cx, cy, R, d - 90);
      s.appendChild(svg('line', { class: 'rb-tick', x1: a.x, y1: a.y, x2: b.x, y2: b.y }));
    }
    s.appendChild(svg('circle', { class: 'rb-home', cx: home.x, cy: home.y, r: 3 }));
    s.appendChild(svg('line', { class: 'rb-needle', x1: cx, y1: cy, x2: tip.x, y2: tip.y }));
    s.appendChild(svg('circle', { class: 'rb-pivot', cx: cx, cy: cy, r: 5 }));
    return s;
  }

  /* ── 侧视：它抬头还是低头 ─────────────────────────────── */
  function sideView(pitch) {
    var cx = 56, cy = 118;
    var s = svg('svg', { viewBox: '0 0 190 150', class: 'rb-view' });
    var el0 = pitch + 20, half = FOV.v / 2;
    var tip = pt(cx, cy, 108, -el0);
    var f1 = pt(cx, cy, 94, -(el0 + half)), f2 = pt(cx, cy, 94, -(el0 - half));
    var home = pt(cx, cy, 70, -12);
    s.appendChild(svg('path', { class: 'rb-dial',
      d: 'M' + cx + ' ' + (cy - 108) + ' A108 108 0 0 1 ' + (cx + 108) + ' ' + cy }));
    /* ★ 水平线以下是物理盲区 —— 画出来，别让人以为它能看见地板 */
    s.appendChild(svg('line', { class: 'rb-floor', x1: cx, y1: cy, x2: cx + 118, y2: cy }));
    s.appendChild(svg('path', { class: 'rb-fov',
      d: 'M' + cx + ' ' + cy + ' L' + f1.x.toFixed(1) + ' ' + f1.y.toFixed(1)
       + ' A94 94 0 0 1 ' + f2.x.toFixed(1) + ' ' + f2.y.toFixed(1) + ' Z' }));
    s.appendChild(svg('circle', { class: 'rb-home', cx: home.x, cy: home.y, r: 3 }));
    s.appendChild(svg('line', { class: 'rb-needle', x1: cx, y1: cy, x2: tip.x, y2: tip.y }));
    s.appendChild(svg('circle', { class: 'rb-pivot', cx: cx, cy: cy, r: 5 }));
    return s;
  }

  function readout(label, value, note) {
    var box = el('div', 'rb-cell');
    box.appendChild(el('div', 'rb-lb', label));
    box.appendChild(el('div', 'rb-val', value));
    if (note) box.appendChild(el('div', 'rb-note', note));
    return box;
  }

  return function RobotPage(host, opts) {
    opts = opts || {};
    var d = opts.data || {};
    var live = !!opts.live;
    var onSend = opts.onSend || function () {};
    var yaw = clamp((d.head || {}).yaw || 0, LIM.yaw[0], LIM.yaw[1]);
    var pitch = clamp((d.head || {}).pitch || 0, LIM.pitch[0], LIM.pitch[1]);

    host.innerHTML = '';
    host.classList.add('rb');

    /* 在不在 */
    var head = el('div', 'rb-top');
    var lamp = el('span', 'rb-lamp' + (d.online ? ' on' : ''));
    head.appendChild(lamp);
    var t = el('div');
    t.appendChild(el('b', null, d.online ? '它在' : (live ? '它在打盹' : '不知道它在不在')));
    t.appendChild(el('i', null, d.online
      ? (d.why || '连着服务器 —— 想按什么都通。')
      : (live ? (d.why || '息屏了，连接断着。待机时它根本不连服务器 —— 这是架构，不是故障。')
              : '没接上 /api/robot —— 是它睡了还是后端没起，这一页不替你猜。')));
    head.appendChild(t);
    host.appendChild(head);

    /* ★ 取不到就明说是占位，不冒充实时 */
    host.appendChild(el('div', 'rb-src', live
      ? '实时 · 直接读的 /api/robot'
      : '还没接后端 —— 下面是一份占位数据，形状是真的，数不是。'));

    /* 身体 */
    var grid = el('div', 'rb-grid');
    var b = d.battery || {}, n = d.network || {};
    grid.appendChild(readout('电量', (b.level != null ? b.level : '—') + '%',
      b.charging ? '在充' : '没在充'));
    grid.appendChild(readout('网络', n.ssid || '—', (n.type || '') + ' · ' + (n.signal || '')));
    grid.appendChild(readout('音量', (d.volume != null ? d.volume : '—') + '', '0–100'));
    grid.appendChild(readout('屏幕', (d.brightness != null ? d.brightness : '—') + '',
      '亮度 · ' + (d.theme || '')));
    host.appendChild(grid);

    /* 头的角度 —— 这一页唯一有空间感的数据 */
    var hb = el('div', 'rb-heads');
    [['往哪边看', topView(yaw), 'yaw ' + yaw + '°', LIM.yaw],
     ['抬头低头', sideView(pitch), 'pitch ' + pitch + '°', LIM.pitch]].forEach(function (row) {
      var box = el('div', 'rb-head');
      box.appendChild(el('div', 'rb-lb', row[0]));
      box.appendChild(row[1]);
      box.appendChild(el('div', 'rb-val', row[2]));
      hb.appendChild(box);
    });
    host.appendChild(hb);
    /* ⚠ 这里是纯文本节点，别写 markdown 的星号 —— 会原样显示出来（0830 当场看见了） */
    var tip = el('div', 'rb-note');
    tip.appendChild(document.createTextNode('正的 yaw ＝ 机器人自己的右手边。'));
    tip.appendChild(el('b', null, '水平线以下是物理盲区'));
    tip.appendChild(document.createTextNode(
      ' —— 镜头光轴自带上仰角，俯仰压到底也只到水平线，人蹲下、躺下它是真找不到。'
      + '软件补不了，只能把它垫高。'));
    host.appendChild(tip);

    /* 回正 */
    var act = el('div', 'rb-act');
    var home = el('button', 'rb-btn', '回正面');
    home.type = 'button';
    home.addEventListener('click', function () { onSend({ head: LIM.home }); });
    act.appendChild(home);
    host.appendChild(act);

    return { el: host, limits: LIM, fov: FOV };
  };
});
