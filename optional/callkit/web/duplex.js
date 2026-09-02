/* 全双工通话 · 浏览器这一半
   ════════════════════════════════════════════════════════════════════
   零依赖。三件事：把麦克风采成 16K 的裸 PCM、把回来的 24K PCM 排队放出来、
   以及**在它听见你开口的那一刻把正在播的声音掐掉**（这一下就是「全双工」的全部意义）。

   ★ 为什么不能用 MediaRecorder：它给的是 webm/opus 容器，不是裸 PCM。
     上游要 16000 Hz 的 pcm，所以只能走 AudioWorklet 自己采。
     （半双工那条路能用 MediaRecorder，是因为那边是整段录完再上传。）
   ════════════════════════════════════════════════════════════════════ */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Duplex = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var IN_RATE = 16000, OUT_RATE = 24000;

  /* 采集器：跑在音频线程里，每 ~20ms 把一块 Float32 丢回主线程 */
  var WORKLET = `
    class Cap extends AudioWorkletProcessor {
      constructor(){ super(); this.buf = []; this.n = 0; }
      process(inputs){
        const ch = inputs[0] && inputs[0][0];
        if (ch && ch.length){
          this.buf.push(new Float32Array(ch)); this.n += ch.length;
          /* 攒够 320 个采样（16K 下正好 20ms）再发一次 —— 一帧一帧发太碎 */
          if (this.n >= 320){
            const out = new Float32Array(this.n); let o = 0;
            for (const b of this.buf){ out.set(b, o); o += b.length; }
            this.port.postMessage(out, [out.buffer]);
            this.buf = []; this.n = 0;
          }
        }
        return true;
      }
    }
    registerProcessor('cap', Cap);
  `;

  function f32ToI16(f) {
    var out = new Int16Array(f.length);
    for (var i = 0; i < f.length; i++) {
      var s = Math.max(-1, Math.min(1, f[i]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }
  function toB64(buf) {
    var b = new Uint8Array(buf), s = '';
    for (var i = 0; i < b.length; i += 0x8000)
      s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
    return btoa(s);
  }
  function fromB64(s) {
    var bin = atob(s), b = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) b[i] = bin.charCodeAt(i);
    return b;
  }

  return function Duplex(opts) {
    opts = opts || {};
    var on = opts.on || function () {};
    var ws = null, ac = null, node = null, stream = null, src = null;
    var play = null, queue = [], playing = false, at = 0, alive = false;
    var lastFrame = 0, watch = null, reopening = false, reopened = 0;

    /* ── 放：把回来的 24K PCM 排成一条队，别一块一块直接 play（会有缝） ── */
    function ensurePlay() {
      if (!play) play = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: OUT_RATE });
      if (play.state === 'suspended') play.resume();
      return play;
    }
    function push(b64) {
      var ctx = ensurePlay();
      var bytes = fromB64(b64);
      var i16 = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength >> 1);
      var buf = ctx.createBuffer(1, i16.length, OUT_RATE);
      var ch = buf.getChannelData(0);
      for (var i = 0; i < i16.length; i++) ch[i] = i16[i] / 32768;
      var s = ctx.createBufferSource();
      s.buffer = buf; s.connect(ctx.destination);
      /* 排队：每块接在上一块屁股后面。留 20ms 余量，别让它抢在当前时间之前 */
      at = Math.max(at, ctx.currentTime + 0.02);
      s.start(at); at += buf.duration;
      queue.push(s);
      s.onended = function () { var i = queue.indexOf(s); if (i >= 0) queue.splice(i, 1); };
      playing = true;
    }
    /* ★ 打断：把排着的全掐掉。全双工的意义就在这一下 —— 你一开口，它就得闭嘴。 */
    function hush() {
      queue.forEach(function (s) { try { s.stop(); } catch (e) {} });
      queue = []; playing = false;
      if (play) at = play.currentTime;
    }

    /* ── 采：AudioWorklet，16K 裸 PCM ── */
    /* ★ 插耳机（有线或蓝牙）＝音频路由变。在 iOS 上已知会发生三件事，
       原来这儿一件都没管，而三件里随便哪一件发生，**上行就当场哑了**，
       页面上却什么都看不出来：
         ① AudioContext 被打断（Safari 报的是 'interrupted'，不是 'suspended'，
            只判 suspended 会漏）—— 整张图停止渲染，process() 不再被调
         ② 麦克风轨被系统结束（切换默认输出设备时要重配采集单元，超时就 ended）
         ③ 设备列表变化（devicechange）
       所以下面三件一起做：**醒过来、盯着它、停了就自己接回来**。 */
    function wake(c) {
      try { if (c && c.state !== 'running' && c.resume) return c.resume(); } catch (e) {}
      return Promise.resolve();
    }
    function onDevChange() {
      if (!alive) return;
      wake(ac); wake(play);
    }
    function guard() {
      if (!alive || !ws || ws.readyState !== 1 || !lastFrame) return;
      if (ac && ac.state !== 'running') wake(ac);
      if (Date.now() - lastFrame > 1800 && !reopening) reopen('麦克风停了');
    }
    async function reopen(why) {
      if (reopening || !alive) return;
      reopening = true;
      if (reopened >= 3) {
        on({ type: 'error', error: '麦克风接不回来了 —— 挂掉重拨一次' });
        reopening = false; return;
      }
      reopened++;
      on({ type: 'lianhuan.mic', ok: false, why: why || '麦克风断了' });
      try {
        try { if (node) node.disconnect(); if (src) src.disconnect(); } catch (e) {}
        try { if (stream) stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
        try { if (ac) ac.close(); } catch (e) {}
        ac = node = src = stream = null;
        await mic();
        on({ type: 'lianhuan.mic', ok: true });
      } catch (err) {
        on({ type: 'error', error: '麦克风接不回来：' + ((err && err.message) || err) });
      }
      reopening = false;
    }

    async function mic() {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      ac = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: IN_RATE });
      await wake(ac);
      ac.onstatechange = function () { if (ac && ac.state !== 'running') wake(ac); };
      var tr = (stream.getAudioTracks && stream.getAudioTracks()[0]) || null;
      if (tr) tr.onended = function () { reopen('麦克风被系统收走了'); };
      try {
        if (navigator.mediaDevices.addEventListener)
          navigator.mediaDevices.addEventListener('devicechange', onDevChange);
      } catch (e) {}
      var url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }));
      await ac.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      src = ac.createMediaStreamSource(stream);
      node = new AudioWorkletNode(ac, 'cap');
      node.port.onmessage = function (e) {
        lastFrame = Date.now();          /* 看门狗靠它知道采集还活着 */
        if (!alive || !ws || ws.readyState !== 1) return;
        ws.send(JSON.stringify({ type: 'input_audio_buffer.append',
                                 audio: toB64(f32ToI16(e.data).buffer) }));
      };
      src.connect(node);
      /* ⚠ 不接到 destination —— 接了就是把自己的声音又放出来（回声） */
      lastFrame = Date.now();
      clearInterval(watch);
      watch = setInterval(guard, 700);
      return ac.sampleRate;
    }

    async function start(cfg) {
      if (alive) return;
      alive = true;
      var proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
      ws = new WebSocket(proto + location.host + (opts.path || '/api/call/duplex'));
      ws.onopen = function () { ws.send(JSON.stringify(cfg || {})); on({ type: 'lianhuan.open' }); };
      ws.onclose = function () { alive = false; on({ type: 'lianhuan.close' }); };
      ws.onerror = function () { on({ type: 'error', error: '连不上这台机器上的代理' }); };
      ws.onmessage = function (e) {
        var d; try { d = JSON.parse(e.data); } catch (x) { return; }
        var t = d.type || '';
        /* ★ 它听见你开口了 —— 立刻闭嘴。这是全双工跟半双工唯一的、也是全部的区别。 */
        /* ★ 中继那头一说「听见你开口了」，这儿立刻闭嘴。
           （掐对面脑子的活儿在服务端做，这儿只管把已经排上的声音停掉。） */
        if (t === 'lianhuan.listening') {
          hush();
        } else if (t === 'lianhuan.audio' && d.audio) {
          push(d.audio);
        } else if (t === 'lianhuan.spoken') {
          playing = false;
        }
        on(d);
      };
      try {
        await mic();
      } catch (err) {
        on({ type: 'error', error: '拿不到麦克风：' + (err && err.message || err) });
        stop();
      }
    }

    function stop() {
      alive = false;
      clearInterval(watch); watch = null; lastFrame = 0; reopened = 0;
      try {
        if (navigator.mediaDevices.removeEventListener)
          navigator.mediaDevices.removeEventListener('devicechange', onDevChange);
      } catch (e) {}
      hush();
      try { if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: 'session.close' })); } catch (e) {}
      try { if (ws) ws.close(); } catch (e) {}
      try { if (node) node.disconnect(); if (src) src.disconnect(); } catch (e) {}
      try { if (stream) stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
      try { if (ac) ac.close(); } catch (e) {}
      ws = node = src = stream = ac = null;
    }

    return {
      start: start, stop: stop, hush: hush,
      /* 让它念一句指定的话（打招呼、或者你替它说） */
      say: function (text) {
        if (ws && ws.readyState === 1)
          ws.send(JSON.stringify({ type: 'speech_text_buffer.commit', text: String(text || '') }));
      },
      /* 明确告诉它「我说完了」，不等它自己判停 */
      done: function () {
        if (ws && ws.readyState === 1)
          ws.send(JSON.stringify({ type: 'input_audio_buffer.commit' }));
      },
      alive: function () { return alive; },
      speaking: function () { return playing; },
      rates: { in: IN_RATE, out: OUT_RATE },
    };
  };
});
