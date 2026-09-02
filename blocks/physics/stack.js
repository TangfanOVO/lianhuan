/* ════════════════════════════════════════════════════════════════════
   从应用 index.html 里**原样抽出来的**（应用是单文件零构建，引不了外链）。
   两份物理上分开存，tests 里钉着：对不上就红。改一处要改两处。
   ★ 里头的算法是设计原件里的代码，**逻辑一字未改** —— 拿到原件先平移，别重做。
   ════════════════════════════════════════════════════════════════════ */
/* ══════════════════ 散摞主页 · 3a 散落成摞 ══════════════════
   ★ 下面 initStack / tStack / qa2 是**原始设计稿里的代码，逻辑一字未改**
     （只把 class 方法的 this 换成闭包里的 S，选择器从 [data-stage="stack"] 换成 [data-stackstage]）。
     规矩是 0804 傍晚栽那一跤换来的：**拿到用户的原件，先平移，别重做。**
     DOM 同理——底噪 44 张、五摞 14 张卡的内联样式，是从原始设计稿里整段搬的。

   两条硬约束（用户在交接里用「⚠」标出来的，别动）：
   ① 摞内转角必须单调递减 —— 名字在纸左边、转轴在纸中心，一负一正的相邻两张
      会让左边缘上下摆（净空那一项变成两头相减，约 −9px），再加多少步距都补不回来。
   ② 五摞各是一层 inset:0 的全屏容器，容器一律 pointer-events:none、只有纸片 auto，
      否则最后一层会把前面四层的点击区全盖住（用户当时只有最后一摞能点）。 */
