/* ════════════════════════════════════════════════════════════════════
   这一份是从应用 `index.html` 里**原样抽出来的**（应用是单文件零构建，
   内联在一整块脚本里，没法引外链）。两份物理上分开存，
   `tests/` 里钉了一条：对不上就红。改任何一处都要两边一起改。
   ════════════════════════════════════════════════════════════════════ */
/* 记忆字云 · Memory Glyph Cloud —— 原生版（0827）
   ★ 出处（0830 核实）：采样与形变配对的算法出自 ThreeUI 的
     Text on a Path II — Study 08「Morphing Glyph Cloud」——
     Meng To 已开源（github.com/MengTo/threeui，MIT，Community 部分含此件）。
     连线、透视深度、拾取与高亮是本项目这份设计新增的。见 UPSTREAM.md。
   ═══════════════════════════════════════════════════════════════════════
   设计和这份实现的算法出自一份设计 handoff。README 的原话：绘制部分的算法应当照搬，外壳换成
   目标代码库自己的组件。连环没有构建链，所以这儿把 React/DCLogic 那层脱掉，
   写成一个无依赖的原生组件；**画布里的每一行算法都是照搬的**。

   采样与形变配对的做法上溯到 ThreeUI 的 Text on a Path II — Study 08
   Morphing Glyph Cloud；连线、透视深度、拾取与高亮是用户这份设计新增的。

   ★ 我做的唯一一处实质改动，是 README「接后端」那一节点名要的反向依赖：
     原型是「形状面积和字号决定采样点数」，真接数据要反过来 ——
     **先按记忆条数解字号，再采样**，这样一个字符严格对应一条记忆，
     不多一个空位、不少一条记忆。见 solveFS()。 */
