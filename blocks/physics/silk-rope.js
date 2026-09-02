/*!
 * silk-rope.js —— 卡片挂在绳子上，风一吹会飘。
 *
 * 一块 Verlet 绳子物理：几根丝线从上边垂下来（或左右横渡），卡片被线牵着，
 * 不是排在网格里。手指扫过去线会晃、卡片跟着荡；悬停某根线，它上面的卡片抬起来、
 * 别的线暗下去；点一下那根线绷紧，**再点一下才真的进去**（两段式，防误触）。
 *
 * 渲染只用一条 SVG path ＋ CSS transform。**零依赖。**
 *
 * ── 用它 ────────────────────────────────────────────────
 *   <div class="silkstage" data-stage>
 *     <svg data-svg aria-hidden="true"></svg>
 *     <div class="silkcard" data-card="0"><b>标题</b><i>小字</i></div>
 *     …一共 13 张
 *     <div class="silkhint" data-hint></div>
 *   </div>
 *
 *   const silk = SilkRope(document.querySelector('[data-stage]'), {
 *     onOpen: el => console.log('进去了', el.dataset.card)
 *   });
 *   silk.setWind(1.4); silk.setMode('blinds'); silk.setDrag(true); silk.reset();
 *
 * ── 关于「13 张」────────────────────────────────────────
 * 默认线形里 `pos` 是 13 个手调的坐标，`ropes[].via` 用的是**数组下标**。
 * ★ 所以删掉一张卡，后面每张都会错位一格。要改数量，`pos` 和 `via` 得一起改，
 *   或者整套传自己的 `layout`。这不是 bug —— 那些坐标是一个一个挪出来的。
 *
 * ── 选项 ────────────────────────────────────────────────
 *   onOpen(el)   点第二下时叫。不给就在 stage 上派发 'silk:open'
 *   chrome       {header, footer, shell, body} 宿主的几个元素，都可选：
 *                用来量高度、以及聚焦某根线时把顶栏底栏淡下去
 *   isActive()   这块现在看得见吗。false 就停算（省电）。默认永远 true
 *   layout       覆盖默认线形 {drape, blinds}
 *   mode         'drape' 垂丝 | 'blinds' 横渡 | 'lantern' 灯串（会强制暗色）
 *   wind         0~2.4，默认 .7
 *   drag         true = 卡片能拖着走，位置记下来
 *   storage      localStorage 键前缀，默认 'silk'。传 null = 什么都不存
 *
 * ── 无障碍 ──────────────────────────────────────────────
 * `prefers-reduced-motion` 下只算 90 帧就停：让卡片落到位，然后不再动。
 */
