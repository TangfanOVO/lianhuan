/* ════════════════════════════════════════════════════════════════════
   从应用 index.html 里**原样抽出来的**（应用是单文件零构建，引不了外链）。
   两份物理上分开存，tests 里钉着：对不上就红。改一处要改两处。
   ★ 里头的算法是设计原件里的代码，**逻辑一字未改** —— 拿到原件先平移，别重做。
   ════════════════════════════════════════════════════════════════════ */
/* ══════════════════ 纸夹桌面 · 2a 风吹纸夹 ══════════════════
   ★ 下面 initPaper / tPaper / foldAt 三个函数是**原始设计稿里的代码，逻辑一字未改**
     （只把 class 方法的 this 换成闭包里的 S，并补了 q/qa 两个等价实现）。
     0804 傍晚栽过一次：照 README「重做」，结果阴影公式写重七倍、色标深一倍、
     风少了五个哈希常数、pick 用错缓动。0804 定死的口径：
     丝线版当初就是整段平移的、效果很好，这一版也该照做，不许推倒重写。
     **拿到原件先平移，别重做。** */
(function(){
  const host = document.querySelector('[data-paperstage]');
  if (!host) return;
  const S = {
    W: 4.5, tap: 2.5, reduced: false,
    q : sel => host.querySelector(sel),
    qa: sel => Array.prototype.slice.call(document.querySelectorAll(sel)),
  };
  try { S.reduced = matchMedia('(prefers-reduced-motion: reduce)').matches; } catch(e){}
  /* 风力跟着设置里那根滑杆走。原件里 S.W 写死 4.5，这里按同一个比例换算：
     滑杆停在默认的 0.7 时 S.W 正好还是 4.5，用户调好的那一档一个数没变。
     （丝线那边也是每帧读同一个键，两处的风是同一阵。） */
  const WIND = () => { try { const v = localStorage.getItem('silk.wind');
    return v == null ? 0.7 : (+JSON.parse(v) || 0); } catch(e){ return 0.7; } };

  Object.assign(S, {
  initPaper(){
    const slips = S.qa('[data-paperstage] [data-slip]').map((el,idx)=>{
      const W = el.offsetWidth, H = el.offsetHeight, torn = el.hasAttribute('data-torn');
      const top = [], n = 11;
      for (let i=0;i<=n;i++){
        const r = Math.abs(Math.sin((i+1+idx*7.3)*12.9898)*43758.5453) % 1;
        top.push([W*i/n, torn ? 0.5 + r*4.8 : 0]);
      }
      /* 每张纸自己的相位和阵频：不再按 index 排队，所以吹起的次序是乱的、每张的节奏也不同 */
      const hs = k=>{ const v = Math.sin((idx+1)*12.9898 + k*78.233)*43758.5453; return v - Math.floor(v); };
      return { el, W, H, torn, top,
        ph0: hs(1)*6.2832, envPh: hs(2)*6.2832, envF: 0.00052 + hs(3)*0.00042,
        gustPh: hs(4)*6.2832, gustF: 0.00031 + hs(5)*0.00029,
        body: el.querySelector('[data-body]'), meta: el.querySelector('[data-body] i'),
        face: el.querySelector('[data-face]'), edge: el.querySelector('[data-edge]'),
        curl: el.querySelector('[data-curl]'), cw: el.querySelector('[data-curlwrap]'),
        fsh: el.querySelector('[data-foldsh]'), fw: el.querySelector('[data-foldwrap]'),
        sh: el.querySelector('[data-shadow]'), sw: el.querySelector('[data-shwrap]'),
        x: parseFloat(el.style.left), rot: parseFloat(el.getAttribute('data-rot')),
        ax: parseFloat(el.getAttribute('data-ax')),
        amp: parseFloat(el.getAttribute('data-amp') || '1'),
        lift:0, pick:0, picked:false };
    });
    slips.forEach(s=>{
      s.el.style.transformOrigin = s.ax+'% 0';
      /* 正文填满了纸的 86–97% 高，缩折角腾不出地方 —— 所以让数据行自己让开。
         上限是算出来的：最深折角时，纸背在这一行的最左点。 */
      if (!s.meta || !s.body) return;
      const g = S.foldAt(s.W, s.H, 1, 0), pts = g.crease.concat(g.lobe(0));
      const mTop = s.body.offsetTop + s.meta.offsetTop;
      const mBot = mTop + s.meta.offsetHeight;
      const mLeft = s.body.offsetLeft + s.meta.offsetLeft;
      let lim = s.W;
      for (let i=0;i<pts.length;i++){
        const a = pts[i], b = pts[(i+1)%pts.length];
        for (let t=0;t<=1.0001;t+=0.1){
          const y = a[1] + (b[1]-a[1])*t;
          if (y >= mTop && y <= mBot){ const x = a[0] + (b[0]-a[0])*t; if (x < lim) lim = x; }
        }
      }
      const mw = lim - mLeft - 2;
      if (lim < s.W && mw > 28){
        s.meta.style.maxWidth = Math.round(mw)+'px';
        s.meta.style.whiteSpace = 'nowrap';
        s.meta.style.overflow = 'hidden';
        s.meta.style.textOverflow = 'ellipsis';
      }
    });
    S.pa = { slips };
    S.qa('[data-paperstage]').forEach(st=>st.addEventListener('click', e=>{
      /* 已经有纸浮着时，点哪儿都只是把它放下 —— 不会顺手把误触到的那张拿起来 */
      if (S.pa.slips.some(o=>o.picked)){ S.pa.slips.forEach(o=>{ o.picked = false; }); return; }
      const b = e.target.closest('[data-slip]'); if (!b) return;
      const s = S.pa.slips.filter(o=>o.el===b)[0], was = s.picked;
      S.pa.slips.forEach(o=>{ o.picked = false; });
      s.picked = !was;
    }));
  },
  /* 一阵风沿 x 走，但每张纸自己的相位/阵频/强度都是乱的 —— 次序不排队、幅度不重复。
     贴住的那一点不动 → rotateX + skewX 让其余部分往上飘。 */
  tPaper(t, dt){
    const slips = S.pa.slips, any = slips.some(s=>s.picked);
    const ease = p=>p<=0?0:p>=1?1:1-Math.pow(1-p,3);
    const wind = S.reduced ? 0 : S.W;
    slips.forEach((s,i)=>{
      /* 一阵风从左边过来：相位随 x 推移，阵的包络有底（0.3），周期 ~9s，
         所以永远有纸在动，而且是一张一张轮着被掀，不是全体同时停。 */
      const ph = s.x*0.014 + s.ph0;
      /* 峰取 1.7 次幂＝顶上不赖着；扑上去快、落下来慢 */
      const carrier = Math.pow(Math.max(0, Math.sin(t*0.0013 - ph)), 1.7);
      /* 阵的包络和强度各用一组互不通约的频率 —— 所以次序和幅度都不重复 */
      const env = 0.3 + 0.7*Math.max(0, Math.sin(t*s.envF - s.envPh));
      const gust = 0.45 + 0.55*(0.5 + 0.5*Math.sin(t*s.gustF - s.gustPh));
      /* tanh 软饱和取代 min(1,·)：风越大折得越深，但顶上永远是个圆弯、不是削平的台子。
         底下垫一层呼吸，所以纸不会有四秒钟直挺挺躺着。 */
      const idle = 0.07*(0.5 + 0.5*Math.sin(t*0.00055 - ph*0.4));
      const target = Math.min(1, idle + Math.tanh(carrier*env*gust*wind*s.amp*0.62));
      s.lift += (target - s.lift)*(target > s.lift ? 0.2 : 0.022);
      /* 拿起放下跟 3a 同一条曲线：430ms easeOutCubic，不再是 0.13 的指数收敛（起手太急） */
      s.pq = Math.max(0, Math.min(1, (s.pq||0) + (s.picked?1:-1)*dt/430));
      s.pick = ease(s.pq);
      /* 夹住 0..1：风力和 amp 只改阵风的频率和错峰，不改几何上限 */
      const L = s.lift*(1 - s.pick*0.8), P = s.pick;
      s.el.style.transform =
        'translate3d(0,'+(-L*2.4 - P*6*S.tap).toFixed(2)+'px,0)'+
        ' rotate('+(s.rot*(1-P*0.9)).toFixed(2)+'deg)'+
        ' rotateX('+(-L*10).toFixed(2)+'deg)'+
        ' skewX('+(-L*2.6).toFixed(2)+'deg)'+
        ' scale('+(1 + P*0.014*S.tap).toFixed(3)+')';
      s.el.style.opacity = any ? (s.picked ? '1' : '0.48') : '1';
      s.el.style.zIndex = s.picked ? 6 : 1;
      /* 角是被减掉的：两个折点不对称（用户的 30%/25%），翻过来的角也不是 45° 镜像
         （15%/31% → 这里 0.5×fx / 1.24×fy）。自由边采九点贝塞尔，所以是弯的。 */
      const W = s.W, H = s.H;
      const pxs = p=>p[0].toFixed(1)+'px '+p[1].toFixed(1)+'px';
      const G = S.foldAt(W, H, L, P), crease = G.crease, lobe = G.lobe, nx = G.nx, ny = G.ny;
      const fp = s.top.map(pxs).concat(crease.slice().reverse().map(pxs), ['0px '+H+'px']);
      const facePoly = 'polygon('+fp.join(',')+')';
      s.face.style.clipPath = facePoly; s.edge.style.clipPath = facePoly; s.sh.style.clipPath = facePoly;
      /* 正文也跟着缺口剪：进度条是整宽的一块，不剪就会在深折时冲出纸外 */
      if (s.body) s.body.style.clipPath = facePoly;
      const fl = crease.concat(lobe(0));
      s.curl.style.clipPath = 'polygon('+fl.map(pxs).join(',')+')';
      s.fsh.style.clipPath = 'polygon('+crease.concat(lobe(1.5+L*2.5)).map(pxs).join(',')+')';
      s.fw.style.transform = 'translate3d('+(1+L*1.6).toFixed(1)+'px,'+(1.4+L*2.2).toFixed(1)+'px,0)';
      /* 色阶横穿卷筒。光铺对尺寸不够 —— CSS 渐变是从盒子中心对角走的，
         折痕投影在 ~37% 而不是 0%，深压痕那半段会被剪掉、高光正好压在折痕上。
         所以每帧把折痕和卷脊的投影算出来，再把色阶重映射进这段窗口。 */
      let mx = 1e9, my = 1e9;
      fl.forEach(p=>{ if (p[0] < mx) mx = p[0]; if (p[1] < my) my = p[1]; });
      const gw = W-mx, gh = H-my;
      s.curl.style.backgroundSize = gw.toFixed(1)+'px '+gh.toFixed(1)+'px';
      const Lg = Math.abs(gw*nx) + Math.abs(gh*ny) || 1;
      const tOf = p=>0.5 + ((p[0]-mx-gw/2)*nx + (p[1]-my-gh/2)*ny)/Lg;
      let t0 = 1, t1 = 0;
      crease.forEach(p=>{ const v = tOf(p); if (v < t0) t0 = v; });
      fl.forEach(p=>{ const v = tOf(p); if (v > t1) t1 = v; });
      if (t1 - t0 > 0.02){
        const ramp = [[0,'rgba(0,0,0,.17)'],[0.10,'rgba(0,0,0,.085)'],[0.26,'rgba(0,0,0,.015)'],
                      [0.52,'rgba(255,255,255,.28)'],[0.78,'rgba(0,0,0,.015)'],[1,'rgba(0,0,0,.07)']];
        s.curl.style.backgroundImage = 'linear-gradient('+(Math.atan2(nx,-ny)*57.2958).toFixed(1)+'deg,'
          + ramp.map(r=>r[1]+' '+((t0+(t1-t0)*r[0])*100).toFixed(1)+'%').join(',') + ')';
      }
      s.fw.style.opacity = (0.20 + L*0.12).toFixed(3);
      s.sw.style.opacity = (0.065 + L*0.09 + P*0.10).toFixed(3);
      s.sw.style.transform = 'translate3d('+(1+L*4+P*3).toFixed(1)+'px,'+(2.5+L*10+P*14).toFixed(1)+'px,0) skewX('+(-L*2.4).toFixed(2)+'deg)';
    });
  },

  /* 折角几何。fx/fy 是 approved 的深度（0.40W / 0.38H），不再被任何"安全上限"削平。 */
  foldAt(W,H,L,P){
    const fx = (0.09 + L*0.40)*W + P*4, fy = (0.09 + L*0.38)*H + P*3;
    const Ax = W-fx, Ay = H, Bx = W, By = H-fy;
    const dl = Math.hypot(fx,fy) || 1;
    const tx = fx/dl, ty = -fy/dl;    // 折痕方向 A→B
    const nx = -fy/dl, ny = -fx/dl;   // 外法线，朝纸里
    const b2 = (ax,ay,qx,qy,bx,by,n)=>{ const o = [];
      for (let i=0;i<=n;i++){ const u = 1-i/n, v = i/n;
        o.push([u*u*ax+2*u*v*qx+v*v*bx, u*u*ay+2*u*v*qy+v*v*by]); }
      return o; };
    const b3 = (ax,ay,c1x,c1y,c2x,c2y,bx,by,n)=>{ const o = [];
      for (let i=0;i<=n;i++){ const v = i/n, u = 1-v, a=u*u*u, b=3*u*u*v, c=3*u*v*v, d=v*v*v;
        o.push([a*ax+b*c1x+c*c2x+d*bx, a*ay+b*c1y+c*c2y+d*by]); }
      return o; };
    const bw = 0.035*dl;   // 折痕近乎直，只朝角那边鼓一点点
    const crease = b2(Ax,Ay,(Ax+Bx)/2-bw*nx,(Ay+By)/2-bw*ny,Bx,By,5);
    /* 翻起来那块是被剪掉那块的镜像（StickerPeel 的 flap = scaleY(-1) 的同一张纸），
       按构造与缺口全等。k<4/3：4/3 正好让曲线过 C 点，收到 1.05 是卷筒吃掉的长度。 */
    const foot = fx*tx, k = 1.05;
    const Cx = 2*(Ax + foot*tx) - W, Cy = 2*(Ay + foot*ty) - H;
    const lobe = ex=>b3(Bx, By,
      Bx + (Cx-Bx)*k + nx*ex, By + (Cy-By)*k + ny*ex,
      Ax + (Cx-Ax)*k + nx*ex, Ay + (Cy-Ay)*k + ny*ex,
      Ax, Ay, 14);
    return { fx, fy, crease, lobe, nx, ny };
  }
  });

  /* ★ 必须等容器真的显示出来再 init：hidden 时 offsetWidth 是 0，
     纸的 W/H 全算成零，clip-path 就把整张纸剪没了 —— 屏幕上只剩底噪。
     跟丝线那次 hidden vs style.display 是同一类坑：量不到尺寸，且不报错。 */
  let inited = false, last = performance.now();
  (function loop(now){
    requestAnimationFrame(loop);
    const dt = Math.min(64, now - last); last = now;
    /* ★ 0830 改成可配置：原来这儿写死找应用自己的排法容器 `[data-home="paper"]`，
         积木单独拿出去用时页面上没有它 → 每帧直接 return → initPaper 一次都没跑过
         → 翻角那层没被 clip-path 裁，整层盖住纸上的字（demo 里当场撞见）。
         现在：应用把 `window.__paperStageHost` 指到自己的排法容器（行为一个字不变），
         没设就看舞台自己在不在。 */
    const sel = window.__paperStageHost;
    const box = sel ? document.querySelector(sel) : host;
    if (!box || box.hidden || !box.offsetWidth) return;
    if (!inited){
      if (!host.offsetWidth) return;              /* 还没量得到，下一帧再说 */
      S.initPaper(); inited = true; wire();
    }
    S.W = 4.5 * WIND() / 0.7;                     /* 滑杆一动，下一帧的风就变了 */
    S.tPaper(now, dt);
  })(last);

  /* 点第二下才进去 —— 落点走 proto 自己那套。init 之后再绑，不然 S.pa 还不存在 */
  const GO = ['我给你留的话','一起听','共读进度','信','__moodpage','玩具厅','空间'];
  function wire(){
  S.qa('[data-paperstage] [data-slip]').forEach((el, i) => {
    el.addEventListener('click', (e) => {
      const o = S.pa && S.pa.slips.filter(x => x.el === el)[0];
      if (!o || !o.picked) return;                  /* 第一下只是拿起来 */
      const t = GO[i] || '';
      const ov = id => { const x = document.getElementById(id); if (x) x.classList.add('on'); };
      /* 跟丝线同一条：借外面那个同名入口，才会连带把数据取上（0805） */
      if (t === '__moodpage'){
        if (window.openEntry && window.openEntry('#moodpage')) return;
        return ov('moodpage');
      }
      if (window.openEntry && window.openEntry(t)) return;    /* 先找真页面，见 openEntry */
      const a = document.getElementById('subname'), c = document.getElementById('subtitle');
      if (a) a.textContent = t; if (c) c.textContent = t;
      ov('sub');
    });
  });
  }

  function fit(){
    const box = host.parentElement; if (!box) return;
    /* 用户的规格：画布 393×660，宽了就等比放大，没有第二套布局。
       原来写死 Math.min(1,·) 只缩不放 → 430 宽的机型两边会露纸色底。 */
    /* ★ 0804 定的死的：卡片不按页面百分比缩放（跟聊天框一个路数）。
       用户那台 440 宽 → k 恒等于 1，一个像素不缩。
       只有窗口比画布还窄时才整体收一点，否则卡组会被裁掉——要的是「底纸随便裁，卡组不许裁」。 */
    const k = Math.min(1, (box.clientWidth || 440) / 440);
    host.style.transform = k < 1 ? 'scale(' + k.toFixed(4) + ')' : '';
    host.style.transformOrigin = '50% 0';
    /* ★ 0804 晚修的：原来这里写 host.height = 660*k —— 缩放的是画布本身，
       而 height 定的是 overflow:hidden 的裁切边界，两件事被搅在一起了：
       k<1 时把画布下缘连内容一起裁掉，k>1 时底下多出一大截空白。
       正解是画布**永远** 393×660（用户的规格），让父容器去让出视觉高度。 */
    host.style.height = '748px';
    box.style.height = (748 * k).toFixed(0) + 'px';
  }
  let ft; addEventListener('resize', () => { clearTimeout(ft); ft = setTimeout(fit, 120); });
  setTimeout(fit, 0);
  window.paperFit = fit;
})();
