/*!
 * thread.js —— 通话时的那条线。
 * ════════════════════════════════════════════════════════════════
 * 一句话：**线是一条线。谁在说，线就往谁那头写；他在想的时候，
 * 线在他那头一笔写出一片叶子。**
 *
 *   var t = Thread(canvas, { leaf: Crest.def('maple') });
 *   t.setPhase('listening');   // 相位：谁在说、在不在想
 *   t.setLevel(0.6);           // 有真音量就喂进来；不喂就用一条合成包络
 *
 * 相位：idle / connecting / incoming / ringing / listening / thinking / speaking / ended
 *
 * ★ 两个人的声音在线上**长得不一样**，这个区别本身就是「现在轮到谁」：
 *   一头是连着的一道涌（合成的声音是连续的），另一头是线上面一串小齿
 *   （识别是一颗一颗字回来的）。
 *
 * ★ 「在想」那一段：一支笔从左往右写这根线，编好一片叶子就落回水平线，
 *   往右走一段再编下一片。**笔走到哪儿＝想了多久**（第一片约 1 秒，第三片约 5 秒）。
 *   一开口，尾巴追着头 0.34 秒把线拆干净。
 *
 * 零依赖。不碰麦克风、不发请求 —— 音量由宿主喂进来，要不要开麦是宿主的事。
 * prefers-reduced-motion 下自动降成一条安静的线。
 */
