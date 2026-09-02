
/* ══ 记忆字云 · 外壳层 ══════════════════════════════════════════════════
   glyph-cloud.js 是画布本身（算法）。这一段是**外壳**：
   取数、把点中的那条显示在图外面、跟着换皮走。

   ★ 图上不显示记忆正文 —— 原项目定的：图只负责看见量、密度和关系，
     正文在图外面，要翻列表和改就点进列表。记忆本来就是列表。

   ★ 这份是原项目 glyph_ui.js 的照搬版，**结构和文案一行没动**，只换了两处：
     ①「取数」原来是两个 HTTP 接口，这份积木一个网络请求都不许发，
        所以收成一个从外面塞进来的 window.GLYPH_SOURCE（见下）。
     ② 高度偏好原来存服务端的 PREF，这儿换成 localStorage，行为一样。
     UI、文案、交互、靠拢动画一律照搬。

   要的 DOM（id 是硬的，样式也认这些 id）：
     #glyphwrap > #glyphcv          画布和它的容器
     #glyphrow  > #glyphgrab #glyphtip #glyphbar(#glyphzo #glyphzi #glyphrst #glyphmode)
     #glyphpick                     点中那条的详情卡（初始带 hidden）
   ════════════════════════════════════════════════════════════════════ */
(function(){
  var wrap = document.getElementById('glyphwrap'),
      cv   = document.getElementById('glyphcv'),
      pick = document.getElementById('glyphpick');
  if (!wrap || !cv || !pick || !window.GlyphCloud) return;

  /* ── 取数：三件事，从外面塞进来 ────────────────────────────────
     window.GLYPH_SOURCE = {
       list:   function(){ return [memory] | Promise },        全部记忆
       near:   function(id, k){ return [memory] | Promise },   ★语义邻居，不是几何近邻
       full:   function(id){ return {text, ring} | Promise },  读全文
       shapes: [{name, box, d}]                                这团字聚成什么形状
     }
     真部署时把这三个换成你自己的请求即可，下面的 UI 一个字都不用改。 */
  var SRC = window.GLYPH_SOURCE || {};
  function P(v){ return (v && typeof v.then === 'function') ? v : Promise.resolve(v); }
  function srcList(){ return P(SRC.list ? SRC.list() : []); }
  function srcNear(id, k){ return P(SRC.near ? SRC.near(id, k) : []); }
  function srcFull(id){ return P(SRC.full ? SRC.full(id) : null); }

  var cloud = null, last = 0, full = {}, cur = null, byId = {}, seq = 0;
  var LAB = {L3: '核心', L2: '长期', L1: '短期', manual: '校准'};

  function css(k){
    return (getComputedStyle(document.documentElement).getPropertyValue(k) || '').trim();
  }
  function esc(t){
    return String(t == null ? '' : t).replace(/[&<>]/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; });
  }

  function head(m){
    return '<div class="gk">' + esc(LAB[m.layer] || m.layer) + ' · ' + esc(m.day || '') + '</div>'
      + '<div class="gt">' + esc(full[m.id] || m.text + (m.len > m.text.length ? '…' : '')) + '</div>'
      + ((m.len > m.text.length && !full[m.id])
          ? '<button class="gmore" data-id="' + m.id + '">读全文 ›</button>' : '');
  }

  /* 相关那一栏。★ 这里给的是**语义**邻居（后端按 embedding 现算），不是几何上的近邻 ——
     几何近邻等于「那阵子前后的事」，跟「说的是同一件事」完全两码事。原项目 0827 定的。 */
  function paint(d){
    cur = d;
    if (!d || !d.memory){
      pick.hidden = true;
      if (cloud) cloud.setRelated(null);
      return;
    }
    var m = d.memory;
    pick.hidden = false;
    pick.innerHTML = head(m) + '<div class="grh">正在想…</div>';

    var tok = ++seq;
    srcNear(m.id, 6)
      .then(function(r){
        if (tok !== seq) return;                    /* 手快点了下一条，旧的这次不算数 */
        var items = (r && r.items) || r || [];
        var idx = items.map(function(it){ return byId[it.id]; })
                       .filter(function(v){ return v != null; });
        if (cloud) cloud.setRelated(idx);           /* 让它们朝这条飘过来 */
        pick.innerHTML = head(m) + (items.length
          ? '<div class="grh">说的是同一件事</div>' + items.map(function(it){
              var i = byId[it.id];
              return '<button class="gri"' + (i != null ? ' data-i="' + i + '"' : '') + '>'
                + '<b>' + esc(it.text) + '</b>'
                + '<i>' + esc(LAB[it.layer] || it.layer) + ' · ' + esc(it.day || '') + '</i>'
                + '</button>';
            }).join('')
          : '<div class="grh">这条还没连上别的</div>');
      })
      .catch(function(err){
        /* ★ 别再静默 —— 栽过一次「catch 里只 console.warn，故障就藏起来了」。
           错误要能查。 */
        console.error('[glyph/near]', m.id, err);
        if (tok === seq) pick.innerHTML = head(m)
          + '<div class="grh">相关的没取到 · ' + esc(String(err && err.message || err)).slice(0, 40) + '</div>';
      });
  }

  pick.addEventListener('click', function(e){
    var more = e.target.closest('.gmore');
    if (more){
      var id = more.getAttribute('data-id');
      srcFull(id).then(function(d){
        if (!d) return;
        full[id] = d.text + (d.ring ? '\n\n〔年轮〕' + d.ring : '');
        if (cur && cur.memory && String(cur.memory.id) === String(id)) paint(cur);
      }).catch(function(err){ console.error('[glyph/full]', id, err); });
      return;
    }
    var it = e.target.closest('.gri');
    if (it && cloud) cloud.select(+it.getAttribute('data-i'));   /* 顺着关系跳到下一条 */
  });

  /* ── 高度偏好 ────────────────────────────────────────────────
     原项目那份用 PREF（存服务端、多端同步）。积木里没有那玩意，也不该有 ——
     换成 localStorage，行为一样：下次进来还是上回拖出来的那个高度。
     故意保留 get/set/onload 三个方法名，好让下面那段拖拽逻辑一个字都不用改。 */
  var PREF = (function(){
    var K = 'glyphcloud.h';
    return {
      get: function(k, d){
        try { var v = localStorage.getItem(K); return v ? +v : d; } catch (e) { return d; }
      },
      set: function(k, v){ try { localStorage.setItem(K, v); } catch (e) {} },
      onload: function(){}
    };
  })();

  /* ── 拖那条把手，调字云区的高矮 ─────────────────────────────
     要的是：想看大图就往下拽，想看下面的列表就往上推。存 PREF，下次进来还是这个高度。
     把手在画布**外面**（wrap 下沿那一条），所以跟画布自己的手势完全不打架。 */
  (function(){
    var row = document.getElementById('glyphrow'), grab = document.getElementById('glyphgrab');
    if (!row || !grab) return;
    var MIN = 150, MAX = Math.round(innerHeight * 0.72), st = null;
    function put(h, save){
      h = Math.max(MIN, Math.min(MAX, Math.round(h)));
      wrap.style.height = h + 'px';
      if (cloud) cloud.resize();
      if (save && typeof PREF !== 'undefined') PREF.set('glyphH', h);
      return h;
    }
    grab.addEventListener('pointerdown', function(e){
      st = { y: e.clientY, h: wrap.getBoundingClientRect().height };
      row.setAttribute('data-drag', '');
      try { grab.setPointerCapture(e.pointerId); } catch (err) {}
      e.preventDefault();
    });
    grab.addEventListener('pointermove', function(e){
      if (!st) return;
      e.preventDefault();
      put(st.h + (e.clientY - st.y), false);
    });
    ['pointerup','pointercancel'].forEach(function(t){
      grab.addEventListener(t, function(){
        if (!st) return;
        st = null; row.removeAttribute('data-drag');
        put(wrap.getBoundingClientRect().height, true);
      });
    });
    /* 上次拖到哪儿，这次就还在哪儿 */
    /* ⚠ 原项目里 PREF 是 `const PREF = (...)()`，**不挂在 window 上** —— 写 window.PREF
       判断永远是 false。同一个作用域里直接引用得到，用 typeof 兜底就行。 */
    if (typeof PREF !== 'undefined'){
      var saved = PREF.get('glyphH', 0);
      if (saved) put(saved, false);
      PREF.onload(function(m){ if (m && m.glyphH) put(m.glyphH, false); });
    }
  })();

  /* 手指一落到画布上就锁住外头那层滚动，抬手放开。
     不改 .subwrap 的样式源，只挂一个属性，撤掉就干净。 */
  (function(){
    var sw = wrap.closest && wrap.closest('.subwrap');
    if (!sw) return;
    var lock = function(){ sw.setAttribute('data-glyph-lock', ''); };
    var free = function(){ sw.removeAttribute('data-glyph-lock'); };
    cv.addEventListener('pointerdown', lock);
    cv.addEventListener('touchstart', lock, {passive: true});
    ['pointerup','pointercancel','pointerleave'].forEach(function(t){
      cv.addEventListener(t, function(){ setTimeout(free, 60); });
    });
    ['touchend','touchcancel'].forEach(function(t){
      cv.addEventListener(t, function(){ setTimeout(free, 60); }, {passive: true});
    });
  })();

  /* 按住不放连着缩放 —— 一千个字符要看清一个，点十下太笨 */
  function holdZoom(btn, ratio){
    if (!btn) return;
    var timer = null;
    var go = function(){ if (cloud) cloud.zoomBy(ratio); };
    var stop = function(){ clearInterval(timer); timer = null; };
    btn.addEventListener('pointerdown', function(e){
      e.preventDefault(); go();
      stop(); timer = setInterval(go, 110);
    });
    ['pointerup','pointerleave','pointercancel'].forEach(function(t){
      btn.addEventListener(t, stop);
    });
  }
  holdZoom(document.getElementById('glyphzi'), 1.28);
  holdZoom(document.getElementById('glyphzo'), 1 / 1.28);

  /* 回到默认：视角、缩放、平移、选中一起归零 —— 免得放大跑偏了还要一下下点回来。
     ★ 不动拖出来的那个高度：那是使用者的偏好，不是「视图状态」。 */
  var rst = document.getElementById('glyphrst');
  if (rst) rst.addEventListener('click', function(){
    if (!cloud) return;
    cloud.reset();
    var m = document.getElementById('glyphmode');
    if (m){ m.textContent = '纯看'; m.classList.remove('on'); }
  });

  var mode = document.getElementById('glyphmode');
  if (mode) mode.addEventListener('click', function(){
    if (!cloud) return;
    var on = !cloud.state.pick;
    cloud.setPick(on);
    this.textContent = on ? '选记忆' : '纯看';
    this.classList.toggle('on', on);
    var tip = document.getElementById('glyphtip');
    /* 提示语撤了（注释太多）—— 模式看按钮本身就知道 */
  });

  /* 底是深是浅，看 --bg 的感知亮度算 —— 一个应用可能有四套皮 × 明暗两态，
     光看 data-theme 认不全（某些皮的暗色是纯黑，另一些是夜蓝）。
     这个判断要准，因为 light 决定两件事：透明度带的宽度（深底 .30-.50 读作空间深度，
     同样的跨度放浅底上读作脏），和小字号的字重补偿（浅底才需要，深底上发丝笔画读作发光）。 */
  function isLight(){
    var v = css('--bg').replace('#', '');
    if (v.length === 3) v = v.split('').map(function(c){ return c + c; }).join('');
    if (v.length < 6) return true;
    var r = parseInt(v.slice(0,2),16), g = parseInt(v.slice(2,4),16), b = parseInt(v.slice(4,6),16);
    return (r * 299 + g * 587 + b * 114) / 1000 > 128;
  }

  /* 从重点色推出「更深/更纯的那一档」当高亮。
     ★ 0827 定的：悬停和选中要用**更深的那一档**重点色，不是同一个 accent ——
       字云那团红是带透明度的（0.27–0.46），比列表里那些实心数字淡一档，
       拿同一个 accent 做高亮压不住，得往深里再推一档。
       暗色皮反过来：往亮里推，而且不用白色选中色 ——
       走「更纯的重点色」或「浅色的重点色」两条路之一。
     ★ 推导不写死：换皮之后 --maple 变成什么，高亮就跟着算，几套皮都不用管。 */
  function shade(hex, amt){
    var v = String(hex || '').replace('#', '');
    if (v.length === 3) v = v.split('').map(function(c){ return c + c; }).join('');
    if (v.length < 6) return hex;
    var o = [0, 2, 4].map(function(i){
      var c = parseInt(v.slice(i, i + 2), 16);
      return Math.max(0, Math.min(255, Math.round(amt > 0 ? c + (255 - c) * amt : c * (1 + amt))));
    });
    return '#' + o.map(function(c){ return ('0' + c.toString(16)).slice(-2); }).join('');
  }
  /* 夜里那档：光「更浅」不够 —— #e0a373 → #edcaae 明度差太小，得找一下才看得见。
     上面那两条路（更纯的重点色 / 浅色的重点色），这儿走**更纯**：
     把饱和度顶上去、亮度再抬一点，得到一个更艳的橙。在夜蓝底上这个才跳得出来。 */
  function punch(hex){
    var v = String(hex || '').replace('#', '');
    if (v.length === 3) v = v.split('').map(function(c){ return c + c; }).join('');
    if (v.length < 6) return hex;
    var r = parseInt(v.slice(0,2),16)/255, g = parseInt(v.slice(2,4),16)/255, b = parseInt(v.slice(4,6),16)/255;
    var mx = Math.max(r,g,b), mn = Math.min(r,g,b), d = mx - mn;
    var l = (mx + mn) / 2, s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
    var h = 0;
    if (d !== 0){
      if (mx === r) h = ((g - b) / d) % 6;
      else if (mx === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h *= 60; if (h < 0) h += 360;
    }
    s = Math.min(1, s * 1.55);          /* 提纯 */
    l = Math.min(0.82, l + (1 - l) * 0.20);   /* 再抬一点亮 */
    var c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs((h / 60) % 2 - 1)), mm = l - c / 2;
    var t = h < 60 ? [c,x,0] : h < 120 ? [x,c,0] : h < 180 ? [0,c,x]
          : h < 240 ? [0,x,c] : h < 300 ? [x,0,c] : [c,0,x];
    return '#' + t.map(function(u){
      return ('0' + Math.round((u + mm) * 255).toString(16)).slice(-2); }).join('');
  }
  /* 纸底往深推（同色系里更实的一档），夜里往更纯更亮推 */
  function hotOf(a, light){ return light ? shade(a, -0.42) : punch(a); }

  /* ★ 配色是反着来的（0827 定的）：**整团字符是重点色**，不是灰 ——
     这样剪影本身就带着这个应用的身份，而不是一团中性的灰。
     那高亮怎么办？一片红里再用红，只靠浓度和大小分层，
     一千个字里挑七个不够看（实测过）。所以**高亮往深里再推一档** —— 红纸上落笔。
     没引入第三个颜色：--maple 是现成的，只是又推导出一档。
     深浅两套皮都成立，因为这俩的明暗关系正好是反的：纸底上往深推，夜里往亮推，
     都是往对比度大的方向走。 */
  function tint(){
    if (!cloud) return;
    var a = css('--maple'), ink = css('--ink');
    cloud.setLight(isLight());
    cloud.setInk(a, a);                       /* 字符＝重点色（这个项目里是枫叶红） */
    cloud.setLineColor(a);                    /* 连线跟字符同色 */
    cloud.setAccent(hotOf(a, isLight()));     /* 高亮＝更深（夜里更亮）的那一档 */
  }

  /* 出事时让人看见，别只留一片空白 */
  function say(msg, retry){
    var el = document.getElementById('glyphtip');
    if (el) el.textContent = msg;
    wrap.dataset.err = retry ? '1' : '';
  }
  /* 画布是不是还活着。iOS 在内存紧张或切页时会把 canvas 的后备存储清掉，
     尺寸也可能量成 0（那一刻元素还在 transform 里）—— 回来得自己量一次、量不出来就重建。 */
  function healthy(){
    if (!cloud) return false;
    var st = cloud.stats();
    return st.n > 0 && st.w > 0 && st.cw > 0 && cv.getBoundingClientRect().width > 0;
  }

  function refresh(force){
    if (!force && cloud && healthy() && Date.now() - last < 20000) return;
    if (cloud && !healthy()) cloud.resize();        /* 先试着量一次，多半就活了 */
    srcList().then(function(d){
      var mem = (d && d.memories) || d || [];
      if (!mem.length){ say('没取到记忆，点这儿再试一次', true); return; }
      last = Date.now();
      say('', false);
      byId = {};
      mem.forEach(function(x, i){ byId[x.id] = i; });
      if (cloud){ cloud.setMemories(mem); cloud.resize(); pick.hidden = true; return; }
      var a = css('--maple'), ink = css('--ink');
      cloud = GlyphCloud.create(cv, {
        memories: mem,
        /* 这团字聚成什么形状。不传就用出厂那几片。
           ★ 点画布本身＝切到下一片，所以这儿至少要给两片才有的切。 */
        shapes: SRC.shapes,
        /* 字符和连线走重点色、高亮走更深的那一档 —— 见上面 tint() 那段注释 */
        accent: hotOf(a, isLight()), lineColor: a, accentDim: false,
        inkLight: a, inkDark: a, light: isLight(),
        depth: 0.1,          /* 定死的：厚了拉不回来，剪影还会被透视推歪 */
        onSelect: paint
      });
      window.__glyph = cloud;   /* 调试把手 */
    }).catch(function(e){
      console.warn('[glyph]', e);
      /* ★ 原来这儿只 console.warn，取数失败就是一片空白，人只看到「图消失了」，
         也不知道该怎么办。现在写出来，并且允许点一下重试。 */
      say('没连上，点这儿再试一次', true);
    });
  }
  /* 提示语本身可点＝重试 */
  wrap.addEventListener('click', function(e){
    if (wrap.dataset.err && e.target.closest('#glyphtip')) refresh(true);
  });

  /* 页面回到前台就量一次，量不出来就重建。三个入口都要挂：
     ★ `pageshow` 是关键的那个 —— 「返回后再回来，画布空白」多半是 **bfcache**：
       iOS 的前进/后退缓存把整页连 JS 状态一起冻起来，回来时状态都在、
       **可 canvas 的后备存储已经被系统丢了**，所以是一片空白而不是报错。
       bfcache 恢复只发 `pageshow`（persisted=true），`visibilitychange` 抓不到。 */
  function revive(){
    if (!cloud) return;
    setTimeout(function(){
      cloud.resize();
      if (!healthy()) refresh(true);
    }, 120);
  }
  addEventListener('pageshow', function(e){ if (e.persisted) revive(); });
  addEventListener('focus', revive);
  document.addEventListener('visibilitychange', function(){
    if (!document.hidden) revive();
  });

  /* ★ 每次点开这一页都重取 —— 新写的记忆当场就在图里。
     宿主那套导航只在第一次进来时取一次（它是给静态列表设计的），所以这儿自己再挂一个。
     stopPropagation 拦不住同一个 document 上已注册的其它捕获监听，两边互不打架。
     （这份积木单独跑时这个选择器一条都命中不了，挂着不碍事；接进带子页的宿主就活了。） */
  document.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('[data-sub="记忆总览"], [data-sub="总览"]');
    if (b) setTimeout(function(){
      if (cloud) cloud.resize();
      refresh(cloud ? !healthy() : false);       /* 画布掉了就强制重建，别被 20 秒节流挡住 */
    }, 90);
  }, true);

  /* 换皮/换明暗：--maple 和 --ink 都变了，字云得跟着重新配色 */
  new MutationObserver(function(){ setTimeout(tint, 40); })
    .observe(document.documentElement, {attributes: true,
             attributeFilter: ['data-skin', 'data-theme']});

  /* 原项目里这一步由「点开记忆总览」触发。积木单独跑时没人点，所以自己起一次。 */
  refresh(true);
})();
