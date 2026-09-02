/*!
 * maple-water.js — 枫叶水面待机 / 滑动解锁
 * 本项目纯原创（procedural 手写，零图片资产），随仓库 MIT/AGPL 一起走。
 * Requires p5.js 1.9.x on the page before this file.
 *
 *   const scene = MapleWater(document.getElementById('stage'), {
 *     density: 78, wind: 1.8, ripple: 1.1,
 *     onProgress: v => bar.style.transform = 'scaleX(' + v + ')',
 *     onUnlock:   u => root.classList.toggle('unlocked', u)
 *   });
 *   scene.set({ wind: 3 });   // live
 *   scene.relock();
 *   scene.destroy();
 */
(function (global) {
  'use strict';

  var DIRS = { right: 0.22, left: Math.PI - 0.22, down: Math.PI / 2, up: -Math.PI / 2 };
  var PALETTES = { autumn: 'autumn', crimson: 'crimson', gold: 'gold' }; // see HUES below

  var DEFAULTS = {
    density: 78,          // 0–90   how many leaves float on the surface
    fall: 2.4,            // 0–6    how often a new leaf drops
    ripple: 1.1,          // 0–4    ripple pressure (amplitude of every splash)
    wind: 1.8,            // 0–4    wind speed
    windDirection: 'down',// right | left | down | up
    paper: 3,             // 0–3    washi grain over the whole picture
    palette: 'autumn',    // autumn | crimson | gold
    /* ★ 0810 加的两个性能旋钮。原来这两个数写死在代码里，调不了。
       真机上掉帧 —— 卡的不是配置，是这两处每帧的开销。 */
    grid: 4.2,            // 3.5–7  波场格子的疏密：GW=W/grid。每帧 stepField+renderField
                          //        各走一遍全部格子，所以开销按 grid 的平方掉。
                          //        4.2→6 少一半格子，只让水纹粗一点，叶子和构图一点不动。
                          //        README 自己写的：低端设备第一个该拧的就是它。
    sharp: 1.5,           // 1–2    渲染分辨率上限（pixelDensity）。1.5→1 少 55% 像素填充，
                          //        代价是画面更软 —— 这张图本来就是深景深，未必看得出来。
    band: 8,              // 2–16   河床横带高度。底图是一带一带画的，每带一个常量水平偏移，
                          //        所以画面里有 H/band 条台阶，台阶随时间左右挪 ——
                          //        0810 报的「几行随机左右抽动」就是它。
                          //        调小＝台阶更细更平滑，代价是每帧 drawImage 次数按比例涨。
                          //        ⚠ 只治标：台阶变细，没变没。真解见 sway。
    sway: 'banded',       // banded | whole | off   河床怎么晃
                          //   banded 分层晃：切成 H/band 条横带，下面（近处浅滩）晃幅大、
                          //          上面（远处深水）小，模仿隔着水看底。层次最好，
                          //          **但带与带之间是跳的，抽动就是这么来的**。
                          //   whole  整片晃：整张河床一起左右飘。没有台阶，晃感还在，
                          //          代价是丢掉「下面凶上面稳」那层透视。102 次 drawImage → 1 次。
                          //   off    钉死不动，水的动感全交给波场和浮叶。最省。
    reach: 0.45,          // 0.2–0.9 滑多远算到底（屏幕宽度的几成）。原来写死 0.62，
                          //         0810 实测：那个距离偏长，滑起来不像一个对角。
    onProgress: null,     // (0..1) => void   slide-to-unlock progress
    onUnlock: null        // (bool) => void   fired at 100% and on relock
  };

  function MapleWater(host, options) {
    if (!global.p5) throw new Error('MapleWater: p5.js must be loaded first');
    var o = options || {};
    var cfg = {};
    for (var key in DEFAULTS) if (o[key] !== undefined) cfg[key] = o[key]; else cfg[key] = DEFAULTS[key];
    cfg.style = PALETTES[cfg.palette] || 'autumn';
    cfg.windDir = DIRS[cfg.windDirection] != null ? DIRS[cfg.windDirection] : DIRS.down;

    var self = {
      setProgress: function (v) { if (cfg.onProgress) cfg.onProgress(v); },
      setUnlocked: function (u) { if (cfg.onUnlock) cfg.onUnlock(u); }
    };

    const HALF = [
      [0, 1.00, 0], [13, 0.58, 1], [21, 0.68, 0], [31, 0.31, 1], [45, 0.58, 0],
      [58, 0.90, 0], [72, 0.44, 1], [85, 0.29, 1], [101, 0.53, 0], [118, 0.71, 0],
      [133, 0.35, 1], [151, 0.27, 1], [167, 0.21, 1]
    ];
    // hue window (degrees) each palette samples leaf colour from
  const HUES = { autumn: [2, 50], crimson: [346, 26], gold: [28, 58] };

    function leafPath(ctx, R) {
      const spec = HALF.slice();
      for (let i = HALF.length - 1; i >= 1; i--) spec.push([-HALF[i][0], HALF[i][1], HALF[i][2]]);
      const P = spec.map(function (s) {
        const a = s[0] * Math.PI / 180;
        return [Math.sin(a) * s[1] * R, -Math.cos(a) * s[1] * R];
      });
      ctx.beginPath();
      ctx.moveTo(P[0][0], P[0][1]);
      for (let i = 1; i < P.length; i++) {
        if (spec[i][2]) {
          const cx = (P[i - 1][0] + P[i][0]) / 2 * 1.2, cy = (P[i - 1][1] + P[i][1]) / 2 * 1.2;
          ctx.quadraticCurveTo(cx, cy, P[i][0], P[i][1]);
        } else ctx.lineTo(P[i][0], P[i][1]);
      }
      ctx.closePath();
    }

    const sketch = function (p) {
      let W = 0, H = 0, HZ = 0, PLANE = 1, bottom = null, caus = null, paper = null;
      let pool = [[], [], []], sunk = [[], []], shad = [], floats = [], falls = [];
      let GW = 0, GH = 0, cur = null, prv = null, nxt = null, mask = null, field = null, acc = 0;
      let t = 0, prog = 0, dragging = false, unlocked = false, glow = 0;
      let lx = 0, ly = 0, pvx = 0, pvy = 0, sinceFall = 0, nextFall = 0.6;
      let gust = null, nextGust = 4, windX = 0, windY = 0;
      /* ResizeObserver can fire while p5 is still inside setup().  Before the
         image pools exist, rebuilding the riverbed asks p5 to draw undefined
         leaf images and the whole splash dies on narrow/mobile viewports. */
      let ready = false;
      const SQ = 0.68, LSZ = 122, NLEAF = 16;
      const R2 = function (a, b) { return a + Math.random() * (b - a); };
      const clamp01 = function (v) { return v < 0 ? 0 : v > 1 ? 1 : v; };
      const yOf = function (u) { return HZ + PLANE * Math.pow(u, 1.8); };
      const kOf = function (y) { return 0.15 + 0.85 * Math.pow(clamp01((y - HZ) / PLANE), 0.72); };
      const uOf = function (y) { return Math.pow(clamp01((y - HZ) / PLANE), 1 / 1.8); };
      const tierOf = function (y) { const u = uOf(y); return u > 0.62 ? 0 : u > 0.34 ? 1 : 2; };
      const hazeOf = function (y) { const u = uOf(y); return u > 0.62 ? 255 : u > 0.34 ? 240 : 214; };

      function hueRange() {
        const r = HUES[cfg.style] || HUES.autumn;
        const span = (r[1] - r[0] + 360) % 360;
        return (r[0] + Math.random() * span) % 360;
      }

      function buildLeaf(S) {
        const g = p.createGraphics(S, S);
        const ctx = g.drawingContext;
        const R = S * 0.40;
        const h1 = hueRange();
        const h2 = (h1 + R2(10, 30)) % 360;
        const s1 = R2(78, 94), l1 = R2(44, 56), l2 = R2(58, 70);
        ctx.save();
        ctx.translate(S / 2, S / 2 - S * 0.05);
        const roll = Math.random();
        const stem = roll < 0.34 ? 0 : roll < 0.62 ? R2(0.30, 0.46) : R2(0.50, 0.72);
        if (stem > 0) {
          const bend = R2(-0.30, 0.30) * stem;
          ctx.strokeStyle = 'hsl(' + ((h1 + 350) % 360) + ',' + (s1 * 0.55) + '%,' + (l1 * 0.5) + '%)';
          ctx.lineWidth = R * R2(0.05, 0.075); ctx.lineCap = 'round';
          ctx.beginPath(); ctx.moveTo(0, R * 0.2);
          ctx.quadraticCurveTo(bend * R * 1.5, R * (0.2 + stem) * 0.62, bend * R, R * (0.2 + stem));
          ctx.stroke();
        }
        leafPath(ctx, R);
        const grad = ctx.createLinearGradient(-R * 0.55, -R * 0.95, R * 0.7, R * 0.95);
        grad.addColorStop(0, 'hsl(' + h2 + ',' + Math.min(96, s1 + 4) + '%,' + l2 + '%)');
        grad.addColorStop(0.55, 'hsl(' + h1 + ',' + s1 + '%,' + l1 + '%)');
        grad.addColorStop(1, 'hsl(' + ((h1 + 352) % 360) + ',' + s1 + '%,' + (l1 * 0.78) + '%)');
        ctx.fillStyle = grad; ctx.fill();
        ctx.save(); ctx.clip();
        ctx.fillStyle = 'hsla(' + ((h1 + 348) % 360) + ',68%,30%,0.24)';
        ctx.beginPath();
        ctx.moveTo(-R * 1.6, -R * 0.1); ctx.lineTo(R * 1.6, R * 0.62);
        ctx.lineTo(R * 1.6, R * 1.8); ctx.lineTo(-R * 1.6, R * 1.8); ctx.closePath(); ctx.fill();
        ctx.fillStyle = 'hsla(' + ((h2 + 8) % 360) + ',96%,80%,0.22)';
        ctx.beginPath();
        ctx.moveTo(-R * 1.6, -R * 1.8); ctx.lineTo(R * 1.6, -R * 1.8);
        ctx.lineTo(R * 1.6, -R * 0.82); ctx.lineTo(-R * 1.6, -R * 0.38); ctx.closePath(); ctx.fill();
        ctx.restore();
        ctx.strokeStyle = 'hsla(' + ((h1 + 346) % 360) + ',62%,26%,0.40)';
        ctx.lineWidth = R * 0.032;
        const vein = [[0, 0.80], [58, 0.70], [-58, 0.70], [118, 0.52], [-118, 0.52]];
        for (let i = 0; i < vein.length; i++) {
          const a = vein[i][0] * Math.PI / 180, L = vein[i][1] * R;
          ctx.beginPath(); ctx.moveTo(0, R * 0.18);
          ctx.lineTo(Math.sin(a) * L, -Math.cos(a) * L + R * 0.06); ctx.stroke();
        }
        leafPath(ctx, R);
        ctx.lineWidth = R * 0.034; ctx.lineJoin = 'round';
        ctx.strokeStyle = 'hsla(' + ((h1 + 350) % 360) + ',70%,26%,0.42)';
        ctx.stroke();
        ctx.restore();
        return g;
      }

      function derive(src, filter, overlay, oa) {
        const g = p.createGraphics(src.width, src.height);
        const c = g.drawingContext;
        c.filter = filter;
        g.image(src, 0, 0);
        c.filter = 'none';
        if (oa > 0) {
          c.globalCompositeOperation = 'source-atop';
          c.globalAlpha = oa; c.fillStyle = overlay;
          c.fillRect(0, 0, src.width, src.height);
          c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
        }
        return g;
      }

      function makeImgs() {
        const all = [pool[0], pool[1], pool[2], sunk[0], sunk[1], shad];
        for (let a = 0; a < all.length; a++) for (let i = 0; i < all[a].length; i++) all[a][i].remove();
        pool = [[], [], []]; sunk = [[], []]; shad = [];
        for (let i = 0; i < NLEAF; i++) {
          const s = buildLeaf(190);
          pool[0].push(s);
          pool[1].push(derive(s, 'blur(2.2px)', '', 0));
          pool[2].push(derive(s, 'blur(5px)', '', 0));
          shad.push(derive(s, 'blur(4px) brightness(0)', '', 0));
          sunk[0].push(derive(s, 'hue-rotate(-20deg) saturate(1.32) brightness(0.9)', '#8e2418', 0.14));
          sunk[1].push(derive(s, 'hue-rotate(-28deg) saturate(1.12) brightness(0.82)', '#7a2a24', 0.16));
        }
      }

      // the streambed: a packed carpet at the far end thinning into the pale shallows
      function buildBottom() {
        if (bottom) bottom.remove();
        const sharp = p.createGraphics(W, H);
        const sc = sharp.drawingContext;
        sharp.imageMode(p.CENTER);
        const A = W * H / 1000000;
        // drifts pile up in rafts, so leaves cluster around a scatter of centres rather
        // than spreading evenly, and sizes follow a power law: mostly small, a few huge
        const nCl = Math.round(40 * A) + 20;
        const cl = [];
        // stratified: one cluster per slot across the width and the depth, jittered —
        // random placement kept dropping three rafts on one corner and none on the other
        const cols = Math.max(4, Math.round(Math.sqrt(nCl * (W / H) * 1.6)));
        const rows = Math.max(3, Math.ceil(nCl / cols));
        for (let r = 0; r < rows; r++) {
          for (let c = 0; c < cols; c++) {
            const u = clamp01((r + R2(0.1, 0.9)) / rows);
            const x = (c + R2(0.05, 0.95)) / cols * (W + 80) - 40;
            cl.push([x, yOf(u), R2(0.07, 0.2) * W, u]);
          }
        }
        const nC = cl.length;
        const passes = [
          [0.00, 0.60, Math.round(2000 * A) + 340],
          [0.20, 0.88, Math.round(900 * A) + 180],
          [0.50, 1.00, Math.round(430 * A) + 100],
          [0.00, 1.00, Math.round(820 * A) + 180]
        ];
        for (let q = 0; q < passes.length; q++) {
          const ps = passes[q];
          for (let i = 0; i < ps[2]; i++) {
            let x, u;
            if (Math.random() < 0.55) {
              const c = cl[(Math.random() * nC) | 0];
              if (c[3] < ps[0] || c[3] > ps[1]) continue;
              const r = c[2] * Math.pow(Math.random(), 0.72);
              const a = R2(0, Math.PI * 2);
              x = c[0] + Math.cos(a) * r;
              u = clamp01(c[3] + Math.sin(a) * r * 0.5 / PLANE);
            } else {
              x = R2(-60, W + 60);
              u = R2(ps[0], ps[1]);
            }
            const y = yOf(u) + R2(-3, 3);
            const k = kOf(y);
            const deep = Math.random() < 0.22 - u * 0.14;
            const big = Math.random() < 0.05;
            const sz = LSZ * k * (big ? R2(1.5, 2.3) : 0.32 + Math.pow(Math.random(), 2.3) * 1.5);
            const rot = R2(0, Math.PI * 2);
            const img = (Math.random() * NLEAF) | 0;
            // its own shadow on whatever it fell onto — these stack, so wherever the
            // carpet piles up the layers underneath go dark on their own
            sharp.push();
            sc.globalAlpha = 0.2 + (1 - u) * 0.1;
            sharp.translate(x + sz * 0.05, y + sz * 0.07);
            sharp.scale(1, SQ);
            sharp.rotate(rot);
            sharp.tint(58, 26, 18);
            sharp.image(shad[img], 0, 0, sz * 1.04, sz * 1.04);
            sharp.pop();
            sharp.push();
            sc.globalAlpha = (deep ? R2(0.55, 0.78) : R2(0.82, 1)) * (0.8 + u * 0.2);
            sharp.translate(x, y);
            sharp.scale(1, SQ);
            sharp.rotate(rot);
            sharp.image(sunk[deep ? 1 : 0][img], 0, 0, sz, sz);
            sharp.pop();
          }
        }
        bottom = p.createGraphics(W, H);
        const b1 = yOf(0.34), b2 = yOf(0.62);
        const ctx = bottom.drawingContext;
        const band = function (y0, y1, r) {
          ctx.save();
          ctx.beginPath(); ctx.rect(0, y0, W, y1 - y0); ctx.clip();
          ctx.filter = 'blur(' + r + 'px)';
          bottom.image(sharp, 0, 0, W, H);
          ctx.filter = 'none';
          ctx.restore();
        };
        band(0, b1, 4.5);
        band(b1, b2, 2.4);
        band(b2, H, 1.1);
        sharp.remove();
      }

      // a sheet of washi under the whole picture — warm fibres, mottle and faint laid lines,
      // weighted toward the near shallows where the water goes pale and empty
      function buildPaper() {
        if (paper) paper.remove();
        const g = p.createGraphics(W, H);
        const wgt = function (y) { return 0.3 + 0.7 * Math.pow(clamp01((y - HZ) / PLANE), 1.25); };
        g.strokeCap(p.ROUND);
        const N = Math.round(W * H / 240);
        for (let i = 0; i < N; i++) {
          const x = R2(-12, W + 12), y = R2(-12, H + 12), L = R2(5, 32);
          const a = R2(-0.42, 0.42) + (Math.random() < 0.5 ? 0 : Math.PI);
          const w = wgt(y);
          g.strokeWeight(R2(0.55, 1.5));
          if (Math.random() < 0.66) g.stroke(255, 252, 242, R2(9, 34) * w);
          else g.stroke(112, 76, 54, R2(3, 10) * w);
          g.line(x, y, x + Math.cos(a) * L, y + Math.sin(a) * L);
        }
        g.noStroke();
        const M = Math.round(W * H / 1300);
        for (let i = 0; i < M; i++) {
          const x = R2(0, W), y = R2(0, H), r = R2(9, 46), w = wgt(y);
          if (Math.random() < 0.62) g.fill(255, 251, 238, R2(4, 14) * w);
          else g.fill(134, 100, 74, R2(2, 6) * w);
          g.ellipse(x, y, r, r * R2(0.5, 1));
        }
        const K = Math.round(W * H / 5200);
        for (let i = 0; i < K; i++) {
          const x = R2(0, W), y = R2(0, H), w = wgt(y);
          g.fill(104, 70, 48, R2(6, 20) * w);
          g.ellipse(x, y, R2(0.8, 2.2), R2(0.8, 2.2));
        }
        g.strokeWeight(1);
        for (let y = 0; y < H; y += 5) {
          g.stroke(255, 252, 242, 9.5 * wgt(y));
          g.line(0, y, W, y);
        }
        paper = g;
      }

      function buildCaustics() {
        if (caus) caus.remove();
        const g = p.createGraphics(W, H);
        g.noStroke();
        for (let y = 0; y < H; y += 9) {
          const k = kOf(y);
          for (let x = 0; x < W; x += 9) {
            const v = p.noise(x * 0.008, y * 0.008);
            if (v > 0.60) { g.fill(255, 246, 226, (v - 0.60) * 460); g.ellipse(x, y, 22 * k + 6, (14 * k + 4) * SQ); }
          }
        }
        caus = p.createGraphics(W, H);
        caus.drawingContext.filter = 'blur(7px)';
        caus.image(g, 0, 0);
        caus.drawingContext.filter = 'none';
        g.remove();
      }

      // ——— the wave field: one shared height map, so every ripple meets every other ———
      function buildField() {
        var _g = Math.max(3, Math.min(9, +cfg.grid || 4.2));   /* 0810：提成旋钮，见 DEFAULTS.grid */
        GW = Math.max(32, Math.min(250, Math.round(W / _g)));
        GH = Math.max(32, Math.min(280, Math.round(H / _g)));
        const n = GW * GH;
        cur = new Float32Array(n); prv = new Float32Array(n); nxt = new Float32Array(n);
        mask = new Float32Array(n);
        for (let j = 0; j < GH; j++) {
          for (let i = 0; i < GW; i++) {
            const e = Math.min(i, j, GW - 1 - i, GH - 1 - j);
            mask[j * GW + i] = e >= 7 ? 1 : 0.80 + e * 0.028;
          }
        }
        field = p.createImage(GW, GH);
        field.loadPixels();
      }

      function splash(x, y, amp, radPx) {
        if (!cur) return;
        const gx = x / W * GW, gy = y / H * GH;
        const r = Math.max(1.4, radPx / (W / GW));
        const i0 = Math.max(0, Math.floor(gx - r)), i1 = Math.min(GW - 1, Math.ceil(gx + r));
        const j0 = Math.max(0, Math.floor(gy - r)), j1 = Math.min(GH - 1, Math.ceil(gy + r));
        const a = amp * cfg.ripple;
        for (let j = j0; j <= j1; j++) {
          for (let i = i0; i <= i1; i++) {
            const d = Math.hypot(i - gx, j - gy);
            if (d <= r) cur[j * GW + i] += a * (Math.cos(d / r * Math.PI) * 0.5 + 0.5);
          }
        }
      }

      function stepField() {
        const g = GW, n = GW * GH;
        for (let j = 1; j < GH - 1; j++) {
          const o = j * g;
          for (let i = 1; i < g - 1; i++) {
            const k = o + i;
            let v = (cur[k - 1] + cur[k + 1] + cur[k - g] + cur[k + g]) * 0.5 - prv[k];
            v *= 0.9805;
            nxt[k] = v * mask[k];
          }
        }
        for (let i = 0; i < g; i++) { nxt[i] = 0; nxt[n - g + i] = 0; }
        for (let j = 0; j < GH; j++) { nxt[j * g] = 0; nxt[j * g + g - 1] = 0; }
        const tmp = prv; prv = cur; cur = nxt; nxt = tmp;
      }

      function heightAt(x, y) {
        const i = Math.round(x / W * GW), j = Math.round(y / H * GH);
        if (i < 1 || j < 1 || i > GW - 2 || j > GH - 2) return 0;
        return cur[j * GW + i];
      }
      function gradAt(x, y, out) {
        const i = Math.round(x / W * GW), j = Math.round(y / H * GH);
        if (i < 1 || j < 1 || i > GW - 2 || j > GH - 2) { out[0] = 0; out[1] = 0; return; }
        const k = j * GW + i;
        out[0] = cur[k + 1] - cur[k - 1];
        out[1] = cur[k + GW] - cur[k - GW];
      }

      function renderField() {
        const px = field.pixels, gain = 330;
        for (let j = 0; j < GH; j++) {
          const o = j * GW;
          for (let i = 0; i < GW; i++) {
            const k = o + i, q = k * 4;
            const l = i > 0 ? cur[k - 1] : cur[k], r = i < GW - 1 ? cur[k + 1] : cur[k];
            const u = j > 0 ? cur[k - GW] : cur[k], d = j < GH - 1 ? cur[k + GW] : cur[k];
            const s = (r - l) * 0.66 + (d - u) * 0.44;
            if (s > 0) {
              px[q] = 255; px[q + 1] = 253; px[q + 2] = 246;
              px[q + 3] = Math.min(150, s * gain * 0.8);
            } else {
              px[q] = 126; px[q + 1] = 88; px[q + 2] = 56;
              px[q + 3] = Math.min(160, -s * gain * 0.95);
            }
          }
        }
        field.updatePixels();
      }

      function newFloat(x, y, vx, vy, ix, sz) {
        return {
          x: x, y: y, vx: vx || 0, vy: vy || 0,
          ix: ix != null ? ix : (Math.random() * NLEAF) | 0,
          rot: R2(0, Math.PI * 2), vr: R2(-0.003, 0.003),
          sz: sz || R2(0.58, 0.96), bob: R2(0, 6.28), bAge: 9, wait: 0, drift: 0
        };
      }
      function seedFloats() {
        floats = [];
        const n = Math.round(cfg.density);
        for (let i = 0; i < n; i++) floats.push(newFloat(R2(10, W - 10), yOf(Math.random())));
      }

      p.setup = function () {
        const r = host.getBoundingClientRect();
        W = Math.max(240, r.width | 0); H = Math.max(320, r.height | 0);
        HZ = H * 0.035; PLANE = H - HZ;
        const c = p.createCanvas(W, H);
        c.elt.style.display = 'block'; c.elt.style.width = '100%'; c.elt.style.height = '100%';
        /* 0810：上限提成旋钮（原来写死 1.5）。见 DEFAULTS.sharp。 */
        p.pixelDensity(Math.min(Math.max(1, Math.min(2, +cfg.sharp || 1.5)), window.devicePixelRatio || 1));
        p.imageMode(p.CENTER);
        p.noiseSeed(7);
        makeImgs(); buildBottom(); buildCaustics(); buildPaper(); buildField(); seedFloats();
        self.rebuildLeaves = function () { makeImgs(); buildBottom(); };
        self.syncDensity = function () {
          const n = Math.round(cfg.density);
          while (floats.length > n) floats.pop();
          while (floats.length < n) floats.push(newFloat(R2(10, W - 10), yOf(Math.random())));
        };
        self.relockSketch = function () {
          unlocked = false; prog = 0; glow = 0;
          seedFloats(); falls = [];
          cur.fill(0); prv.fill(0);
          self.setProgress(0); self.setUnlocked(false);
        };
        /* 0810 加的唯一一处：把 doUnlock 接出去。
           连环的门用口令进，不用滑动解锁 —— 口令对了的那一下才放这朵大水花。
           内部逻辑一个字没动，只是让外面调得到。 */
        self.unlockAt = doUnlock;
        bindPointer();
        ready = true;
      };

      p.windowResized = function () {
        if (!ready) return;
        const r = host.getBoundingClientRect();
        const nw = Math.max(240, r.width | 0), nh = Math.max(320, r.height | 0);
        if (nw === W && nh === H) return;
        W = nw; H = nh; HZ = H * 0.035; PLANE = H - HZ;
        p.resizeCanvas(W, H); buildBottom(); buildCaustics(); buildPaper(); buildField();
      };

      function bindPointer() {
        const loc = function (e) {
          const r = host.getBoundingClientRect();
          return [e.clientX - r.left, e.clientY - r.top];
        };
        host.addEventListener('pointerdown', function (e) {
          try { host.setPointerCapture(e.pointerId); } catch (err) {}
          const q = loc(e); lx = q[0]; ly = q[1]; dragging = true; pvx = 0; pvy = 0;
          splash(lx, ly, 1.5, 15);
          host.style.cursor = 'grabbing';
        });
        host.addEventListener('pointermove', function (e) {
          const q = loc(e), x = q[0], y = q[1];
          if (dragging) {
            const dx = x - lx, dy = y - ly;
            pvx = dx; pvy = dy;
            if (!unlocked && Math.abs(dx) > Math.abs(dy) * 0.5) {
              /* 0810：滑多远算到底，提成 reach 旋钮（原来写死 0.62，实测太远） */
              prog = Math.max(0, Math.min(1, prog + dx / (W * Math.max(0.2, Math.min(0.9, +cfg.reach || 0.45)))));
              self.setProgress(prog);
              if (prog >= 0.995) doUnlock(x, y);
            }
            const sp = Math.hypot(dx, dy);
            if (sp > 4) splash(x, y, Math.min(0.85, 0.16 + sp * 0.04), 12);
          }
          lx = x; ly = y;
        });
        const up = function () {
          if (!dragging) return;
          dragging = false; pvx = 0; pvy = 0; host.style.cursor = 'grab';
        };
        host.addEventListener('pointerup', up);
        host.addEventListener('pointercancel', up);
        host.addEventListener('pointerleave', up);
      }

      function doUnlock(x, y) {
        unlocked = true;
        self.setUnlocked(true);
        splash(x, y, 6, 40);
        for (let i = 0; i < floats.length; i++) {
          const f = floats[i];
          const a = Math.atan2((f.y - y) * 0.5, f.x - x) + R2(-0.5, 0.5);
          const k = R2(3.2, 6.4);
          f.vx += Math.cos(a) * k; f.vy += Math.sin(a) * k * 0.6; f.vr += R2(-0.05, 0.05);
        }
      }

      function rowWarp(j) {
        let s = 0;
        const o = j * GW, step = 5;
        for (let i = 2; i < GW - 2; i += step) s += cur[o + i + 1] - cur[o + i - 1];
        return s / Math.max(1, (GW - 4) / step);
      }

      function water() {
        const ctx = p.drawingContext;
        const g = ctx.createLinearGradient(0, 0, W * 0.22, H);
        g.addColorStop(0, '#dcc596');
        g.addColorStop(0.22, '#e7d5b0');
        g.addColorStop(0.52, '#f0e3c8');
        g.addColorStop(0.78, '#f5ecd8');
        g.addColorStop(1, '#faf4e6');
        ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
        const hz = ctx.createLinearGradient(0, 0, 0, HZ + PLANE * 0.30);
        hz.addColorStop(0, 'rgba(255,250,236,' + (0.12 + glow * 0.16).toFixed(3) + ')');
        hz.addColorStop(1, 'rgba(255,250,236,0)');
        ctx.fillStyle = hz; ctx.fillRect(0, 0, W, HZ + PLANE * 0.30);
        const rg = ctx.createRadialGradient(W * 0.3, HZ + PLANE * 0.12, 0, W * 0.3, HZ + PLANE * 0.12, Math.max(W, H) * 0.85);
        rg.addColorStop(0, 'rgba(255,248,226,' + (0.12 + glow * 0.2).toFixed(3) + ')');
        rg.addColorStop(1, 'rgba(255,248,226,0)');
        ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
      }

      function drawFloat(f) {
        const k = kOf(f.y), tier = tierOf(f.y), hz = hazeOf(f.y);
        const img = pool[tier][f.ix];
        const b = f.bAge < 1.4 ? Math.sin(f.bAge * 10.5) * Math.exp(-f.bAge * 4.2) : 0;
        const ride = heightAt(f.x, f.y) * 3.2;
        const S = LSZ * f.sz * k * (1 + Math.sin(t * 1.5 + f.bob) * 0.03 + b * 0.075);
        const y = f.y + ride - b * 2.4 * k;
        p.push();
        p.translate(f.x + 3 * k, y + 5 * k);
        p.scale(1, SQ); p.rotate(f.rot);
        p.tint(70, 46, 40, 70);
        p.image(img, 0, 0, S, S);
        p.pop();
        p.push();
        p.translate(f.x, y);
        p.scale(1, SQ); p.rotate(f.rot);
        p.tint(255, 255, 255, hz);
        p.image(img, 0, 0, S, S);
        p.pop();
        p.noTint();
      }

      function drawFall(f) {
        const k = kOf(f.ly), tier = tierOf(f.ly), hz = hazeOf(f.ly);
        const img = pool[tier][f.ix];
        const land = LSZ * f.sz * k;
        const S = land * (1 + f.h * 0.9);
        const flip = Math.cos(t * f.flip + f.fph);
        const sq = Math.max(0.16, Math.abs(flip));
        const fade = Math.min(1, (1 - f.h) * 7);
        const sway = Math.sin(t * f.sway + f.ph) * f.amp * f.h;
        p.push();
        p.translate(f.lx + sway * 0.55 + Math.sin(t * 2.6 + f.ph) * 3, f.ly + f.h * f.fallH * 0.5);
        p.scale(1, -SQ * 0.92); p.rotate(f.rot); p.scale(sq, 1);
        p.tint(255, 244, 232, fade * (26 + (1 - f.h) * 46));
        p.image(pool[2][f.ix], 0, 0, S * 0.94, S * 0.94);
        p.pop();
        if (f.h < 0.62) {
          const a = 1 - f.h / 0.62;
          p.push();
          p.translate(f.lx, f.ly);
          p.scale(1, SQ); p.rotate(f.rot); p.scale(sq, 1);
          p.tint(62, 40, 34, 18 + a * 66);
          p.image(img, 0, 0, land * (0.62 + a * 0.38), land * (0.62 + a * 0.38));
          p.pop();
        }
        p.push();
        p.translate(f.lx + sway, f.ly - f.h * f.fallH);
        p.rotate(f.rot); p.scale(sq, 1);
        p.tint(255, 255, 255, fade * hz);
        p.image(img, 0, 0, S, S);
        const gl = Math.pow(Math.max(0, flip), 10);
        if (gl > 0.02) {
          p.blendMode(p.SCREEN);
          p.tint(255, 240, 208, gl * 120 * fade);
          p.image(img, 0, 0, S, S);
          p.blendMode(p.BLEND);
        }
        p.pop();
        p.noTint();
      }

      const G = [0, 0];

      p.draw = function () {
        const dt = Math.min(0.05, p.deltaTime / 1000);
        const st = dt * 60;
        t += dt;
        if (unlocked) glow = Math.min(1, glow + dt * 0.9);

        acc += dt;
        let steps = 0;
        while (acc >= 0.0166 && steps < 3) { stepField(); acc -= 0.0166; steps++; }
        if (steps === 3) acc = 0;

        nextGust -= dt;
        if (!gust && nextGust <= 0) {
          // one prevailing direction downstream — gusts change how hard it blows, not where
          gust = { a: cfg.windDir + R2(-0.16, 0.16), k: R2(0.5, 1.15), age: 0, dur: R2(1.6, 3.2) };
          nextGust = R2(3, 7);
        }
        if (gust) {
          gust.age += dt;
          const e = Math.sin(Math.PI * Math.min(1, gust.age / gust.dur));
          const s = gust.k * e * cfg.wind;
          windX = Math.cos(gust.a) * s; windY = Math.sin(gust.a) * s * 0.5;
          if (Math.random() < e * 0.7) splash(R2(0, W), yOf(Math.random()), 0.2 * e, R2(7, 15));
          if (gust.age > gust.dur) gust = null;
        } else {
          // never fully still: a steady breath in the prevailing direction
          const base = 0.16 * cfg.wind;
          windX += (Math.cos(cfg.windDir) * base - windX) * Math.min(1, dt * 2);
          windY += (Math.sin(cfg.windDir) * base * 0.5 - windY) * Math.min(1, dt * 2);
        }

        if (!dragging && !unlocked && prog > 0) {
          prog = Math.max(0, prog - dt * 1.7);
          self.setProgress(prog);
        }

        water();

        /* ── 河床怎么晃（0810 提成 sway 旋钮）──
           原来只有 banded 一种：切成横带、每带一个常量偏移，带与带之间是跳的，
           这就是那个「几行随机左右抽动」。band 调小只是把台阶变细，治标不治本。 */
        const SWAY = (cfg.sway === 'whole' || cfg.sway === 'off') ? cfg.sway : 'banded';
        p.imageMode(p.CORNER);
        // gentle standing wobble only — driving this from the wave field slid whole
        // rows sideways whenever a leaf landed, which read as the screen lurching
        if (SWAY === 'off') {
          p.image(bottom, 0, 0, W, H);                       /* 钉死。1 次 drawImage，最省 */
        } else if (SWAY === 'whole') {
          /* 整张一起飘：没有带，就没有台阶。丢掉的是 kOf(y) 那层「近处浅滩晃得凶、
             远处深水稳」的透视 —— 而那层正是台阶的来源，二选一。 */
          const amb = (Math.sin(t * 1.15) * 1.1 + Math.sin(-t * 0.62) * 1.6 + windX * 2.4) * 0.9;
          p.image(bottom, amb, 0, W, H);
        } else {
          const SH = Math.max(2, Math.min(16, Math.round(+cfg.band || 8)));
          for (let y = 0; y < H; y += SH) {
            const amb = (Math.sin(y * 0.021 + t * 1.15) * 1.1 + Math.sin(y * 0.0085 - t * 0.62) * 1.6 + windX * 2.4) * (0.3 + kOf(y));
            p.image(bottom, amb, y, W, SH, 0, y, W, SH);
          }
        }

        p.push();
        p.blendMode(p.SCREEN);
        p.tint(255, 255, 255, 13 + glow * 14);
        p.image(caus, ((t * 5) % W) - W, Math.sin(t * 0.2) * 12, W, H);
        p.image(caus, (t * 5) % W, Math.sin(t * 0.2) * 12, W, H);
        p.pop();

        renderField();
        p.image(field, 0, 0, W, H);
        p.imageMode(p.CENTER);
        p.noTint();

        for (let i = floats.length - 1; i >= 0; i--) {
          const f = floats[i];
          const k = kOf(f.y);
          f.bAge += dt;
          if (f.wait > 0) { f.wait -= dt; if (f.wait <= 0) splash(f.x, f.y, 0.55 + k * 0.5, 4 + k * 5); }
          const n = p.noise(f.x * 0.0022, f.y * 0.0022, t * 0.05) * 12.566;
          f.vx += Math.cos(n) * 0.0032 + windX * 0.062;
          f.vy += Math.sin(n) * 0.0022 + windY * 0.062;
          gradAt(f.x, f.y, G);
          // a leaf that just touched down must not be launched by its own splash
          const fg = Math.min(1, f.bAge / 0.9);
          const gx = Math.max(-0.3, Math.min(0.3, G[0])), gy = Math.max(-0.3, Math.min(0.3, G[1]));
          // a big leaf carries more water with it: every push divides by its mass
          const im = 1 / (f.sz * f.sz);
          f.vx -= gx * 4.2 * fg * im;
          f.vy -= gy * 2.4 * fg * im;
          f.vr += gx * 0.035 * fg * im;
          if (dragging) {
            const dx = f.x - lx, dy = (f.y - ly) / 0.62;
            const d = Math.hypot(dx, dy);
            if (d < 130) {
              const kk = (1 - d / 130) * (Math.min(28, Math.hypot(pvx, pvy)) * 0.055 + 0.14);
              const ang = Math.atan2(dy, dx);
              f.vx += Math.cos(ang) * kk * 0.7 + pvx * 0.02 * (1 - d / 130);
              f.vy += (Math.sin(ang) * kk * 0.7 + pvy * 0.02 * (1 - d / 130)) * 0.55;
              f.vr += (pvx / 240) * (1 - d / 130);
            }
          }
          if (f.drift) f.vy += 0.03;
          f.vx *= Math.pow(0.947, st); f.vy *= Math.pow(0.947, st);
          const cap = 3.4 / f.sz;
          const spd = Math.hypot(f.vx, f.vy);
          if (spd > cap) { const q = cap / spd; f.vx *= q; f.vy *= q; }
          f.x += f.vx * st * k; f.y += f.vy * st * k * 0.62;
          f.rot += (f.vr + f.vx * 0.0016) * st; f.vr *= Math.pow(0.955, st);

          const off = 40 + LSZ * f.sz * k * 0.6;
          if (f.x < -off || f.x > W + off || f.y > H + off || f.y < HZ - 6) {
            floats.splice(i, 1);
            if (!unlocked && floats.length < cfg.density) {
              floats.push(newFloat(R2(20, W - 20), yOf(Math.random() * 0.12)));
            }
          }
        }

        sinceFall += dt;
        const rate = nextFall / Math.max(0.15, cfg.fall * (1 + (gust ? 0.9 : 0)));
        if (sinceFall > rate && falls.length < 10) {
          sinceFall = 0; nextFall = R2(0.5, 1.6);
          const u = Math.pow(Math.random(), 0.7);
          const yl = yOf(u), k = kOf(yl);
          falls.push({
            lx: R2(-40, W + 40), ly: yl, h: 1, vh: R2(0.15, 0.24),
            fallH: (yl - HZ + 140) * R2(1.0, 1.35),
            sway: R2(0.7, 1.6), ph: R2(0, 6.28), amp: R2(20, 60) * k,
            flip: R2(1.0, 2.1), fph: R2(0, 6.28),
            rot: R2(0, 6.28), vr: R2(-1.0, 1.0), sz: R2(0.62, 0.94),
            ix: (Math.random() * NLEAF) | 0
          });
        }
        for (let i = falls.length - 1; i >= 0; i--) {
          const f = falls[i];
          f.h -= f.vh * dt;
          f.rot += f.vr * dt;
          f.lx += windX * 0.5 * st * f.h;
          if (f.h <= 0) {
            falls.splice(i, 1);
            // lands where it was headed: a splash and a bounce, no drift
            // settles first, then the water answers
            const nf = newFloat(f.lx, f.ly, R2(-0.1, 0.1), R2(-0.04, 0.04), f.ix, f.sz);
            nf.rot = f.rot; nf.vr = R2(-0.005, 0.005); nf.bAge = 0; nf.wait = 0.13;
            floats.push(nf);
            // never pop a leaf out of existence — the oldest one is just let go
            // downstream, drifting off the near edge over half a minute
            if (floats.length > cfg.density + 10) {
              for (let q = 0; q < floats.length; q++) {
                if (!floats[q].drift) { floats[q].drift = 1; break; }
              }
            }
          }
        }

        // leaves crowd rather than collide: they overlap-resolve softly, share momentum
        // by mass, and lose most of it to the water instead of bouncing apart
        for (let a = 0; a < floats.length; a++) {
          const A = floats[a];
          const ka = kOf(A.y), ra = LSZ * A.sz * ka * 0.30;
          for (let b = a + 1; b < floats.length; b++) {
            const B = floats[b];
            const kb = kOf(B.y), rb = LSZ * B.sz * kb * 0.30;
            const rr = ra + rb;
            let dx = B.x - A.x, dy = (B.y - A.y) / SQ;
            const d2 = dx * dx + dy * dy;
            if (d2 > rr * rr || d2 < 1e-4) continue;
            const d = Math.sqrt(d2);
            const nx = dx / d, ny = dy / d;
            const ma = A.sz * A.sz, mb = B.sz * B.sz, mt = ma + mb;
            const push = (rr - d) * 0.16;
            A.x -= nx * push * (mb / mt); A.y -= ny * push * SQ * (mb / mt);
            B.x += nx * push * (ma / mt); B.y += ny * push * SQ * (ma / mt);
            const rel = (B.vx - A.vx) * nx + (B.vy - A.vy) * ny;
            if (rel < 0) {
              const j = -rel * 0.22;
              A.vx -= nx * j * (mb / mt); A.vy -= ny * j * SQ * (mb / mt);
              B.vx += nx * j * (ma / mt); B.vy += ny * j * SQ * (ma / mt);
              A.vr -= ny * j * 0.004; B.vr += ny * j * 0.004;
            }
          }
        }

        const list = [];
        for (let i = 0; i < floats.length; i++) list.push([floats[i].y, 0, floats[i]]);
        for (let i = 0; i < falls.length; i++) list.push([falls[i].ly, 1, falls[i]]);
        list.sort(function (a, b) { return a[0] - b[0]; });
        for (let i = 0; i < list.length; i++) {
          if (list[i][1]) drawFall(list[i][2]); else drawFloat(list[i][2]);
        }

        const ctx = p.drawingContext;
        ctx.save();
        ctx.globalCompositeOperation = 'screen';
        const sg = ctx.createLinearGradient(0, HZ + PLANE * 0.1 + Math.sin(t * 0.35) * 22, W, HZ + PLANE * 0.5);
        sg.addColorStop(0, 'rgba(255,244,222,0)');
        sg.addColorStop(0.5, 'rgba(255,244,222,' + (0.03 + glow * 0.05).toFixed(3) + ')');
        sg.addColorStop(1, 'rgba(255,244,222,0)');
        ctx.fillStyle = sg; ctx.fillRect(0, 0, W, H);
        ctx.restore();

        if (cfg.paper > 0.01) {
          p.imageMode(p.CORNER);
          p.tint(255, 255, 255, Math.min(255, 170 * cfg.paper));
          p.image(paper, 0, 0, W, H);
          if (cfg.paper > 1.5) {
            p.tint(255, 255, 255, Math.min(255, (cfg.paper - 1.5) * 160));
            p.image(paper, 0, 0, W, H);
          }
          p.noTint();
          p.imageMode(p.CENTER);
        }
      };
    };

    var p5i = new global.p5(sketch, host);
    var ro = null;
    if (global.ResizeObserver) {
      ro = new global.ResizeObserver(function () { if (p5i && p5i.windowResized) p5i.windowResized(); });
      ro.observe(host);
    }

    return {
      p5: p5i,
      config: cfg,
      /** Live-patch any option. density/palette rebuild lazily; the rest apply next frame. */
      set: function (patch) {
        for (var k in patch) {
          if (k === 'windDirection') cfg.windDir = DIRS[patch[k]] != null ? DIRS[patch[k]] : cfg.windDir;
          else if (k === 'palette') cfg.style = PALETTES[patch[k]] || cfg.style;
          cfg[k] = patch[k];
        }
        if (patch.palette !== undefined && self.rebuildLeaves) self.rebuildLeaves();
        if (patch.density !== undefined && self.syncDensity) self.syncDensity();
        return this;
      },
      relock: function () { if (self.relockSketch) self.relockSketch(); return this; },
      /** 0810 加：在 (x,y) 处放那朵解锁大水花（amp 6 / r 40）并把所有浮叶向外甩开。
          不给坐标就落在画面中央偏下 —— 口令框大致在那儿。 */
      unlock: function (x, y) {
        if (!self.unlockAt) return this;
        var el = host, w = el ? el.clientWidth : 0, h = el ? el.clientHeight : 0;
        self.unlockAt(x == null ? w * 0.5 : x, y == null ? h * 0.62 : y);
        return this;
      },
      destroy: function () {
        if (ro) ro.disconnect();
        try { p5i.remove(); } catch (e) {}
      }
    };
  }

  MapleWater.DEFAULTS = DEFAULTS;
  global.MapleWater = MapleWater;
  if (typeof module === 'object' && module.exports) module.exports = MapleWater;
})(typeof window !== 'undefined' ? window : this);