(function(){
  const host = document.querySelector('[data-stackstage]');
  if (!host) return;
  const S = {
    W: 4.5, reduced: false,                     /* W 是风力，原件默认 4.5；这里只用来定 sway 幅度 */
    qa: sel => Array.prototype.slice.call(document.querySelectorAll(sel)),
    qa2(root, sel){ return root ? Array.prototype.slice.call(root.querySelectorAll(sel)) : []; },
  };
  try { S.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches; } catch(e){}
  /* 跟纸夹同一个滑杆（silk.wind）。这边 sway 里本来就有 Math.min(1.4, S.W) 的封顶，
     所以往上推没有变化、往下拉才看得出来 —— 那个封顶是定的，留着。 */
  const WIND = () => { try { const v = localStorage.getItem('silk.wind');
    return v == null ? 0.7 : (+JSON.parse(v) || 0); } catch(e){ return 0.7; } };

  Object.assign(S, {
  initStack(){
    const st = host;   /* 原件这里是 stage 本身 */
    const groups = S.qa('[data-stackstage] [data-stack]').map((el,gi)=>({
      el, gi, q:0, name: el.getAttribute('data-gname'),
      label: el.querySelector('[data-sname]'),
      items: S.qa2(el, '[data-leaf]').map((le,li)=>{
        const n = a=>parseFloat(le.getAttribute(a));
        return { el:le, i:li, meta: le.querySelector('[data-meta]'),
          px:n('data-px'), py:n('data-py'), pr:n('data-pr'),
          tx:n('data-tx'), ty:n('data-ty'), tr:n('data-tr'), sel:false, g:0 };
      })
    }));
    S.stk = { groups, open:-1 };
    const hint = document.querySelector('[data-stackhint]');
    const say = x=>{ if (hint) hint.textContent = x; };
    const shut = ()=>{ S.stk.open = -1;
      groups.forEach(g=>g.items.forEach(i=>{ i.sel = false; }));
      say('五摞散着 · 点一摞摊开'); };
    st.addEventListener('click', e=>{
      const St = S.stk, le = e.target.closest('[data-leaf]');
      /* 已经有卡浮着时：点同一摞里的另一张＝换那张浮起来（目的不同，不算误触）；
         点别处（空白，或别的摞的卡）＝只是把它放下，这一摞还开着。 */
      if (groups.some(g=>g.items.some(i=>i.sel))){
        const open = groups[St.open];
        const inOpen = le && open && open.items.some(i=>i.el===le);
        if (inOpen){
          const it = open.items.filter(i=>i.el===le)[0], was = it.sel;
          open.items.forEach(i=>{ i.sel = false; });
          it.sel = !was;
          say(it.sel ? open.name + ' › ' + it.el.querySelector('b').textContent
                     : open.name + ' · 点一张进去');
        } else {
          groups.forEach(g=>g.items.forEach(i=>{ i.sel = false; }));
          say(open ? open.name + ' · 点一张进去' : '五摞散着 · 点一摞摊开');
        }
        return;
      }
      if (!le){ shut(); return; }
      const me = groups.filter(g=>g.items.some(i=>i.el===le))[0];
      if (!me) return;
      if (St.open !== me.gi){
        St.open = me.gi;
        groups.forEach(g=>g.items.forEach(i=>{ i.sel = false; }));
        say(me.name + ' · 摊开了 · 点一张进去');
      } else {
        const it = me.items.filter(i=>i.el===le)[0], was = it.sel;
        me.items.forEach(i=>{ i.sel = false; });
        it.sel = !was;
        say(it.sel ? me.name + ' › ' + it.el.querySelector('b').textContent
                   : me.name + ' · 点一张进去');
      }
    });
  },
  qa2(root, sel){ return root ? Array.prototype.slice.call(root.querySelectorAll(sel)) : []; },
  tStack(t, dt){
    const St = S.stk, ease = p=>p<=0?0:p>=1?1:1-Math.pow(1-p,3);
    const any = St.open >= 0;
    const w = document.querySelector('[data-wall-stack]');
    if (w){ w.style.opacity = any ? '0.45' : '1'; w.style.filter = any ? 'blur(1.6px)' : 'none'; }
    St.groups.forEach(g=>{
      const on = g.gi === St.open;
      g.q = Math.max(0, Math.min(1, g.q + (on ? 1 : -1)*dt/430));
      const sway = S.reduced ? 0 : Math.sin(t*0.0006 + g.gi*1.3)*0.45*Math.min(1.4, S.W);
      /* 只在真开着（或正在开合）时抬起来，收起后不许还压着别的摞 */
      g.el.style.zIndex = g.q > 0.001 ? 12 : 2;
      /* 沉下去的摞不能用 opacity —— 一透明，卡片的纸色就跟底纸糊在一起了。
         改成：卡片保持不透明、只做轻微高斯模糊；真正让位的是底纸那一层。 */
      g.el.style.opacity = '1';
      g.el.style.filter = (any && !on) ? 'blur(2.2px)' : 'none';
      if (g.label) g.label.style.opacity = (1 - g.q).toFixed(2);
      const n = g.items.length, iTotal = 430 + (n-1)*30;
      const picked = g.items.some(i=>i.sel);
      g.items.forEach(it=>{
        const e = ease((g.q*iTotal - it.i*30)/430);
        it.gq = Math.max(0, Math.min(1, (it.gq||0) + (it.sel?1:-1)*dt/430));
        it.g = ease(it.gq);
        it.el.style.transform = 'translate3d('
          + (it.px + (it.tx-it.px)*e).toFixed(1)+'px,'
          + (it.py + (it.ty-it.py)*e - it.g*7).toFixed(1)+'px,0) rotate('
          + (it.pr + (it.tr-it.pr)*e + sway*(1-e)).toFixed(2)+'deg) scale('
          + (1 + it.g*0.035).toFixed(3)+')';
        it.el.style.zIndex = it.sel ? 25 : it.i;
        it.el.style.opacity = picked ? (it.sel ? '1' : '0.45') : '1';
        it.el.style.boxShadow = '0 '+(1.5+e*4+it.g*14).toFixed(1)+'px '
          + (4+e*11+it.g*22).toFixed(1)+'px rgba(0,0,0,'
          + (0.06+e*0.04+it.g*0.06).toFixed(3)+')';
        if (it.meta) it.meta.style.opacity = Math.max(0, Math.min(1, e*1.4)).toFixed(2);
      });
    });
  }
  });

  /* ★ 跟纸夹同一个坑：容器 hidden 时 offsetWidth 是 0。3a 不吃 offsetWidth 算几何，
     但 fit() 要量父容器的宽，而且没显示时白跑 rAF 没意义 —— 一样等显示出来再 init。 */
  let inited = false, last = performance.now();
  (function loop(now){
    requestAnimationFrame(loop);
    const dt = Math.min(64, now - last); last = now;
    /* ★ 0830 同纸夹那处：写死找应用的排法容器，积木单独用时永远不初始化。 */
    const sel = window.__stackStageHost;
    const box = sel ? document.querySelector(sel) : host;
    if (!box || box.hidden || !box.offsetWidth) return;
    if (!inited){
      if (!host.offsetWidth) return;              /* 还没量得到，下一帧再说 */
      S.initStack(); inited = true; wire();
    }
    S.W = 4.5 * WIND() / 0.7;
    S.tStack(now, dt);
  })(last);

  /* 点第二下才进去 —— 第一下是把这摞摊开／把这张选中，跟 2a 的「拿起来」同一个规矩。
     这里的监听绑在纸片上，比 initStack 绑在 host 上的那个先跑（target 阶段在冒泡之前），
     所以读到的 it.sel 是**上一次**的状态：为真 = 这张已经选中了，这一下就是进去。
     原件那个监听随后会把它 sel 置回 false，正好——跳走之后摞是干净的摊开态。 */
  const GO = { '心情': '__moodpage' };
  function wire(){
    S.qa('[data-stackstage] [data-leaf]').forEach(el=>{
      el.addEventListener('click', ()=>{
        const St = S.stk; if (!St) return;
        let it = null;
        St.groups.forEach(g=>g.items.forEach(i=>{ if (i.el===el) it = i; }));
        if (!it || !it.sel) return;                 /* 第一下只是摊开／选中 */
        const b = el.querySelector('b'), name = b ? b.textContent : '';
        const ov = id => { const x = document.getElementById(id); if (x) x.classList.add('on'); };
        if (GO[name] === '__moodpage'){
          if (window.openEntry && window.openEntry('#moodpage')) return;
          return ov('moodpage');
        }
        if (window.openEntry && window.openEntry(name)) return;   /* 先找真页面，见 openEntry */
        const a = document.getElementById('subname'), c = document.getElementById('subtitle');
        if (a) a.textContent = name; if (c) c.textContent = name;
        ov('sub');
      });
    });
  }

  function fit(){
    const box = host.parentElement; if (!box) return;
    /* 用户的规格：画布 393×660，宽了就等比放大，没有第二套布局。（跟纸夹同一份 fit）
       画布的 height 是裁切边界，不许跟着 k 变；让出视觉高度是父容器的事。 */
    /* ★ 0804 定的死的：卡片不按页面百分比缩放（跟聊天框一个路数）。
       用户那台 440 宽 → k 恒等于 1，一个像素不缩。
       只有窗口比画布还窄时才整体收一点，否则卡组会被裁掉——要的是「底纸随便裁，卡组不许裁」。 */
    const k = Math.min(1, (box.clientWidth || 440) / 440);
    host.style.transform = k < 1 ? 'scale(' + k.toFixed(4) + ')' : '';
    host.style.transformOrigin = '50% 0';
    host.style.height = '748px';
    box.style.height = (748 * k).toFixed(0) + 'px';
  }
  let ft; addEventListener('resize', () => { clearTimeout(ft); ft = setTimeout(fit, 120); });
  setTimeout(fit, 0);
  window.stackFit = fit;
})();