(function (global) {
  'use strict';

  function SilkRope(stage, opts) {
    opts = opts || {};
    if (!stage) return null;
    var svg = stage.querySelector('[data-svg]');
    var cards = [].slice.call(stage.querySelectorAll('[data-card]'));
    var hint = stage.querySelector('[data-hint]');
    if (!svg || !cards.length) return null;

    var KEY = opts.storage === null ? null : (opts.storage || 'silk');
    var k2 = function (k) { return KEY + '.' + String(k).replace(/^silk\./, ''); };
    function LSget(k, d) {
      if (!KEY) return d;
      try { var v = localStorage.getItem(k2(k)); return v ? JSON.parse(v) : d; } catch (e) { return d; }
    }
    function LSset(k, v) {
      if (!KEY) return;
      try { localStorage.setItem(k2(k), JSON.stringify(v)); } catch (e) {}
    }

    /* ── 宿主适配器 ──────────────────────────────────────
       伸到这块以外的手，全都只在这一个对象里。
       核心物理一行都不碰宿主 —— 所以你把它贴到任何页面上都行，要接什么改这儿。 */
    var chrome = opts.chrome || {};
    var themeBefore = null;
    var S = {
      active: opts.isActive || function () { return true; },
      bodyEl: function () { return chrome.body || null; },
      shellH: function () { return (chrome.shell || document.documentElement).clientHeight || 812; },
      headH: function (d) { return chrome.header ? chrome.header.offsetHeight : d; },
      navH:  function (d) { return chrome.footer ? chrome.footer.offsetHeight : d; },
      navTop: function () { return chrome.footer ? chrome.footer.offsetTop : 0; },
      /* 聚焦一根线时顶栏底栏淡下去，让注意力落在线上 */
      dim: function (on) {
        [chrome.header, chrome.footer].forEach(function (el, i) {
          if (!el) return;
          el.style.transition = 'opacity .4s var(--e-out, ease)';
          el.style.opacity = on ? (i ? '.45' : '.25') : '1';
        });
      },
      /* 点第二下＝进去。默认派发事件，宿主爱怎么接怎么接 */
      /* 点第二下＝进去。**两条路都给**：派事件（好接、好测），再调 onOpen（好写）。
         ★ 这里绝不能抛错 —— 它跟 styles() 在同一行链上，
           抛了会把后面的活一起带走（真栽过：styles() 里一个未定义变量，
           焦点清了、回调却从来没跑，看着像「点了没反应」）。 */
      open: function (el) {
        try {
          stage.dispatchEvent(new CustomEvent('silk:open', { detail: { card: el }, bubbles: true }));
        } catch (e) {}
        if (opts.onOpen) { try { opts.onOpen(el); } catch (e) { console.error('[silk] onOpen 出错：', e); } }
      },
      pref: function (k, d) { return LSget(k, d); }
    };

    var mode = opts.mode || LSget('mode', 'drape');
    var dragMode = opts.drag !== undefined ? opts.drag : LSget('drag', false);
    var st = null, raf = 0, frame = 0;
    var reduced = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    if (opts.wind !== undefined) LSset('wind', opts.wind);

    var DRAPE={
      pos:[[108,204],[288,242],[178,318],[86,392],[272,382],[176,462],[312,470],[84,528],[196,556],[292,570],[196,636],[306,672],[72,690]],
      ropes:[
        {a:[64,-14],b:[110,826],via:[0,2,5],w:1.15,op:.78,slack:1.012},
        {a:[250,-14],b:[352,826],via:[1,4,6],w:1.05,op:.74,slack:1.01},
        {a:[18,-14],b:[206,826],via:[3,7,12],w:1.35,op:.84,slack:1.012},
        {a:[160,-14],b:[300,826],via:[8,10],w:1.1,op:.76,slack:1.012},
        {a:[330,-14],b:[380,826],via:[9,11],w:1.6,op:.86,slack:1.014},
        {a:[104,-14],b:[46,826],via:[],w:.85,op:.5,slack:1.1},
        {a:[300,-14],b:[386,826],via:[],w:.7,op:.42,slack:1.13},
        {a:[196,-14],b:[168,826],via:[],w:.9,op:.46,slack:1.08},
        {a:[364,-14],b:[262,826],via:[],w:.65,op:.38,slack:1.15},
        {a:[344,-14],b:[344,300],via:[],w:.8,op:.5,tail:true},
        {a:[148,-14],b:[148,206],via:[],w:.7,op:.42,tail:true},
        /* ★ 0806 加密的纯装饰线（要的是更多、更密、更随机，不急）。
           规矩三条：① via:[] —— 不挂卡片、不接跳转 ② 比主线更细更淡，别跟挂着东西的线抢眼
           ③ slack 取 1.05 以上才看得出弯，1.01 那档是绷得最紧的主线在用。 */
        {a:[38,-14],b:[96,826],via:[],w:.55,op:.32,slack:1.1},
        {a:[222,-14],b:[130,826],via:[],w:.5,op:.28,slack:1.13},
        {a:[386,-14],b:[306,826],via:[],w:.7,op:.38,slack:1.06},
        {a:[6,-14],b:[70,826],via:[],w:.45,op:.24,slack:1.15},
        {a:[276,-14],b:[222,826],via:[],w:.6,op:.34,slack:1.09},
        {a:[128,-14],b:[368,826],via:[],w:.4,op:.22,slack:1.14},
        {a:[82,-14],b:[286,826],via:[],w:.5,op:.26,slack:1.11},
        {a:[316,-14],b:[152,826],via:[],w:.55,op:.3,slack:1.12},
        {a:[240,-14],b:[240,368],via:[],w:.5,op:.3,tail:true},
        {a:[52,-14],b:[52,244],via:[],w:.55,op:.34,tail:true}
      ],
      lift:-22,hoverLift:-5,sig:76,fall:.6,above:1,coupA:.18,coupF:.3,windMul:1,grav:.05
    };
    var BLINDS={
      pos:[[96,206],[272,236],[170,292],[88,652],[256,404],[166,452],[306,492],[86,530],[196,572],[300,612],[206,694],[312,330],[86,368]],
      ropes:[
        {a:[-18,252],b:[411,166],via:[0,1],w:1.2,op:.62,slack:1.01},
        {a:[-18,188],b:[411,246],via:[2,11],w:1.15,op:.6,slack:1.012},
        {a:[-18,336],b:[411,296],via:[12,4],w:1.2,op:.6,slack:1.01},
        {a:[-18,424],b:[411,376],via:[5,6],w:1.15,op:.58,slack:1.012},
        {a:[-18,466],b:[411,666],via:[7,8],w:1.25,op:.64,slack:1.012},
        {a:[-18,706],b:[411,556],via:[3,10,9],w:1.6,op:.7,slack:1.014},
        {a:[-18,196],b:[411,686],via:[],w:2.2,op:.6,slack:1.05},
        {a:[-18,656],b:[411,206],via:[],w:1,op:.44,slack:1.06},
        {a:[-18,300],b:[411,624],via:[],w:.9,op:.4,slack:1.08},
        {a:[-18,566],b:[411,326],via:[],w:1.05,op:.46,slack:1.07},
        {a:[-18,430],b:[411,474],via:[],w:1.3,op:.5,slack:1.14},
        {a:[-18,236],b:[411,470],via:[],w:.8,op:.36,slack:1.1},
        {a:[-18,616],b:[411,180],via:[],w:.75,op:.34,slack:1.05},
        {a:[-18,222],b:[411,228],via:[],w:.7,op:.2,slack:1.006},
        {a:[-18,404],b:[411,412],via:[],w:.7,op:.2,slack:1.005},
        {a:[-18,548],b:[411,542],via:[],w:.7,op:.2,slack:1.006},
        {a:[-18,674],b:[411,668],via:[],w:.7,op:.2,slack:1.004},
        /* 0806 加密的（横渡和灯串共用这一份）。最后那条几乎是直的，跟上面四条一样当底纹使。 */
        {a:[-18,150],b:[411,352],via:[],w:.65,op:.3,slack:1.09},
        {a:[-18,360],b:[411,152],via:[],w:.6,op:.28,slack:1.11},
        {a:[-18,504],b:[411,742],via:[],w:.7,op:.32,slack:1.07},
        {a:[-18,742],b:[411,432],via:[],w:.55,op:.26,slack:1.12},
        {a:[-18,596],b:[411,596],via:[],w:.65,op:.18,slack:1.005}
      ],
      lift:9,hoverLift:6,sig:98,fall:.34,above:.45,coupA:.14,coupF:.24,windMul:.65,grav:.05
    };


    function spline(pts,step){
      var out=[],marks=[],i,k;
      if(pts.length===2){
        var d=Math.hypot(pts[1][0]-pts[0][0],pts[1][1]-pts[0][1]), seg=Math.max(4,Math.round(d/step));
        for(k=0;k<=seg;k++) out.push([pts[0][0]+(pts[1][0]-pts[0][0])*k/seg,pts[0][1]+(pts[1][1]-pts[0][1])*k/seg]);
        marks[0]=0; marks[1]=out.length-1; return {pts:out,marks:marks};
      }
      var P=[pts[0]].concat(pts).concat([pts[pts.length-1]]);
      for(i=1;i<P.length-2;i++){
        var p0=P[i-1],p1=P[i],p2=P[i+1],p3=P[i+2];
        var dd=Math.hypot(p2[0]-p1[0],p2[1]-p1[1]), sg=Math.max(2,Math.round(dd/step));
        for(k=0;k<sg;k++){
          var t=k/sg,t2=t*t,t3=t2*t;
          out.push([
            .5*(2*p1[0]+(-p0[0]+p2[0])*t+(2*p0[0]-5*p1[0]+4*p2[0]-p3[0])*t2+(-p0[0]+3*p1[0]-3*p2[0]+p3[0])*t3),
            .5*(2*p1[1]+(-p0[1]+p2[1])*t+(2*p0[1]-5*p1[1]+4*p2[1]-p3[1])*t2+(-p0[1]+3*p1[1]-3*p2[1]+p3[1])*t3)
          ]);
          if(k===0) marks[i-1]=out.length-1;
        }
      }
      out.push([pts[pts.length-1][0],pts[pts.length-1][1]]);
      marks[pts.length-1]=out.length-1;
      return {pts:out,marks:marks};
    }

    function rebuild(){
      /* ★★ 容器还没有宽度就先别算。
         这块可能被放在一个 display:none 的页里、一个还没展开的 tab 里、
         或者一个此刻不可见的面板里 —— 那时 clientWidth 是 0，
         所有几何都会算成零，卡片被扔到画外，看起来像「渲染坏了」。
         挂个 ResizeObserver 等它有宽度，然后自己回来重算一次。
         （原项目栽过一模一样的：容器 hidden 时初始化，offsetWidth=0，
           clip-path 把纸整个剪没了。） */
      if (!stage.clientWidth) { waitForWidth(); return; }
      var cf=cfg(), NS='http://www.w3.org/2000/svg';
      var H=S.shellH();
      /* ★ 画布高度直接问滚动容器要净高（clientHeight 减掉它自己的上下 padding），
         别再拿「顶栏＋底栏＋26」去估。用户那台 440×894 上估出来的 742 比一屏多 14px，
         主页就多出一条能滑动的余量 —— 纸夹和散摞是钉死一屏的，丝线也该一样。
         短屏（SE、横屏）仍旧走下面那个 540 的下限：不压扁，改成整页滚。 */
      var bodyEl=S.bodyEl(), avail=0;   /* 宿主的滚动容器，没有就按普通布局算 */
      if(bodyEl){
        var bcs=getComputedStyle(bodyEl);
        avail=bodyEl.clientHeight-(parseFloat(bcs.paddingTop)||0)-(parseFloat(bcs.paddingBottom)||0);
      }
      if(!(avail>0)) avail=H-S.headH(80)-S.navH(64)-26;
      var stageH=Math.max(540,avail);
      stage.style.height=stageH+'px';
      var W=stage.clientWidth||393;
      /* ★ 0807 铺满之后，画布上下沿就是屏幕上下沿了 —— 绳子照旧画到画布外（起点 -192），
         所以线是从屏幕最顶垂下来、从两条栏后面穿过去的。
         但**卡片**不能跟着跑到栏底下，得收进安全区：上让开顶栏、下让开底栏。
         底边直接问底栏要它自己的 offsetTop（它是相对 .body 定位的，铺满时 .body 顶＝画布顶），
         别拿 62＋10＋safe 去凑 —— safe-area 各机不同，凑出来的迟早错。 */
      var full = bodyEl && bodyEl.classList.contains('fullbleed');
      var top = full ? (S.headH(64) + 12) : 16;
      var bot = (full && S.navTop()>0) ? (S.navTop() - 12) : (stageH - 52);
      var sx=W/393;
      function mapY(y){ return top+(y-180)/540*(bot-top); }
      svg.textContent='';
      svg.setAttribute('viewBox','0 0 '+W+' '+stageH);
      svg.setAttribute('preserveAspectRatio','none');
      st={ropes:[],cards:[],bulbs:[],focus:-1,hover:-1,amp:0,stageH:stageH,W:W,focusRope:-1,suppress:false,lastA:null,grab:null};
      /* 拖过的位置按 {W, stageH} 校验：换了屏幕尺寸就不认，免得串到画外去（原始设计稿里的规矩） */
      var saved=LSget('pos.'+mode,null);
      /* 这个位置上还挂着卡吗。
         ★ 撤一个入口的正确做法是**留着 DOM、加 hidden**（因为 via 用的是数组下标，
           删 DOM 会让后面每张卡都错位一格）—— 可这样一来，线还是会从那个空坐标拐一下，
           屏上就是一个**没有卡的尖角**。没有卡片的地方，丝线该自然垂下去。
         ★ 只看元素自己的 hidden / display，不看 offsetParent：
           建线的时候整个舞台可能还没显示出来，用可见性判会把所有卡都误判成没挂。 */
      function hung(el){
        if(!el) return false;
        if(el.hasAttribute('hidden')) return false;
        try{ if(getComputedStyle(el).display==='none') return false; }catch(e){}
        return true;
      }

      cf.ropes.forEach(function(rc,ri){
        /* ★ 只把**真挂着卡**的 via 当控制点。下标不重排 —— 空的那个跳过就是了，
           spline 直接从上一个点连到下一个点，剩下的交给 verlet 垂。 */
        var via=(rc.via||[]).filter(function(ci){ return hung(cards[ci]); });
        var pts=[rc.a].concat(via.map(function(i){ return cf.pos[i]; })).concat([rc.b]);
        pts=pts.map(function(p){ return [p[0]*sx,mapY(p[1])]; });
        var sp=spline(pts,13), n=sp.pts.length, i;
        var r={ri:ri,n:n,x:new Float64Array(n),y:new Float64Array(n),px:new Float64Array(n),py:new Float64Array(n),
               inv:new Float64Array(n),rest:new Float64Array(n-1),seed:ri*2.71,op:rc.op};
        for(i=0;i<n;i++){ r.x[i]=r.px[i]=sp.pts[i][0]; r.y[i]=r.py[i]=sp.pts[i][1]; r.inv[i]=1; }
        r.inv[0]=0; if(!rc.tail) r.inv[n-1]=0;
        for(i=0;i<n-1;i++) r.rest[i]=Math.hypot(r.x[i+1]-r.x[i],r.y[i+1]-r.y[i])*(rc.slack||1);
        r.ix=Float64Array.from(r.x); r.iy=Float64Array.from(r.y);
        var p=document.createElementNS(NS,'path');
        r.base=mode==='lantern'
          ? (rc.op>=.44?'rgba(224,163,115,.42)':'rgba(224,163,115,.16)')   /* 灯串下线由灯光定色 */
          : (rc.op>=.44?'var(--thread2)':'var(--thread)');
        p.setAttribute('fill','none'); p.setAttribute('stroke',r.base);
        p.setAttribute('stroke-width',rc.w); p.setAttribute('stroke-linecap','round');
        p.setAttribute('stroke-opacity',rc.op);
        p.setAttribute('vector-effect','non-scaling-stroke');
        p.style.transition='stroke-opacity .4s var(--e-out),stroke .4s var(--e-out)';
        svg.appendChild(p); r.path=p; st.ropes.push(r);
        via.forEach(function(ci,j){
          var el=cards[ci];
          var pt=sp.marks[j+1];
          var tx0=cf.pos[ci][0]*sx, ty0=mapY(cf.pos[ci][1]), tx=tx0, ty=ty0;
          if(saved&&saved[ci]&&saved.W===W&&saved.SH===stageH){ tx=saved[ci][0]; ty=saved[ci][1]; }
          st.cards.push({idx:ci,el:el,ropeIdx:ri,pt:pt,
            tx:tx,ty:ty,tx0:tx0,ty0:ty0,s:1,vs:0,tScale:1,h:(el.offsetHeight||46)/2});
          r.inv[pt]=.26;
        });
      });
      if(mode==='lantern'){
        /* 灯挂在绳结上，所以风一吹灯跟着晃。大小、间距、明暗、呼吸速度全随机，
           三分之一的灯会不定时亮闪一下 —— 排整齐就成圣诞树了。 */
        var bulbG=document.createElementNS(NS,'g');
        st.ropes.forEach(function(r){
          if(r.op<.44) return;
          var taken={};
          st.cards.forEach(function(c){ if(c.ropeIdx===r.ri) for(var k=-3;k<=3;k++) taken[c.pt+k]=1; });
          var bi=3+Math.floor(Math.random()*4);
          while(bi<r.n-3){
            if(!taken[bi]){
              var sz=.5+Math.random()*Math.random()*1.1;      /* 偏小，偶尔来一颗大的 */
              var halo=document.createElementNS(NS,'circle');
              halo.setAttribute('r',(3.4*sz+1.2).toFixed(2)); halo.setAttribute('fill','#e0a373'); halo.setAttribute('opacity','.1');
              var mid=document.createElementNS(NS,'circle');
              mid.setAttribute('r',(1.5*sz+.5).toFixed(2)); mid.setAttribute('fill','#e8b285'); mid.setAttribute('opacity','.22');
              var core=document.createElementNS(NS,'circle');
              core.setAttribute('r',(.55*sz+.32).toFixed(2)); core.setAttribute('fill','#fff3df'); core.setAttribute('opacity','.9');
              bulbG.appendChild(halo); bulbG.appendChild(mid); bulbG.appendChild(core);
              st.bulbs.push({r:r,i:bi,halo:halo,mid:mid,core:core,
                ph:Math.random()*6.3,sp:.6+Math.random()*1.9,tw:Math.random()<.34,
                nx:Math.random()*3000,dim:.5+Math.random()*.5,flash:0});
            }
            bi+=2+Math.floor(Math.random()*7);
          }
        });
        svg.appendChild(bulbG);
      }
      st.ropes.forEach(function(r){ r.iinv=Float64Array.from(r.inv); });
      st.cards.forEach(function(c,i){ c.pos=i; });
      wire();
      setDrag(dragMode);
    }

    function find(idx){ var out=null; if(st) st.cards.forEach(function(c){ if(c.idx===idx) out=c; }); return out; }

    /* ── 拖动模式 ── local / nearest / savePos / setDrag / resetSilk 是原始设计稿里那五个，
         逻辑一字未改（class 的 this 换成闭包里的 st / stage，键还是 silk.pos.<排法>）。 */
    function local(e){ var b=stage.getBoundingClientRect(); return {x:e.clientX-b.left,y:e.clientY-b.top}; }
    function nearest(p,max){
      var best=null,bd=max*max;
      st.ropes.forEach(function(r){
        for(var i=1;i<r.n-1;i++){
          if(r.inv[i]===0) continue;
          var dx=r.x[i]-p.x,dy=r.y[i]-p.y,d=dx*dx+dy*dy;
          if(d<bd){ bd=d; best={r:r,i:i,card:null}; }
        }
      });
      return best;
    }
    function savePos(){
      var o={W:st.W,SH:st.stageH};
      st.cards.forEach(function(c){ o[c.idx]=[c.tx,c.ty]; });
      LSset('pos.'+mode,o);
    }
    function setDrag(v){
      dragMode=!!v; LSset('silk.drag',dragMode);
      [].forEach.call(document.querySelectorAll('[data-drag]'),function(b){
        b.classList.toggle('on',(b.getAttribute('data-drag')==='1')===dragMode);
      });
      if(st) st.cards.forEach(function(c){ c.el.style.cursor=dragMode?'grab':'pointer'; });
      /* 原件是把滚动容器的 touch-action 关掉；proto 的 .body 是所有页共用的（nopad 那一跤就是这么来的），
         所以只关这块画布自己的 —— 别的页照样能滚。 */
      stage.style.touchAction=dragMode?'none':'';
      /* 鼠标拖的时候别把卡片上的字选中（Mac 上拖一下就蓝了一片）；手机上无所谓，但一起关掉更干净 */
      stage.style.userSelect=dragMode?'none':'';
      stage.style.webkitUserSelect=dragMode?'none':'';
    }
    function resetSilk(){
      if(!st) return;
      try{ if(KEY) localStorage.removeItem(k2('pos.'+mode)); }catch(e){}
      st.grab=null;
      st.ropes.forEach(function(r){ for(var i=0;i<r.n;i++){ r.x[i]=r.px[i]=r.ix[i]; r.y[i]=r.py[i]=r.iy[i]; r.inv[i]=r.iinv[i]; } });
      st.cards.forEach(function(c){ c.tx=c.tx0; c.ty=c.ty0; });
    }
    function pluck(c,amp){
      var r=st.ropes[c.ropeIdx], a=amp*.3, i;
      for(i=Math.max(0,c.pt-12);i<Math.min(r.n,c.pt+13);i++){
        if(r.inv[i]===0) continue;
        r.py[i]-=a*(1-Math.abs(i-c.pt)/13);
      }
    }
    function styles(){
      if(!st) return;
      var f=st.focus,h=st.hover;
      st.cards.forEach(function(c){
        var isF=c.pos===f, isH=c.pos===h&&f<0;
        c.tScale=isF?1.26:(isH?1.05:1);
        c.el.style.opacity=(f>=0&&!isF)?'.2':'1';
        c.el.style.filter=(f>=0&&!isF)?'blur(.7px)':'none';
        c.el.style.zIndex=isF?6:(isH?5:3);
        c.el.style.boxShadow=isF?'var(--shadow-lift)':(isH?'var(--shadow-lift)':'var(--shadow)');
      });
      var fr=f>=0?st.cards[f].ropeIdx:(h>=0?st.cards[h].ropeIdx:-1);
      st.focusRope=fr;
      st.ropes.forEach(function(r,i){
        var hot=f>=0&&i===fr;
        r.path.setAttribute('stroke-opacity',f<0?r.op:(hot?1:r.op*.28));
        r.path.setAttribute('stroke',hot?(mode==='lantern'?'#f0c08a':'var(--accent)'):r.base);
      });
      S.dim(f>=0);                                  /* 顶栏底栏淡下去，注意力落在这根线上 */
      if(hint) hint.style.opacity=f>=0?'0':'1';
    }

    function wire(){
      st.cards.forEach(function(c){
        if(c.el.__wired) return;
        c.el.__wired=true;
        var ci=c.idx;
        c.el.addEventListener('pointerenter',function(){
          if(!st||st.focus>=0) return;
          var t=find(ci); if(!t) return;
          st.hover=t.pos; styles();
        });
        c.el.addEventListener('pointerleave',function(){
          if(!st) return;
          var t=find(ci);
          if(t&&st.hover===t.pos){ st.hover=-1; styles(); }
        });
        c.el.addEventListener('click',function(e){
          e.stopPropagation();
          if(!st||st.suppress) return;              /* 刚拖完那一下不算点 */
          var t=find(ci); if(!t) return;
          if(st.focus===t.pos){ st.focus=-1; styles(); S.open(c.el); }
          else { st.focus=t.pos; st.hover=-1; pluck(t,1.6); styles(); }
        });
      });
      if(stage.__wired) return;
      stage.__wired=true;
      stage.addEventListener('click',function(e){
        if(!st) return;
        if(e.target.closest&&e.target.closest('[data-card]')) return;
        if(st.focus>=0&&!st.suppress){ st.focus=-1; styles(); }
      });
      /* 拖：抓卡片就拖卡片，抓空处就抓离手指最近的那个绳结（30px 以内）。
         拖到哪儿挂哪儿、不回弹 —— 卡片的落点存本机，线的落点只在这一场里算数。 */
      stage.addEventListener('pointerdown',function(e){
        if(!dragMode||!st||!true||!S.active()) return;
        var p=local(e), ce=e.target.closest?e.target.closest('[data-card]'):null;
        var g=null;
        if(ce){ st.cards.forEach(function(c){ if(c.el===ce) g={r:st.ropes[c.ropeIdx],i:c.pt,card:c}; }); }
        if(!g) g=nearest(p,30);
        if(!g) return;
        g.gx=p.x; g.gy=p.y; g.moved=0; g.inv0=g.r.inv[g.i]; g.r.inv[g.i]=0;
        st.grab=g;
        e.preventDefault();
      });
      stage.addEventListener('pointermove',function(e){
        var g=st&&st.grab; if(!g) return;
        var p=local(e);
        g.moved+=Math.abs(p.x-g.gx)+Math.abs(p.y-g.gy);
        g.gx=p.x; g.gy=p.y;
        /* ★ 这一处跟原始设计稿不一样，是这边非改不可的：原件在 pointerdown 就抓指针，
           抓了以后 click 的落点被改到容器上 —— 在 proto 里的后果是**开着拖动就点不开卡片**
           （实测：click 打到 [data-stage]，卡片根本收不到）。
           改成真拖起来（超过那 6px）才抓：没拖动的那一下还是原来的 click，卡片照样点得开；
           一旦开始拖，抓指针的好处（手指滑出卡片也跟得住）一样在。 */
        if(g.moved>6&&!g.cap){ g.cap=true; try{ stage.setPointerCapture(e.pointerId); }catch(err){} }
      });
      var drop=function(){
        var g=st&&st.grab; if(!g) return;
        st.grab=null;
        if(g.card){ g.r.inv[g.i]=g.inv0; if(g.moved>6){ g.card.tx=g.gx; g.card.ty=g.gy; savePos(); } }
        else if(g.moved>6){ g.r.x[g.i]=g.r.px[g.i]=g.gx; g.r.y[g.i]=g.r.py[g.i]=g.gy; }
        else g.r.inv[g.i]=g.inv0;
        if(g.moved>6){ st.suppress=true; setTimeout(function(){ if(st) st.suppress=false; },90); }
      };
      stage.addEventListener('pointerup',drop);
      stage.addEventListener('pointercancel',drop);
      /* 还没抓住指针就把手指滑出画布的话，stage 收不到 pointerup —— 兜一层，
         免得那个绳结一直挂在 inv=0 上（动不了了，还看不出为什么）。 */
      window.addEventListener('pointerup',drop);
      window.addEventListener('pointercancel',drop);
    }

    function solve(r,slack){
      for(var i=0;i<r.n-1;i++){
        var i1=r.inv[i],i2=r.inv[i+1],tot=i1+i2;
        if(tot===0) continue;
        var dx=r.x[i+1]-r.x[i],dy=r.y[i+1]-r.y[i];
        var d=Math.hypot(dx,dy)||1e-4, diff=(d-r.rest[i]*slack)/d*.9;
        dx*=diff; dy*=diff;
        r.x[i]+=dx*(i1/tot); r.y[i]+=dy*(i1/tot);
        r.x[i+1]-=dx*(i2/tot); r.y[i+1]-=dy*(i2/tot);
      }
    }
    function tick(now){
      raf=requestAnimationFrame(tick);
      if(!st||!true||!S.active()) return;
      frame++;
      if(reduced&&frame>90) return;
      var cf=cfg(), k, i, r, c;
      var wind=(+LSget('silk.wind',0.7))*cf.windMul*(reduced?0:1), slack=.955;
      /* 手指按住的那个点，这一帧就钉在手指上（速度也一起清掉，松手才不会弹飞） */
      if(st.grab){ var q=st.grab; q.r.px[q.i]=q.r.x[q.i]; q.r.py[q.i]=q.r.y[q.i]; q.r.x[q.i]=q.gx; q.r.y[q.i]=q.gy; }
      var act=st.focus>=0?st.focus:st.hover;
      var A=act>=0?st.cards[act]:null;
      if(A) st.lastA=A;
      var AA=A||st.lastA;
      var tgt=A?(st.focus>=0?cf.coupF:cf.coupA):0;
      st.amp+=(tgt-st.amp)*(tgt>st.amp?.1:.055);
      var amp=st.amp, use=amp>.004&&AA;
      for(k=0;k<st.ropes.length;k++){
        r=st.ropes[k];
        for(i=0;i<r.n;i++){
          if(r.inv[i]===0) continue;
          var vx=(r.x[i]-r.px[i])*.962, vy=(r.y[i]-r.py[i])*.962;
          r.px[i]=r.x[i]; r.py[i]=r.y[i];
          var fx=wind*(.055*Math.sin(now*.00082+r.seed+i*.12)+.032*Math.sin(now*.0021+r.seed*1.9+i*.05));
          var fy=cf.grav+wind*.014*Math.sin(now*.0013+r.seed*2.2+i*.08);
          if(use){
            var ddx=(r.x[i]-AA.tx)/cf.sig, rd=r.ri-AA.ropeIdx;
            fy+=amp*Math.exp(-ddx*ddx)*Math.exp(-Math.abs(rd)*cf.fall)*(rd<0?cf.above:1);
          }
          r.x[i]+=vx+fx; r.y[i]+=vy+fy;
        }
      }
      for(k=0;k<st.cards.length;k++){
        c=st.cards[k]; r=st.ropes[c.ropeIdx]; i=c.pt;
        if(st.grab&&st.grab.r===r&&st.grab.i===i) continue;   /* 正被拖的那张不回弹 */
        var foc=st.focus===c.pos, hov=st.hover===c.pos&&st.focus<0;
        var kk=foc?.05:(hov?.06:.042), lift=foc?cf.lift:(hov?cf.hoverLift:0);
        r.x[i]+=(c.tx-r.x[i])*kk;
        r.y[i]+=(c.ty+lift-r.y[i])*kk;
      }
      for(k=0;k<4;k++) for(i=0;i<st.ropes.length;i++) solve(st.ropes[i],slack);
      for(k=0;k<st.ropes.length;k++){
        r=st.ropes[k];
        var d='M'+r.x[0].toFixed(1)+' '+r.y[0].toFixed(1);
        for(i=1;i<r.n-1;i++) d+='Q'+r.x[i].toFixed(1)+' '+r.y[i].toFixed(1)+' '+((r.x[i]+r.x[i+1])/2).toFixed(1)+' '+((r.y[i]+r.y[i+1])/2).toFixed(1);
        d+='L'+r.x[r.n-1].toFixed(1)+' '+r.y[r.n-1].toFixed(1);
        r.path.setAttribute('d',d);
      }
      for(k=0;k<st.cards.length;k++){
        c=st.cards[k]; r=st.ropes[c.ropeIdx];
        c.vs+=(c.tScale-c.s)*.085; c.vs*=.7; c.s+=c.vs;
        c.el.style.transform='translate3d('+r.x[c.pt].toFixed(1)+'px,'+r.y[c.pt].toFixed(1)+'px,0) translate(-50%,-50%) scale('+c.s.toFixed(3)+')';
      }
      for(k=0;k<st.bulbs.length;k++){
        var b=st.bulbs[k], bx=b.r.x[b.i].toFixed(1), by=b.r.y[b.i].toFixed(1);
        var f=b.dim*(.62+.38*Math.sin(now*.0011*b.sp+b.ph))+.06*Math.sin(now*.0083+b.ph*3.1);
        if(b.tw){
          if(now>b.nx){ b.nx=now+900+Math.random()*5200; b.flash=now; }
          if(b.flash&&now-b.flash<380) f+=1.5*Math.pow(1-(now-b.flash)/380,2);
        }
        if(st.focusRope===b.r.ri) f*=1.8; else if(st.focus>=0) f*=.4;
        b.halo.setAttribute('cx',bx); b.halo.setAttribute('cy',by);
        b.mid.setAttribute('cx',bx);  b.mid.setAttribute('cy',by);
        b.core.setAttribute('cx',bx); b.core.setAttribute('cy',by);
        b.halo.setAttribute('opacity',(.12*f).toFixed(3));
        b.mid.setAttribute('opacity',(.24*f).toFixed(3));
        b.core.setAttribute('opacity',Math.min(1,.34+.66*f).toFixed(3));
      }
    }


    /* ── 丝线颜色 ── 从原始设计稿的 renderThreads/applySkin 搬的，配色和「中性」的算法一字未改：
         中性 = 重点色压到 35%（细线 22%），线有一层淡呼应、又不跟强调色抢；
         挑了具体颜色就锁那个，淡线取它 40% 透明。灯串下不管，那儿由灯光定色。
       ★ proto 的 `--thread2` 本来就写成 color-mix(var(--accent)…)，是惰性求值 ——
         所以「中性」这一档只要把内联覆盖清掉就自动跟着重点色走，不用自己算一遍。 */
    function applyThread(){
      var t = S.pref('thread','auto'), r = document.documentElement.style;
      if (mode==='lantern'){
        /* 灯串的线由灯光定色，两个都还给样式表 */
        r.removeProperty('--thread'); r.removeProperty('--thread2');
      } else if (t === 'auto'){
        /* ★ 0805 定的：丝线颜色要跟着重点色变 —— 就是这一处。
           中性 = 跟着重点色走：`--thread2` 在 :root 上本来就写成
           `color-mix(var(--accent) 35%, var(--thread))`，是惰性求值，
           **只要把内联的那层撤掉，它自己就跟着重点色变**（四套皮各取各的底色）。
           细线那层 `--thread` 跟重点色那边同一个公式（accent 26%）——
           不能只是撤掉：撤了就退回死板的纸线色，只有主线跟着变，看上去像只变了一半；
           也不能不管：从「锁死某个颜色」切回来时，那一层还留着上一个颜色的 40%。 */
        r.removeProperty('--thread2');
        var acc = S.pref('accent',null);
        if (acc) r.setProperty('--thread', 'color-mix(in srgb, ' + acc + ' 26%, #ddd2c6)');
        else r.removeProperty('--thread');       /* 用户没挑过重点色，那就还给皮肤自己 */
      } else {
        r.setProperty('--thread2', t);
        r.setProperty('--thread', 'color-mix(in srgb, ' + t + ' 40%, transparent)');
      }
      /* 线的颜色是建好那会儿钉在 path 上的，改完得重刷一遍 */
      if (st) st.ropes.forEach(function(rp){
        rp.base = mode==='lantern'
          ? (rp.op>=.44?'rgba(224,163,115,.42)':'rgba(224,163,115,.16)')
          : (rp.op>=.44?'var(--thread2)':'var(--thread)');
        if (st.focusRope !== rp.ri) rp.path.setAttribute('stroke', rp.base);
      });
    }
    function cfg() { return (mode === 'blinds' || mode === 'lantern') ? BLINDS : DRAPE; }

    function applyMode() {
      /* 灯串是夜里限定 —— 纸底上那点暖光根本看不见。进它的时候切暗色，
         出来还回去（记着原来是哪套，不霸占使用者的主题设置）。 */
      var R = document.documentElement;
      if (mode === 'lantern') {
        if (themeBefore === null) themeBefore = R.getAttribute('data-theme') || '';
        R.setAttribute('data-theme', 'dark');
      } else if (themeBefore !== null) {
        if (themeBefore) R.setAttribute('data-theme', themeBefore); else R.removeAttribute('data-theme');
        themeBefore = null;
      }
      applyThread();
      rebuild();
    }

    /* 等容器有宽度。只等一次，量到了就断开 —— 别留个观察者在后台空转。 */
    var ro = null;
    function waitForWidth() {
      if (ro || typeof ResizeObserver === 'undefined') return;
      ro = new ResizeObserver(function () {
        if (!stage.clientWidth) return;
        ro.disconnect(); ro = null;
        rebuild();
      });
      ro.observe(stage);
    }

    var rt = 0;
    function onResize() { clearTimeout(rt); rt = setTimeout(rebuild, 120); }
    window.addEventListener('resize', onResize);

    if (opts.layout) {
      if (opts.layout.drape) DRAPE = opts.layout.drape;
      if (opts.layout.blinds) BLINDS = opts.layout.blinds;
    }
    setTimeout(applyMode, 0);
    raf = requestAnimationFrame(tick);

    return {
      setWind:   function (v) { LSset('wind', +v); },
      setDrag:   function (v) { setDrag(!!v); },
      setMode:   function (m) { mode = m; LSset('mode', m); applyMode(); },
      setThread: function (c) { LSset('thread', c); applyThread(); },
      reset:   resetSilk,
      rebuild: rebuild,
      repaint: applyThread,      /* 换了重点色之后叫一下，线的颜色才跟着走 */
      destroy: function () {
        cancelAnimationFrame(raf);
        window.removeEventListener('resize', onResize);
        if (ro) { ro.disconnect(); ro = null; }
        svg.textContent = '';
        st = null;
        S.dim(false);
      }
    };
  }

  if (typeof module === 'object' && module.exports) module.exports = SilkRope;
  global.SilkRope = SilkRope;
})(typeof window !== 'undefined' ? window : this);