(function (global) {
  'use strict';

  /* 线的长度：头尾差这么多之后尾巴才开始拆（笔头快到右头了，左边才动）。
     ★ 700 是原项目 call.html:419 的原值。0830 重写时写成了 150 ——
       尾巴紧追笔头，屏上只剩短短一截，「一支笔在写」那个感觉整个没了。
       0902 改回原值：**这个数不许再动**。 */
  var TRAIL = 700;

  function Thread(canvas, opts) {
    if (!canvas || !canvas.getContext) return null;
    opts = opts || {};
    var g = canvas.getContext('2d');
    var reduce = false;
    try { reduce = matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) {}

    var st = { phase: 'idle' };
    var level = 0, ext = -1, extAt = 0, prevLevel = 0, lastT = 0, sylAt = 0, ringAt = 0;
    var packets = [], thinkAt = 0, unwindAt = 0, pen = 0, penHold = null;
    var tailHold = 0, tailForce = null, penTotal = 0, leafPts = null, alive = true, raf = 0;
    var tok = { ink: '#2b2724', thread: '#ddd2c6', maple: '#b5533a' };

    function readTokens() {
      var cs = getComputedStyle(document.documentElement);
      var q = function (n) { return cs.getPropertyValue(n).trim(); };
      tok.ink = q('--ink') || tok.ink;
      tok.thread = q('--thread') || tok.thread;
      tok.maple = q('--maple') || q('--accent') || tok.maple;
    }

    /* 把叶子的 path 采成一串点。★ 柄留着 —— 没叶梗像鸡爪。
       整片轮廓从柄脚左角绕到右角，柄脚两边各留一道缝（见下面的 leg()）。 */
    function takeLeaf() {
      if (leafPts) return;
      var def = opts.leaf || (global.Crest && global.Crest.def && global.Crest.def('maple'));
      if (!def || !def.path) return;
      var ns = 'http://www.w3.org/2000/svg';
      var svg = document.createElementNS(ns, 'svg');
      svg.setAttribute('viewBox', def.viewBox || '0 0 384 512');
      svg.style.cssText = 'position:absolute;width:0;height:0;opacity:0;pointer-events:none';
      var el = document.createElementNS(ns, 'path');
      el.setAttribute('d', def.path);
      if (def.transform) el.setAttribute('transform', def.transform);
      svg.appendChild(el);
      document.body.appendChild(svg);
      var L = 0;
      try { L = el.getTotalLength(); } catch (e) {}
      if (!L) { svg.remove(); return; }
      var M = 240, raw = [], i;
      for (i = 0; i < M; i++) { var q = el.getPointAtLength(L * i / M); raw.push({ x: q.x, y: q.y }); }
      svg.remove();

      /* 叶柄留着（没叶梗像鸡爪）。整片轮廓从柄脚左角绕到右角，柄脚两边各留一道缝（见 leg()）。
         ★ 锚点 (241,512)/(271,512) 是这片枫叶自己的柄脚坐标（512 viewBox）——
           跟 call.html:633-637 一字不差，别改。
         ⚠ 0902 的跤：家徽那儿一度放的是 FA 的另一个 384×512 变体，柄脚在 208.6..238.6，
           这两个锚点就落到同一个采样点上，walk() 只取回 1 个点 —— 叶子一片都写不出来。
           病根不在这段算法，在「同一片枫叶留了两份 path」。现在全仓库只有一份
           （blocks/base/crest.js，＝家里 call.html 的 #crest ＝ 字云的 D_MAPLE）。 */
      var iL = 0, iR = 0, dL = 1e9, dR = 1e9;
      raw.forEach(function (q, k) {
        var a = (q.x - 241) * (q.x - 241) + (q.y - 512) * (q.y - 512); if (a < dL) { dL = a; iL = k; }
        var b = (q.x - 271) * (q.x - 271) + (q.y - 512) * (q.y - 512); if (b < dR) { dR = b; iR = k; }
      });
      var walk = function (dir) {
        var o = [];
        for (var k = iL; o.length <= M; k = (k + dir + M) % M) { o.push(raw[k]); if (k === iR) break; }
        return o;
      };
      var a2 = walk(1), b2 = walk(-1), run = (a2.length >= b2.length ? a2 : b2);
      if (run.length > 1 && run[0].x > run[run.length - 1].x) run.reverse();
      leafPts = run;
    }

    function fit() {
      var r = Math.min(global.devicePixelRatio || 1, 2);
      var w = canvas.clientWidth, h = canvas.clientHeight;
      if (!w || !h) return;
      canvas.width = w * r; canvas.height = h * r;
      canvas.getContext('2d').setTransform(r, 0, 0, r, 0, 0);
    }

    /* 没人喂音量时用一条合成包络 —— 线在浏览器里也是活的 */
    function reading(now) {
      if (ext >= 0 && now - extAt < 400) return ext;
      var p = st.phase;
      if (p !== 'listening' && p !== 'speaking') return 0;
      var t = now / 1000, sp = p === 'speaking' ? 1 : 0.82;
      var syl = Math.abs(Math.sin(t * 4.1 * sp)) * (0.55 + 0.45 * Math.sin(t * 1.13 + (p === 'speaking' ? 0 : 2.2)));
      var gate = 0.5 + 0.5 * Math.sin(t * 0.61 + 1.7);
      return Math.max(0, Math.min(1, 0.16 + syl * 0.62 * gate));
    }

    function loop(now) {
      if (!alive) return;
      raf = requestAnimationFrame(loop);
      var dt = Math.min(0.05, lastT ? (now - lastT) / 1000 : 0.016); lastT = now;
      level += (reading(now) - level) * (reduce ? 1 : 0.2);

      var w = canvas.clientWidth, h = canvas.clientHeight; if (!w || !h) return;
      g.clearRect(0, 0, w, h);
      var p = st.phase, t = reduce ? 0 : now / 1000, y0 = h * 0.58;
      var side = p === 'speaking' || p === 'incoming' ? 0 : p === 'listening' || p === 'ringing' ? 1 : -1;
      var sag = p === 'thinking' ? 3.4 : p === 'connecting' ? 1.6 : 0;

      var leaves = [];
      if (thinkAt && !leafPts) takeLeaf();
      if (thinkAt && leafPts) {
        var k = unwindAt ? Math.max(0, 1 - (now - unwindAt) / 340) : 1;
        if (k <= 0) { thinkAt = 0; unwindAt = 0; pen = 0; penHold = null; }
        else {
          for (var j = 0; j < 3; j++) leaves.push({
            u: 0.165 + j * 0.108, h: 34 - j * 8.5,
            rot: [-0.05, 0.085, -0.12][j] + (reduce ? 0 : 0.05 * Math.sin(t * 0.52 + j * 1.9)),
            sway: reduce ? 0 : 2.1 * Math.sin(t * 0.74 + j * 1.1)
          });
          if (unwindAt) {
            if (penHold == null) { penHold = pen || 0; tailHold = Math.max(0, penHold - TRAIL); }
            pen = penHold; tailForce = tailHold + (penHold - tailHold) * (1 - k);
          } else {
            penHold = null; tailForce = null;
            var nz = 0.5 + 0.5 * Math.sin(t * 1.55) * Math.sin(t * 0.61 + 1.1);
            var v = reduce ? 4000 : 104 * (nz < 0.17 ? 0.1 : 0.42 + nz * 0.95);   /* 顿一下再走 */
            pen = (pen || 0) + dt * v;
            if (pen > (penTotal || 1e9) + TRAIL) pen = 0;
          }
        }
      } else if (!thinkAt && pen) { pen = 0; penHold = null; }

      /* 响铃：打过来的从那头一遍遍推过来、两下一组；打出去的是慢慢一下 */
      if (!reduce && (p === 'incoming' || p === 'ringing')) {
        var period = p === 'incoming' ? 1600 : 2000;
        if (!ringAt || now - ringAt > period) {
          ringAt = now;
          var dir = p === 'incoming' ? 1 : -1, u0 = dir === 1 ? 0 : 1;
          packets.push({ born: now, dir: dir, u0: u0, amp: 12, k: 30, grain: false });
          if (p === 'incoming') packets.push({ born: now + 240, dir: dir, u0: u0, amp: 9, k: 30, grain: false });
        }
      }
      /* 说话：一个音节一个波包，从说话的那头往对面走 */
      if (!reduce && side >= 0 && (p === 'listening' || p === 'speaking')) {
        if (level > 0.18 && level - prevLevel > 0.02 && now - sylAt > 110) {
          sylAt = now;
          var her = p === 'listening';
          packets.push({
            born: now, dir: her ? -1 : 1, u0: her ? 1 : 0, k: her ? 26 : 30, grain: her,
            amp: (her ? 9.5 : 14) * Math.min(1, level + 0.25)
          });
        }
      }
      prevLevel = level;
      if (packets.length > 18) packets.splice(0, packets.length - 18);
      packets = packets.filter(function (x) { return now - x.born < 2700; });

      var breeze = function (u) {
        return reduce ? 0 : (p === 'thinking' ? 1 : 0.42) *
          (2 * Math.sin(u * 5.6 - t * 1.85) + 1.3 * Math.sin(u * 2.6 - t * 1.15 + 1.3));
      };
      var yAt = function (u) {
        var y = y0 + breeze(u);
        for (var n = 0; n < packets.length; n++) {
          var kk = packets[n], age = (now - kk.born) / 1000;
          if (age < 0 || age > 2.7) continue;
          var d = u - (kk.u0 + kk.dir * 0.52 * age);
          var env = Math.exp(-(d * d) * (kk.grain ? 150 : 46)) * Math.exp(-age * 0.85);
          if (env < 0.003) continue;
          y += kk.grain ? -Math.abs(Math.sin(d * kk.k * 3.2 + age * 7)) * kk.amp * env
                        : Math.sin(d * kk.k - age * 7) * kk.amp * env;
        }
        if (sag) y += Math.sin(Math.PI * u) * sag * (0.62 + 0.38 * Math.sin(t * 0.5));
        return y;
      };

      /* ★ 叶子就是这根线：走到叶柄爬上去绕一圈，落回线上继续往右。整条一笔。 */
      var pts = [], SEG = w / 150, cur = 0, x;
      for (var li = 0; li < leaves.length; li++) {
        var lf = leaves[li], s = lf.h / 512, ax = lf.u * w, ay = yAt(lf.u);
        var P = leafPts, N = P.length, co = Math.cos(lf.rot), si = Math.sin(lf.rot);
        var leg = function (q) {
          return (q.x < 256 ? -1 : 1) * 37 * Math.max(0, Math.min(1, (q.y - 352) / 14));
        };
        var inX = ax + (P[0].x - 256 + leg(P[0])) * s;
        for (x = cur; x < inX; x += SEG) pts.push([x, yAt(x / w)]);
        for (var jj = 0; jj < N; jj++) {
          var hf = 1 - P[jj].y / 512;                       /* 0 柄脚 … 1 叶尖 */
          var dx = (P[jj].x - 256 + leg(P[jj])) * s + lf.sway * hf, dy = (P[jj].y - 512) * s;
          pts.push([ax + dx * co - dy * si, ay + dx * si + dy * co]);
        }
        cur = ax + (P[N - 1].x - 256 + leg(P[N - 1])) * s;
      }
      for (x = cur; x <= w; x += SEG) pts.push([x, yAt(x / w)]);
      pts.push([w, yAt(1)]);

      var total = 0, i;
      for (i = 1; i < pts.length; i++) total += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      penTotal = total;
      var headD = leaves.length ? Math.min(pen, total) : total;
      var tailD = !leaves.length ? 0 : tailForce != null ? tailForce : Math.max(0, pen - TRAIL);
      var acc = 0, tipX = pts[0][0], tipY = pts[0][1], tail0X = pts[0][0], started = false;
      g.beginPath();
      for (i = 1; i < pts.length; i++) {
        var a = pts[i - 1], b = pts[i], seg = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1e-6;
        var s0 = acc; acc += seg;
        if (acc <= tailD) continue;      /* 已经被拆掉了 */
        if (s0 >= headD) break;          /* 还没写到 */
        var f0 = Math.max(0, (tailD - s0) / seg), f1 = Math.min(1, (headD - s0) / seg);
        var x0 = a[0] + (b[0] - a[0]) * f0, y0p = a[1] + (b[1] - a[1]) * f0;
        tipX = a[0] + (b[0] - a[0]) * f1; tipY = a[1] + (b[1] - a[1]) * f1;
        if (!started) { g.moveTo(x0, y0p); tail0X = x0; started = true; }
        g.lineTo(tipX, tipY);
      }
      var grad;
      if (leaves.length) {
        grad = g.createLinearGradient(tail0X, 0, Math.max(tipX, tail0X + 14), 0);
        grad.addColorStop(0, tok.thread);          /* 正在被拆掉的那头，已经沉进纸里 */
        grad.addColorStop(0.42, tok.maple);
        grad.addColorStop(1, tok.maple);           /* 笔尖最实 */
      } else {
        grad = g.createLinearGradient(side === 1 ? w : 0, 0, side === 1 ? 0 : w, 0);
        var hot = p === 'idle' || p === 'ended' ? tok.thread : tok.ink;
        grad.addColorStop(0, side < 0 ? tok.thread : hot);
        grad.addColorStop(1, tok.thread);
      }
      g.strokeStyle = grad;
      g.lineWidth = leaves.length ? 1.45 : 1.2;
      g.lineCap = 'round'; g.lineJoin = 'round';
      g.globalAlpha = p === 'idle' ? 0.5 : p === 'ended' ? 0.3 : leaves.length ? 0.96 : 0.8;
      g.stroke();
      if (leaves.length && headD > 1 && headD < total - 0.5) {     /* 笔尖那一点湿墨 */
        g.beginPath(); g.arc(tipX, tipY, 1.9, 0, Math.PI * 2);
        g.fillStyle = tok.maple; g.globalAlpha = 0.85; g.fill();
      }
      g.globalAlpha = 1;
    }

    var onResize = function () { fit(); };
    global.addEventListener('resize', onResize);
    readTokens(); fit(); raf = requestAnimationFrame(loop);

    return {
      setPhase: function (p) {
        if (st.phase === p) return;
        packets.length = 0; ringAt = 0;              /* 线上的波属于上一个说话的人 */
        if (p === 'thinking') { thinkAt = performance.now(); unwindAt = 0; }
        else if (thinkAt) unwindAt = performance.now();   /* 他一开口＝把线拆掉 */
        st.phase = p;
      },
      getPhase: function () { return st.phase; },
      setLevel: function (v) { ext = Math.max(0, Math.min(1, +v || 0)); extAt = performance.now(); },
      setLeaf: function (def) { opts.leaf = def; leafPts = null; },
      retheme: readTokens,
      fit: fit,
      destroy: function () {
        alive = false; cancelAnimationFrame(raf);
        global.removeEventListener('resize', onResize);
      }
    };
  }

  if (typeof module === 'object' && module.exports) module.exports = Thread;
  else global.Thread = Thread;
})(typeof window !== 'undefined' ? window : this);