(function (global) {
  'use strict';

  var CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789<>/\\{}[]()=+-*#$%&@?!";

  /* 四档字形，iOS 原生都有，不用加载 webfont。
     wl 是**浅底**用的字重：发丝笔画在 7px 上画出来几乎全是抗锯齿的半覆盖像素 ——
     深底上读作发光，浅底上就是没画上去。这是覆盖率问题，调透明度治不好。 */
  var FACES = {
    '细黑': { fam: '"Helvetica Neue", Helvetica, Arial, sans-serif', w: 200, wl: 500 },
    '轻黑': { fam: '"Helvetica Neue", Helvetica, Arial, sans-serif', w: 300, wl: 600 },
    '衬线': { fam: 'Georgia, "Times New Roman", serif', w: 400, wl: 700 },
    '粗黑': { fam: 'Inter, system-ui, sans-serif', w: 700, wl: 700 }
  };

  function rng(seed) {
    var s = seed >>> 0;
    return function () {
      s ^= s << 13; s >>>= 0; s ^= s >> 17; s ^= s << 5; s >>>= 0; return s / 4294967296;
    };
  }

  /* 形状光栅化。原版 fitPoints 每次调用都重新光栅化一遍 320²；这儿拆成两步，
     因为解字号要用不同的 spacing 反复采样十几轮，形状本身一次就够。 */
  function raster(paint) {
    var S = 320, c = document.createElement('canvas');
    c.width = c.height = S;
    var x = c.getContext('2d');
    paint(x, S);
    var data = x.getImageData(0, 0, S, S).data;
    var hit = new Uint8Array(S * S);
    var x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, any = 0;
    for (var i = 0; i < S * S; i++) {
      if (data[i * 4 + 3] <= 128) continue;
      hit[i] = 1; any++;
      var gx = i % S, gy = (i / S) | 0;
      if (gx < x0) x0 = gx; if (gx > x1) x1 = gx;
      if (gy < y0) y0 = gy; if (gy > y1) y1 = gy;
    }
    if (!any) return null;
    return { S: S, hit: hit, x0: x0, x1: x1, y0: y0, y1: y1,
             span: Math.max(x1 - x0, y1 - y0) || 1,
             mx: (x0 + x1) / 2, my: (y0 + y1) / 2 };
  }

  /* 在 bbox 上按 cell 走一遍抖动网格，落在形状里的留下。
     输出归一化到 bbox，所以宽扁的形状和高瘦的形状占同样大的画面。 */
  function sample(R, spacing, rand) {
    if (!R) return [];
    var cell = Math.max(1.6, spacing * R.span), out = [];
    for (var gy = R.y0; gy < R.y1; gy += cell) {
      for (var gx = R.x0; gx < R.x1; gx += cell) {
        var jx = gx + rand() * cell, jy = gy + rand() * cell;
        var ix = jx | 0, iy = jy | 0;
        if (ix < 0 || ix >= R.S || iy < 0 || iy >= R.S || !R.hit[iy * R.S + ix]) continue;
        out.push({ x: (jx - R.mx) / R.span, y: (jy - R.my) / R.span });
      }
    }
    return out;
  }

  /* 极角优先、半径次之。这一步是形变好看的全部原因：
     按角度配对，形变读作**转身**；随机配对读作洗牌。 */
  function order(set) {
    return set.map(function (p, i) {
      return { i: i, a: Math.atan2(p.y, p.x), r: Math.hypot(p.x, p.y) };
    }).sort(function (u, v) { return u.a - v.a || u.r - v.r; })
      .map(function (o) { return o.i; });
  }

  /* 形状是遮罩，跟数据无关 —— 想换只换 path。
     ★ 0830 换过一次：原来头两片是 **Claude 和 Claude Code 的 logo**。
       自己原项目用没问题，但这份是要发出去的 —— 一个开源项目默认把别家的商标
       当装饰形状，会让人以为它是那家出的。**商标不是许可证能解决的事**
       （MIT 那种「署名就能用」不适用于商标），所以换成了中性的：心、圆、枫叶。
       想换回什么形状都行，改下面三个 path 即可，一个字符对一条记忆的算法不受影响。
     ★ 枫叶那片是 Font Awesome Free 6 的 canadian-maple-leaf（CC BY 4.0，要署名，
       声明在 THIRD_PARTY_NOTICES.md），viewBox 是 512 不是 24 ——
       所以 SHAPES 每一项都带各自的画布尺寸。
     ★ 心和圆是这儿自己写的，没有出处要交代。 */
  var D_HEART = "M12 21C4 15 2 10.6 2 7.8A4.8 4.8 0 0 1 12 6a4.8 4.8 0 0 1 10 1.8C22 10.6 20 15 12 21Z";
  var D_RING  = "M2 12a10 10 0 0 1 20 0a10 10 0 0 1 -20 0Z";

  var D_MAPLE = "M383.8 351.7c2.5-2.5 105.2-92.4 105.2-92.4l-17.5-7.5c-10-4.9-7.4-11.5-5-17.4 2.4-7.6 20.1-67.3 20.1-67.3s-47.7 10-57.7 12.5c-7.5 2.4-10-2.5-12.5-7.5s-15-32.4-15-32.4-52.6 59.9-55.1 62.3c-10 7.5-20.1 0-17.6-10 0-10 27.6-129.6 27.6-129.6s-30.1 17.4-40.1 22.4c-7.5 5-12.6 5-17.6-5C293.5 72.3 255.9 0 255.9 0s-37.5 72.3-42.5 79.8c-5 10-10 10-17.6 5-10-5-40.1-22.4-40.1-22.4S183.3 182 183.3 192c2.5 10-7.5 17.5-17.6 10-2.5-2.5-55.1-62.3-55.1-62.3S98.1 167 95.6 172s-5 9.9-12.5 7.5C73 177 25.4 167 25.4 167s17.6 59.7 20.1 67.3c2.4 6 5 12.5-5 17.4L23 259.3s102.6 89.9 105.2 92.4c5.1 5 10 7.5 5.1 22.5-5.1 15-10.1 35.1-10.1 35.1s95.2-20.1 105.3-22.6c8.7-.9 18.3 2.5 18.3 12.5S241 512 241 512h30s-5.8-102.7-5.8-112.8 9.5-13.4 18.4-12.5c10 2.5 105.2 22.6 105.2 22.6s-5-20.1-10-35.1 0-17.5 5-22.5z";

  /* 下面这几片是这儿自己画的，没有出处要交代。都是**闭合能填的**轮廓 ——
     字云是拿填充区域去撒字的，描线那种（房子、结）填出来是一团糊，别往里放。 */
  var D_STAR  = "M12 2.6l2.9 6.1 6.6.9-4.8 4.7 1.2 6.6-5.9-3.2-5.9 3.2 1.2-6.6L2.5 9.6l6.6-.9z";
  var D_CLOUD = "M7 19a4.6 4.6 0 0 1-.5-9.2A6 6 0 0 1 17.8 9a4.2 4.2 0 0 1 .7 8.3 4 4 0 0 1-.5.1z";
  var D_CAT   = "M4.6 8.2 4 3.7l3.9 2.4a9.6 9.6 0 0 1 8.2 0L20 3.7l-.6 4.5A8 8 0 0 1 21 13c0 4.4-4 8-9 8s-9-3.6-9-8a8 8 0 0 1 1.6-4.8z";
  var D_MOON  = "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z";
  var D_LEAF  = "M5 19c0-8 5-14 14-14 0 9-5 14-14 14z";

  /* 出厂这几片。**换成什么都行** —— `create(cv, {shapes: […]})` 一传就整组换掉，
     每片写 `{d: 'SVG 的 path', box: 那个 path 的 viewBox 边长, name: '给人看的名字'}`。
     ★ 想放哪家模型的标、自家的 logo，自己贴进去就是了。
       这份仓库里不预置任何厂商的商标：**分发别人的商标跟用别人的代码不是一回事** ——
       MIT 那种「署名就能用」对商标不适用，而你自己给自己贴，那是你自己的事。
     ★ 出厂给够几片是有理由的：只给一片，采用者装完看到的就是死的一个形状，
       得读文档、写代码才知道能换。给一排能点的，「这东西能换」不用讲。 */
  var DEFAULT_SHAPES = [
    { d: D_MAPLE, box: 512, name: '枫叶' },
    { d: D_HEART, box: 24,  name: '心' },
    { d: D_RING,  box: 24,  name: '圆' },
    { d: D_STAR,  box: 24,  name: '星' },
    { d: D_CLOUD, box: 24,  name: '云' },
    { d: D_CAT,   box: 24,  name: '猫' },
    { d: D_MOON,  box: 24,  name: '月' },
    { d: D_LEAF,  box: 24,  name: '叶' }
  ];

  function bakeShapes(list) {
    return (list && list.length ? list : DEFAULT_SHAPES).map(function (s) {
      var box = s.box || 24;
      return {
        name: s.name || '',
        paint: function (x, S) {
          x.setTransform(S / box, 0, 0, S / box, 0, 0);
          x.fillStyle = '#000';
          x.fill(new Path2D(s.d), 'evenodd');
          x.setTransform(1, 0, 0, 1, 0, 0);
        }
      };
    });
  }

  function hex2rgb(v, fb) {
    v = String(v || fb).replace('#', '');
    if (v.length === 3) v = v.split('').map(function (c) { return c + c; }).join('');
    return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16)];
  }

  function create(cv, opts) {
    opts = opts || {};
    var A_ = {
      memories: opts.memories || [],
      accent: opts.accent || '#d97757',
      face: opts.face || '粗黑',
      linkDensity: opts.linkDensity == null ? 1.75 : opts.linkDensity,
      depth: opts.depth == null ? 0.1 : opts.depth,
      showLinks: opts.showLinks !== false,
      mutate: opts.mutate !== false,
      accentDim: opts.accentDim !== false,   /* 浅底是否把重点色降阶，见 buildHot */
      /* ★ 横向中心。上游写死的是 w/2 + min(w,h)*0.06 —— 那个 6% 是**给上游那版
         左下角 340px 宽的控制面板让位的**（1280×760 的桌面布局）。我们的控制条在右下，
         照抄过来就是纯粹的歪，用户一眼看出来了。默认摆正，谁要让位谁自己传。
         教训跟今天另外两条一样：**别人规格里的数值是跟着他那套布局/配色定的，换了就得重定。** */
      centerX: opts.centerX == null ? 0.5 : opts.centerX,
      centerY: opts.centerY == null ? 0.5 : opts.centerY,
      linkAlpha: opts.linkAlpha,        /* 不给就按深浅两档的默认走 */
      onSelect: opts.onSelect || function () {},
      onReady: opts.onReady || function () {}
    };
    /* whiteLinks=true：静止的连线跟字符同色（定下的默认）。
       README 那版默认是界面重点色，那是 Nocturne 的调子，原项目一片灰更安静。 */
    var S = { shape: 0, sel: null, pick: false, light: !!opts.light,
              whiteLinks: opts.whiteLinks !== false, spin: false };

    /* 字符的墨色。默认是上游作者调的中性蓝灰；预览页把它换成原项目的 --ink，
       这样深浅两套跟连环一致（纸底暖褐、夜里冷白）。 */
    var LIGHTNODE = hex2rgb(opts.inkLight, '#425262'), DARKNODE = hex2rgb(opts.inkDark, '#8a94a0');
    var LINE = hex2rgb(opts.lineColor, '#9184d9');
    var self = {}, ink64 = [], hot64 = [], line64 = [], HOT = [217, 119, 87], hotCss = '';
    var pair = [], links = [], leaf = [], adj = [], focusAdj = [];
    var px, py, pd, pz, orderIdx, FS = 0.0165, nGlyph = 0, nLink = 0;
    /* 语义邻居（后端现算的）＋ 它们朝选中那条靠拢的力度。
       ★ 0827 定的：与其守住一个好看的排布、让相关的两条隔半张图连一根长线，
         不如**点中那一瞬间把相关的挪到附近来**。反正字符本来就一直在变、
         切个形状连线全都要重排，布局不是神圣的 —— 显示真实的关系才是。
         松开就各回各位，剪影一点不受损。 */
    var related = null, pull = 0, pullT = 0;
    var from = 0, to = 0;              /* 正在去的那个形态；from<0 表示起点是 g.cur 快照 */
    var viewX = 0, viewXT = 0, viewY = 0, viewYT = 0, zoom = 1, zoomT = 1;
    var panX = 0, panY = 0, hover = -1, m = 1, target = 1, drag = null;
    var pts = new Map(), pinch = null, mid = null, w = 0, h = 0, dpr = 1, mx = 0, my = 0;
    var raf = 0, t0 = 0, prev = 0, ro = null, dead = false;
    var reduceMotion = window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function buildInk() {
      var ink = S.light ? LIGHTNODE : DARKNODE;
      var floor = S.light ? 0.27 : 0.30, spread = S.light ? 0.19 : 0.20;
      ink64 = [];
      for (var q = 0; q < 64; q++) ink64.push('rgba(' + ink + ',' + (floor + q / 63 * spread).toFixed(4) + ')');
      /* 连线的透明度上限。这一档是**底网**，不是主角 —— 字符才是。
         0827 定的：整体再降一档。深底 0.46→0.36、浅底 0.32→0.25。
         （0.22 那个原始值是 README 配 Nocturne 那个紫定的，原项目换成跟字同色的灰之后
         得重新定 —— 换了色就得重定数值，跟出门页那条同一个道理。）
         实际落到画面上还要乘 lv/23≈0.71，所以深底约 0.26、浅底约 0.18。 */
      var lc = S.whiteLinks ? ink : LINE;
      var ceil = A_.linkAlpha != null ? A_.linkAlpha : (S.light ? 0.25 : 0.36);
      line64 = [];
      for (var k = 0; k < 24; k++) line64.push('rgba(' + lc + ',' + (k / 23 * ceil).toFixed(4) + ')');
    }
    function buildHot() {
      var rgb = hex2rgb(A_.accent, '#d97757');
      /* 浅底上重点色必须降阶，不然它压不住、也够不着 3:1。
         ★ 但只在「一个色通吃两种底」时才需要 —— 原项目的 --maple 深浅两态各有各的值
         （纸底 #b5533a / 夜里 #e0a373），已经各自调好，再乘一次就闷了。所以给个开关。 */
      if (S.light && A_.accentDim) rgb = rgb.map(function (c) { return Math.round(c * 0.66); });
      HOT = rgb; hotCss = 'rgb(' + rgb + ')';
      hot64 = [];
      for (var q = 0; q < 64; q++) hot64.push('rgba(' + rgb + ',' + (0.62 + q / 63 * 0.38).toFixed(4) + ')');
    }

    /* ★ README「接后端」那条反向依赖：采样点数由形状面积和字号决定，
       跟记忆条数没关系 —— 真接数据要反过来解。二分字号，直到两个形状
       各自采出的点都刚够放下 n 条记忆。形状只光栅化一次，二分很便宜。 */
    var SHAPES = bakeShapes(opts.shapes);      /* 每个实例可以有自己的一组形状 */
    /* ★ 至少要两片。关系是「一对字符在**两个**剪影里都挨得近」才连的，
         build() 里直接取 p[0] 和 p[1] —— 只给一片时 p[1] 不存在，当场抛。
         只给一片就把它复制一份当第二片：A/B 相同，连线照算，形变没得变而已。
         （0830 加：形状做成可传之后，第一个只传一片的人就会撞上。） */
    if (SHAPES.length === 1) SHAPES = SHAPES.concat(SHAPES);
    var RS = SHAPES.map(function (s) { return raster(s.paint); });
    function countAt(fs) {
      var gap = (fs * 0.62 * 1.06) / 0.62, min = 1e9;
      for (var k = 0; k < RS.length; k++) {
        min = Math.min(min, sample(RS[k], gap, rng(9152026)).length);
      }
      return min;      /* 按最瘦的那个形状解字号 —— 它放不下就都放不下 */
    }
    function solveFS(n) {
      var lo = 0.004, hi = 0.08;          /* 字号越大 → cell 越大 → 点越少 */
      for (var k = 0; k < 22; k++) {
        var mid = (lo + hi) / 2;
        if (countAt(mid) > n) lo = mid; else hi = mid;
      }
      return lo;                           /* 取偏大的那头：宁可点数略多于 n，也别不够 */
    }

    function build() {
      var mem = A_.memories, n = mem.length;
      if (!n || RS.indexOf(null) >= 0) { pair = []; nGlyph = 0; nLink = 0; return; }
      FS = solveFS(n);
      var gap = (FS * 0.62 * 1.06) / 0.62;
      var rand = rng(9152026);
      /* 每个形状各采一遍、各按极角排一遍。所有形状用同一个 M（＝记忆条数），
         按比例映射到各自的极角序上 —— 于是**任意两个形状之间**都是角度配对，
         形变读作转身而不是洗牌，第三片枫叶也一样。 */
      var sets = RS.map(function (R) { return sample(R, gap, rand); });
      if (sets.some(function (s) { return !s.length; })) { pair = []; nGlyph = 0; return; }
      var ords = sets.map(order);
      var M = n;
      for (var si = 0; si < sets.length; si++) M = Math.min(M, sets[si].length);

      pair = [];
      for (var j = 0; j < M; j++) {
        var p = [];
        for (var k = 0; k < sets.length; k++) {
          var q = sets[k][ords[k][(j * sets[k].length / M) | 0]];
          /* z 是一层平的随机薄片，不是穹顶 —— 穹顶会把剪影拱成一段圆弧 */
          p.push([q.x, q.y, (rand() - 0.5) * 0.5]);
        }
        pair.push({
          p: p, cur: null,
          ax: p[0][0], ay: p[0][1],       /* 关系仍在形态 A 的坐标里算一次 */
          bx: p[1][0], by: p[1][1],
          c: CHARS.charAt((rand() * CHARS.length) | 0),
          nf: 0, ph: rand() * Math.PI * 2,
          sp: 0.5 + rand() * 0.85, wob: 0.4 + rand() * 0.8
        });
      }
      nGlyph = pair.length;

      /* 关系建一次，之后云怎么转怎么形变都不重算。一对要在**两个剪影里都近**，
         按 A/B 里更差的那个距离挑，免得在一个形状里齐整的边到另一个形状变成横跨全屏的线。 */
      var dens = A_.linkDensity;
      links = []; leaf = [];
      var hubs = [];
      function rel(i, j) {
        var a = pair[i].p, b = pair[j].p, worst = 0, sum = 0;
        for (var k = 0; k < a.length; k++) {
          var d = Math.hypot(b[k][0] - a[k][0], b[k][1] - a[k][1]);
          if (d > worst) worst = d;
          sum += d;
        }
        /* 原式是两个形状的 max(da,db) + (da+db)*0.18；形状数变了，
           后一项按个数归一化，量纲跟两形状时一致。 */
        return worst + (sum / a.length) * 0.36;
      }
      if (dens > 0) {
        var step = Math.max(2, Math.round(7 / dens));
        for (var i = 0; i < pair.length; i += step) hubs.push(i);
        var seen = {};
        hubs.forEach(function (i) {
          hubs.filter(function (j) { return j !== i; })
            .map(function (j) { return { j: j, d: rel(i, j) }; })
            .sort(function (u, v) { return u.d - v.d; }).slice(0, 3)
            .forEach(function (o) {
              var id = i < o.j ? i * 100000 + o.j : o.j * 100000 + i;
              if (seen[id]) return;
              seen[id] = 1; links.push(i, o.j);
            });
        });
        /* 每个非枢纽连一条到最近的枢纽。这层静止时**完全不画**，
           只有聚焦到它两端之一时才以重点色出现 —— 保证每条记忆的一级关系 ≥ 1，
           否则点到的字符里有三分之二什么都不会亮。 */
        for (var q = 0; q < pair.length; q++) {
          if (q % step === 0) continue;
          var best = -1, bd = 1e9;
          for (var hi2 = 0; hi2 < hubs.length; hi2++) {
            var d2 = rel(q, hubs[hi2]);
            if (d2 < bd) { bd = d2; best = hubs[hi2]; }
          }
          if (best >= 0) leaf.push(q, best);
        }
      }
      nLink = links.length / 2;
      adj = pair.map(function () { return []; });
      for (var k = 0; k < links.length; k += 2) {
        adj[links[k]].push(links[k + 1]); adj[links[k + 1]].push(links[k]);
      }
      for (var k2 = 0; k2 < leaf.length; k2 += 2) {
        adj[leaf[k2]].push(leaf[k2 + 1]); adj[leaf[k2 + 1]].push(leaf[k2]);
      }
      focusAdj = adj.map(function (items, i) {
        var uniq = items.filter(function (v, k3) { return items.indexOf(v) === k3; });
        return uniq.sort(function (a, b) { return rel(i, a) - rel(i, b); }).slice(0, 6);
      });
      px = new Float32Array(pair.length); py = new Float32Array(pair.length);
      pd = new Float32Array(pair.length); pz = new Float32Array(pair.length);
      orderIdx = new Array(pair.length);
    }

    function size() {
      var r = cv.getBoundingClientRect();
      if (!r.width) return;
      dpr = Math.min(1.75, window.devicePixelRatio || 1);
      cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
      w = r.width; h = r.height;
      cv.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    /* 朝屏幕上某个点缩放 —— 居中缩放会把你正瞄着的东西甩出去 */
    function scaleAt(sx, sy, ratio) {
      var before = zoomT, next = Math.max(0.55, Math.min(5, before * ratio)), k = next / before;
      var bx = w * A_.centerX, by = h * A_.centerY;
      panX = (sx - bx) - k * ((sx - bx) - panX);
      panY = (sy - by) - k * ((sy - by) - panY);
      zoomT = next;
    }

    /* 屏幕点 → 最近的那个字符的 index。命中半径 22px。 */
    function pick(sx, sy) {
      if (!px) return -1;
      var best = -1, bd = 22 * 22;
      for (var i = 0; i < px.length; i++) {
        var dx = px[i] - sx, dy = py[i] - sy, d = dx * dx + dy * dy;
        if (d < bd) { bd = d; best = i; }
      }
      return best;
    }

    /* 三个形态循环着切。中途再点一下不能跳 —— 把此刻的插值结果烘成新的起点，
       from 置 -1 表示「起点是 g.cur 这个快照」，接着往下一个形状走。 */
    function toggle() {
      var e = m < 0.5 ? 4 * m * m * m : 1 - Math.pow(-2 * m + 2, 3) / 2;
      for (var i = 0; i < pair.length; i++) {
        var g = pair[i], A = from < 0 ? g.cur : g.p[from], B = g.p[to];
        g.cur = [A[0] + (B[0] - A[0]) * e, A[1] + (B[1] - A[1]) * e, A[2] + (B[2] - A[2]) * e];
      }
      from = -1;
      to = (to + 1) % SHAPES.length;
      m = 0; target = 1;
      S.shape = to;
    }

    function emit(index) {
      var mem = A_.memories;
      var detail = (index === null || index < 0 || !pair.length) ? null : {
        index: index,
        memory: mem[index] || null,
        glyph: pair[index].c,
        relations: (focusAdj[index] || []).map(function (j) {
          return { index: j, memory: mem[j] || null };
        })
      };
      A_.onSelect(detail);
    }
    function selectMemory(i) {
      S.sel = i >= 0 ? i : null;
      if (S.sel === null) { related = null; pullT = 0; }
      emit(S.sel);
    }

    function bind() {
      cv.addEventListener('pointerdown', function (e) {
        pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pts.size === 2) {
          var v = [].slice.call(pts.values());
          pinch = Math.hypot(v[0].x - v[1].x, v[0].y - v[1].y) || 1;
          var rb = cv.getBoundingClientRect();
          mid = [(v[0].x + v[1].x) / 2 - rb.left, (v[0].y + v[1].y) / 2 - rb.top];
          drag = null; return;
        }
        var r0 = cv.getBoundingClientRect();
        /* ★ 选谁在**按下那一刻**就定死，不能等抬手再算：
           手指抬起会滑几个像素，而字符本身一直在飘（±0.009 的正弦漂移），
           两头一凑，抬手那一下很容易命中旁边那个 —— 0827 记下的那个缺陷
           （已经选中的字符会突然跳成另一个）就是这个。 */
        var hit0 = pick(e.clientX - r0.left, e.clientY - r0.top);
        drag = { x: e.clientX, y: e.clientY, startX: e.clientX, startY: e.clientY,
                 viewX: viewXT, viewY: viewYT, moved: 0, hit: hit0 };
        /* 按下去还没动的那一下也要亮，不然手机上得先划一段才有反应 */
        hover = hit0;
        try { cv.setPointerCapture(e.pointerId); } catch (err) {}
        cv.style.cursor = 'grabbing';
      });
      cv.addEventListener('pointermove', function (e) {
        if (pts.has(e.pointerId)) pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (pts.size === 2 && pinch) {
          var v = [].slice.call(pts.values());
          var d = Math.hypot(v[0].x - v[1].x, v[0].y - v[1].y) || 1;
          var r2 = cv.getBoundingClientRect();
          var cxm = (v[0].x + v[1].x) / 2 - r2.left, cym = (v[0].y + v[1].y) / 2 - r2.top;
          scaleAt(cxm, cym, d / pinch);
          /* 两指中点挪了多少，整团就跟着挪多少 —— 放大之后要够得着边角 */
          if (mid) { panX += cxm - mid[0]; panY += cym - mid[1]; }
          mid = [cxm, cym];
          pinch = d; return;
        }
        var r = cv.getBoundingClientRect();
        mx = e.clientX - r.left; my = e.clientY - r.top;
        /* 一千个长一样的字符里，人能瞄准一个像素，但瞄不准一个意思 ——
           所以先无成本地告诉他这是哪一条，点击只负责「留住」。
           ★ 这一句原来关在 `if (!drag)` 里面：鼠标悬停能亮，**手机上亮不了** ——
             手指一按下就进了拖拽分支。可 README 写的是「悬停 / 手指移动」都要亮，
             手机上手指移动本来就同时是拖拽。所以拖着转的时候，手指底下那一片也跟着亮。 */
        hover = pick(mx, my);
        if (!drag) {
          cv.style.cursor = (S.pick && hover >= 0) ? 'pointer' : 'grab';
          return;
        }
        var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        drag.moved += Math.abs(dx) + Math.abs(dy);
        if (e.shiftKey) { panX += dx; panY += dy; }
        else {
          var tx = e.clientX - drag.startX, ty = e.clientY - drag.startY;
          viewXT = Math.max(-0.28, Math.min(0.28, drag.viewX + tx / Math.max(1, w) * 0.82));
          viewYT = Math.max(-0.18, Math.min(0.18, drag.viewY - ty / Math.max(1, h) * 0.82));
        }
        drag.x = e.clientX; drag.y = e.clientY;
      });
      cv.addEventListener('pointerleave', function () { hover = -1; });
      function up(e) {
        pts.delete(e.pointerId);
        if (pts.size < 2) { pinch = null; mid = null; }
        /* 按下到抬起累计位移 < 6px 才算点击，否则算拖拽 */
        if (drag && drag.moved < 6) {
          if (!S.pick) toggle(); else selectMemory(drag.hit);   /* 用按下那一刻定的，见上 */
        }
        drag = null; hover = -1; cv.style.cursor = 'grab';
      }
      cv.addEventListener('pointerup', up);
      cv.addEventListener('pointercancel', function (e) {
        pts.delete(e.pointerId);
        if (pts.size < 2) { pinch = null; mid = null; }
        drag = null; cv.style.cursor = 'grab';
      });
      /* ══ 双指：捏合缩放 ＋ 两指拖动平移 ══════════════════════════════
         ★ 这一段必须走 **Touch Events**，不能用 Pointer Events。前两版我都写错了：
           · `user-scalable=no` —— iOS Safari 从 10 起就故意无视（可访问性）
           · `touch-action: none` —— WebKit 里它只管元素内的滚动/平移，
             **管不着浏览器级的整页双指缩放**
           结果第二根手指的 `pointerdown` 根本没派发到画布，pinch 从头就收不到料。
           而 `touchmove` 里的 `preventDefault()`（passive:false）是真能按住页面缩放的，
           `e.touches` 也一定给全所有手指 —— 这才是 iOS 上唯一靠得住的那条路。
         单指旋转、点击照旧走 pointer；两指一落地就把 pointer 那套掐掉，两边不打架。 */
      function two(t){
        var a = t[0], b = t[1], r = cv.getBoundingClientRect();
        return { d: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) || 1,
                 x: (a.clientX + b.clientX) / 2 - r.left,
                 y: (a.clientY + b.clientY) / 2 - r.top };
      }
      var tp = null;
      cv.addEventListener('touchstart', function (e) {
        if (e.touches.length !== 2) return;
        e.preventDefault();
        drag = null; pts.clear(); pinch = null; mid = null;   /* 掐断单指那一路 */
        tp = two(e.touches);
      }, { passive: false });
      cv.addEventListener('touchmove', function (e) {
        if (e.touches.length < 2 || !tp) return;
        e.preventDefault();
        var n = two(e.touches);
        scaleAt(n.x, n.y, n.d / tp.d);          /* 朝两指中点缩放 */
        panX += n.x - tp.x; panY += n.y - tp.y; /* 中点挪多少，整团跟着挪多少 */
        tp = n;
      }, { passive: false });
      ['touchend', 'touchcancel'].forEach(function (t) {
        cv.addEventListener(t, function (e) { if (e.touches.length < 2) tp = null; });
      });
      /* Safari 私有的 gesture 事件顺手也堵上 —— 有些版本走这条 */
      ['gesturestart', 'gesturechange', 'gestureend'].forEach(function (t) {
        cv.addEventListener(t, function (e) { e.preventDefault(); }, { passive: false });
      });
      cv.addEventListener('wheel', function (e) {
        e.preventDefault();
        var r = cv.getBoundingClientRect();
        scaleAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * 0.0014));
      }, { passive: false });
    }

    function frame(now) {
      if (dead) return;
      raf = requestAnimationFrame(frame);
      var dt = Math.min(64, now - prev); prev = now;
      if (!w || !pair.length) return;
      var ctx = cv.getContext('2d');
      ctx.clearRect(0, 0, w, h);

      zoom += (zoomT - zoom) * Math.min(1, dt / 180);
      var follow = reduceMotion ? 1 : Math.min(1, dt / 70);
      viewX += (viewXT - viewX) * follow;
      viewY += (viewYT - viewY) * follow;
      m += (target - m) * Math.min(1, dt / 520);
      var e = m < 0.5 ? 4 * m * m * m : 1 - Math.pow(-2 * m + 2, 3) / 2;
      var travel = 4 * e * (1 - e);
      var t = (now - t0) / 1000;

      var u = Math.min(w, h), span = u * 0.60 * zoom;
      var cx = w * A_.centerX + panX, cy = h * A_.centerY + panY, F = span * 2.6;
      /* 没有自动旋转 —— 这团东西本质是一张薄片，转过 90° 侧面就没了。
         空闲动效只能是**有界摆动**，不能累加。 */
      var sway = (S.spin && !drag) ? Math.sin(t * 0.25) * 0.14 : 0;
      var vX = viewX + sway, vY = viewY, inflate = A_.depth;

      var P = pair, n = P.length, i;
      pull += (pullT - pull) * Math.min(1, dt / 380);

      function basePos(g, out){
        var SA = from < 0 ? g.cur : g.p[from], SB = g.p[to];
        out[0] = SA[0] + (SB[0] - SA[0]) * e + Math.sin(t * g.sp + g.ph) * 0.009 * g.wob;
        /* 形变中每个字符额外走一条弧线，中途散开最大 */
        out[1] = SA[1] + (SB[1] - SA[1]) * e
               + Math.cos(t * g.sp * 0.9 + g.ph) * 0.009 * g.wob - travel * Math.sin(g.ph) * 0.075;
        out[2] = (SA[2] + (SB[2] - SA[2]) * e) * inflate;
        return out;
      }

      /* 先把选中那条的位置算出来，相关的那几条才知道该朝哪儿飘 */
      var anchor = null;
      if (S.sel !== null && pull > 0.001 && related && related.length) {
        anchor = basePos(P[S.sel], [0, 0, 0]);
      }
      var tmp = [0, 0, 0];

      for (i = 0; i < n; i++) {
        var g = P[i];
        basePos(g, tmp);
        var ux = tmp[0], uy = tmp[1], uz = tmp[2];
        if (anchor && i !== S.sel && related.indexOf(i) >= 0) {
          /* 朝选中那条靠过去，但不重合 —— 留住各自的来向，看得出是「从哪儿过来的」 */
          ux += (anchor[0] - ux) * pull;
          uy += (anchor[1] - uy) * pull;
          uz += (anchor[2] - uz) * pull;
        }
        var x1 = ux + uz * vX * 2.2, y2 = uy - uz * vY * 2.2;
        var d = F / (F - uz * span);
        px[i] = cx + x1 * span * d; py[i] = cy + y2 * span * d;
        pd[i] = d; pz[i] = uz; orderIdx[i] = i;
      }

      var sel = S.sel !== null ? S.sel : (hover >= 0 ? hover : null);
      /* 高亮的那一组是固定的数据关系。投影只改变它们画在哪儿，
         从不改变谁跟谁有关。 */
      /* ★ 亮起来的这一组，优先用后端现算的**语义**邻居；
         没取到（或只是悬停没点）才回落到几何最近邻。
         静止那张网说的是「密度」，这一组说的是「相关」，两回事。 */
      var near1 = (S.sel !== null && related && related.length) ? related
                : ((sel !== null && focusAdj.length) ? focusAdj[sel] : null);

      if (A_.mutate && !reduceMotion) {
        for (i = 0; i < n; i++) {
          var gg = P[i];
          /* ⚠ 0827 一度让「钉住的那条」定住不变形 —— 那是脑补出来的需求：
             当时报的现象是点选之后字符会跳成另一个，真正的病因是 pick 用了抬手坐标（已修），
             不是字形在跳。规格正好相反：**选中的那条跳得最凶**，那是"这条正活着"。
             0827 复核钉死：选中的那个字符自己也要加速变化，不能只有关联的变。改回来了。 */
          var active = (i === sel) || (near1 && near1.indexOf(i) >= 0);
          /* 聚焦要抢在这个字符原来那个慢节奏的到期时间前面，
             否则刚进高亮组的字符会先干等好几秒才开始变 */
          if (active) { gg.c = CHARS.charAt((Math.random() * CHARS.length) | 0); gg.nf = now + 1; continue; }
          if (now <= gg.nf) continue;
          gg.c = CHARS.charAt((Math.random() * CHARS.length) | 0);
          gg.nf = now + 1800 + Math.random() * 6000;
        }
      }

      /* 连线按透明度分 24 桶，每桶一次 beginPath + 一次 stroke。
         被形变拉长的连线淡出：关系不变、布局重排 —— 这正好是记忆库该有的语义。 */
      if (A_.showLinks && links.length) {
        var rest = 0.15, buckets = [];
        for (var k = 0; k < links.length; k += 2) {
          var a = links[k], b = links[k + 1];
          var ddx = px[a] - px[b], ddy = py[a] - py[b];
          var len = Math.hypot(ddx, ddy) / span;
          var stretch = Math.max(0, 1 - Math.max(0, len - rest) / (rest * 2.6));
          var depth = (pz[a] + pz[b]) * 0.5;
          var al = stretch * (0.42 + 0.58 * Math.min(1, Math.max(0, depth + 0.5)));
          if (al < 0.04) continue;
          var lv = Math.min(23, (al * 23) | 0);
          (buckets[lv] || (buckets[lv] = [])).push(a, b);
        }
        ctx.lineWidth = 1;
        for (var lv2 = 0; lv2 < 24; lv2++) {
          var arr = buckets[lv2];
          if (!arr) continue;
          ctx.strokeStyle = line64[lv2];
          ctx.beginPath();
          for (var q2 = 0; q2 < arr.length; q2 += 2) {
            ctx.moveTo(px[arr[q2]], py[arr[q2]]);
            ctx.lineTo(px[arr[q2 + 1]], py[arr[q2 + 1]]);
          }
          ctx.stroke();
        }
      }

      if (sel !== null && near1 && near1.length) {
        ctx.strokeStyle = 'rgba(' + HOT + ',' + (S.light ? 0.5 : 0.88) + ')';
        ctx.lineWidth = S.light ? 1 : 1.5;
        ctx.beginPath();
        for (var b2 = 0; b2 < near1.length; b2++) {
          ctx.moveTo(px[sel], py[sel]);
          ctx.lineTo(px[near1[b2]], py[near1[b2]]);
        }
        ctx.stroke();
      }

      /* 从后往前画；字号量化到 0.25px，让 ctx.font 一帧只改几次而不是一千次 */
      orderIdx.sort(function (a, b) { return pz[a] - pz[b]; });
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      var fsBase = u * FS * zoom, fd = FACES[A_.face] || FACES['细黑'];
      var lastFont = '', lastKey = -1;
      for (var kk = 0; kk < n; kk++) {
        var ii = orderIdx[kk], gl = P[ii], dd = pd[ii];
        var near = Math.max(0, Math.min(1, pz[ii] + 0.5));
        var boost = 0, grow = 1, hotRamp = false;
        if (sel !== null) {
          if (ii === sel) { boost = 0.5; grow = 1.5; hotRamp = true; }
          else if (near1 && near1.indexOf(ii) >= 0) { boost = 0.3; grow = 1.22; hotRamp = true; }
        }
        var fs = Math.round(fsBase * dd * (0.72 + 0.5 * near) * grow * 4) / 4;
        if (fs < 2) continue;
        /* 浅底的覆盖率亏空只在发丝字号上存在，所以字重补偿要跟着字号走，不能是个常数 */
        var f = ((S.light && fs < 11) ? fd.wl : fd.w) + ' ' + fs + 'px ' + fd.fam;
        if (f !== lastFont) { ctx.font = f; lastFont = f; }
        var lv3 = Math.min(63, Math.max(0, (Math.pow(near, 1.15) + boost) * 63 | 0));
        var key = (hotRamp ? 64 : 0) + lv3;
        if (key !== lastKey) { ctx.fillStyle = (hotRamp ? hot64 : ink64)[lv3]; lastKey = key; }
        ctx.fillText(gl.c, px[ii], py[ii]);
      }
    }

    buildInk(); buildHot(); build(); bind();
    ro = new ResizeObserver(size); ro.observe(cv);
    size();
    t0 = performance.now(); prev = t0;
    raf = requestAnimationFrame(frame);
    A_.onReady({ n: nGlyph, links: nLink, fs: FS });

    self.setMemories = function (list) { A_.memories = list || []; S.sel = null; build(); emit(null); };
    self.setLight = function (v) { S.light = !!v; buildInk(); buildHot(); };
    self.setPick = function (v) { S.pick = !!v; S.sel = null; emit(null); };
    self.setWhiteLinks = function (v) { S.whiteLinks = !!v; buildInk(); };
    self.setAccent = function (v) { A_.accent = v; buildHot(); };
    self.setLineColor = function (v) { LINE = hex2rgb(v, '#9184d9'); buildInk(); };
    self.setInk = function (light, dark) {
      LIGHTNODE = hex2rgb(light, '#425262'); DARKNODE = hex2rgb(dark, '#8a94a0'); buildInk();
    };
    self.setFace = function (v) { A_.face = v; };
    self.setSpin = function (v) { S.spin = !!v; };
    self.setCenterY = function (v) { A_.centerY = v; };
    self.setCenterX = function (v) { A_.centerX = v; };
    self.setDepth = function (v) { A_.depth = v; };
    self.setLinkAlpha = function (v) { A_.linkAlpha = v; buildInk(); };
    self.zoomBy = function (r) { scaleAt(w / 2, h / 2, r); };
    self.zoomLevel = function () { return zoomT; };
    self.setRelated = function (idxs) {
      related = (idxs && idxs.length) ? idxs.slice() : null;
      pullT = related ? 0.62 : 0;
    };
    self.select = selectMemory;
    self.toggleShape = toggle;
    self.reset = function () {
      viewX = viewXT = viewY = viewYT = 0; zoomT = 1; panX = panY = 0;
      S.sel = null; emit(null);
      related = null; pullT = 0;
      from = 0; to = 0; m = 1; target = 1;
      for (var i = 0; i < pair.length; i++) pair[i].cur = null;
    };
    self.shapeName = function () { return SHAPES[to].name; };
    self.state = S;
    self.stats = function () { return { n: nGlyph, links: nLink, w: w, h: h, cw: cv.width }; };
    self.resize = size;   /* 外面发现画布尺寸不对时手动量一次 */
    self.destroy = function () { dead = true; cancelAnimationFrame(raf); if (ro) ro.disconnect(); };
    return self;
  }

  global.GlyphCloud = { create: create, CHARS: CHARS, FACES: FACES,
                        DEFAULT_SHAPES: DEFAULT_SHAPES };
})(window);

