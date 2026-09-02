/* 静态预览专用 —— 构建时追加在 dist/index.html 末尾，源文件里没有这一段。
   做三件事：① 页顶一条常驻横条，说明「没有后端」；② 把横条的高度让出来，别压住顶栏；
   ③ 把两个会「假装在工作」的入口（发送、打电话）在捕获阶段拦下——只说明，不清空输入框，不伪造气泡。 */
(function () {
  document.documentElement.dataset.static = '1';

  /* ① 横条：不是 toast，不会消失 */
  var b = document.createElement('div');
  b.id = 'static-bar';
  b.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:9999;'
    + 'padding:calc(8px + env(safe-area-inset-top,0px)) 12px 8px;'
    + 'font:13px/1.5 system-ui,sans-serif;text-align:center;background:#3a3532;color:#f4f1ec';
  b.textContent = '静态预览 · 这里没有后端。你说的话不会送到任何地方，也不会被保存；看到的空状态是真的空。';
  document.body.appendChild(b);

  /* ② 让位：应用里 html,body 是 fixed inset:0、.app 是 100dvh、开屏是 fixed inset:0，
        给 body 加 padding 推不动它们。量出横条的实际高度存进 --static-bar，三处一起往下挪；
        窄屏文字换行变高了，resize 时再量一次。 */
  var css = document.createElement('style');
  css.textContent = 'html[data-static] body{top:var(--static-bar,0px);height:auto}'
    + 'html[data-static] .app{height:calc(100dvh - var(--static-bar,0px))}'
    + 'html[data-static] #splash{top:var(--static-bar,0px)}';
  document.head.appendChild(css);
  function fit() { document.documentElement.style.setProperty('--static-bar', b.offsetHeight + 'px'); }
  fit(); window.addEventListener('resize', fit);

  /* ③ 拦截：挂在 window 的捕获阶段 + stopImmediatePropagation，应用自己挂的 click 一个都跑不到。
        ⚠ 必须是 window 不是 document：应用把「打电话」的处理器也挂在 document 的捕获阶段，
          而且比这段脚本先注册——同一节点上按注册顺序跑，挂 document 拦不住它，通话页照样会开。
        toast(msg, ms) 是应用挂到 window 上的（index.html：window.toast = toast），签名核过。 */
  function say(msg) { if (typeof window.toast === 'function') window.toast(msg, 3600); else alert(msg); }
  var SEND = '静态预览：没有后端，这句发不出去，也不会被保存。';
  var CALL = '静态预览：没有后端，打不了电话。';
  window.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('.send, #callbtn, [data-act="call"]');
    if (!t) return;
    e.stopImmediatePropagation(); e.preventDefault();
    say(t.classList.contains('send') ? SEND : CALL);
  }, true);
  /* 发送还有一条键盘路：聊天输入框里 ⌘/Ctrl+回车 —— 同样拦下 */
  window.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || !(e.metaKey || e.ctrlKey) || !e.target || e.target.id !== 'ta') return;
    e.stopImmediatePropagation(); e.preventDefault();
    say(SEND);
  }, true);
})();
