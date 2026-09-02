/* ══════════════════════════════════════════════════════════════
   聊天页 · 界面这一层
   —— 从应用里那一份整段搬过来的。函数名、口径、注释里的出处，一个没改。

   ★ 这一层**一个网络请求都没有**。它只认「事件」：
        emit('sent'|'recv'|'stage'|'tool'|'os'|'say'|'meta'|'end' …)
     接你自己的后端＝把那些事件喂进来，界面照旧。
     demo.html 里喂的是一段**编出来的**对话（脚本在页面里，看得见）。

   用：
     const chat = Chat(document);          // 或者 Chat(某个容器)
     chat.emit('say', {text:'…|||…', think:'…', first:true});
     chat.say('你好', 'me');
   ══════════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';

  /* ★ 伙伴的名字只写在这一处 —— **改这一处就换成你自己的名字**。
     工具脚注（「◯◯翻了翻记忆 ›」）和详情卡标题都引它，别再往别处写死。 */
  var NAME = '伙伴';

  function Chat(root, opts) {
    root = root || document;
    opts = opts || {};
    var $ = function (sel) { return root.querySelector(sel); };

    /* 那十五个入口在预览页里都不接真东西 —— 结构原样留着，落点换成 opts.hooks */
    var NO_DOOR = opts.noDoorText || '预览页不接真入口';
    var hooks = opts.hooks || {};

    var app   = $('#app') || root.querySelector('.app') || document.body;
    var log   = $('#chatlog');
    var stat  = $('#chatstat');
    var ta    = $('#ta');
    var send  = root.querySelector('.send');
    var bodyEl = $('#body');
    if (!log || !ta) return null;

    /* ── toast ──
       它一直关在 IIFE 里，外面那些 `typeof toast === 'function'` 的保护于是永远不成立
       —— 等于那几处提示语从来没弹过。挂出去，别人才用得上（0806）。 */
    var toastEl = $('#toast'), toastT = null;
    function toast(msg) {
      if (!toastEl) return;
      toastEl.textContent = msg; toastEl.classList.add('on');
      clearTimeout(toastT);
      toastT = setTimeout(function () { toastEl.classList.remove('on'); }, 2100);
    }

    /* 工具名 → 界面上说人话。这张表是**原项目那套工具的例子**，不是规格 ——
       你自己的工具叫什么名字，就在这儿加什么。查不到就原样显示工具名，不会崩。
       ★ 名字里带 `mcp__xxx__` 前缀的会先剥掉前缀再查（见下面 toolCN）。 */
    var TOOL = {Write:'写东西',Edit:'改东西',Read:'看文件',Glob:'找文件',Grep:'翻代码',
      WebSearch:'查东西',WebFetch:'翻网页',write_memo:'记一笔',write_timeline:'记时间线',
      search_memo:'翻记忆',query_timeline:'翻时间线',music_play:'放歌',music_search:'找歌',
      renovate_home:'装修家里',post_moment:'发动态',write_diary:'写日记',write_letter:'写信',
      create_reminder:'定提醒',read_space:'看空间',query_health:'看你的身体数据',look:'睁眼看',
      read_calendar:'翻日历',query_tasks:'看待办',get_kaomoji:'找颜文字'};
    var toolCN = function (n) {
      n = String(n || '');
      var k = n.replace(/^mcp__[a-z_]+__/, '');
      return TOOL[k] || TOOL[n] || k;
    };
    var esc = function (t) {
      return String(t == null ? '' : t).replace(/[&<>]/g, function (c) {
        return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];
      });
    };

    /* 脚注用过去式说法（进行时那张表是状态条用的）—— 两张表都照抄，
       用户认得这些话，别自己另起一套。 */
    var TOOL_DID = {query_timeline:'翻了翻你们的时间线',write_timeline:'在时间线记了一笔',
      search_memo:'翻了翻记忆',write_memo:'悄悄记下了什么',query_health:'看了看你的身体数据',
      write_diary:'写了页日记',read_letters:'重读了信',get_kaomoji:'挑了个颜文字',
      query_tasks:'看了看待办',query_phone_activity:'看了眼你的动静',create_reminder:'设了个提醒',
      read_calendar:'看了眼日历',write_letter:'写了封信',post_moment:'发了条空间',
      read_space:'翻了翻空间',reply_space:'回了空间评论',read_wallet:'看了看钱包',
      spend_wallet:'花了点小钱',fish:'去钓了竿鱼',music_search:'搜了首歌',
      music_play:'点了首歌放给你',WebSearch:'上网查了查',WebFetch:'打开看了个网页',
      Read:'看了看东西',Write:'写了点东西',Edit:'改了点东西'};
    var toolDid = function (list) {
      var out = [];
      (list || []).forEach(function (t) {
        var nm = (t && t.name) || t || '';
        var s = TOOL_DID[String(nm).replace(/^mcp__[a-z_]+__/, '')] || TOOL_DID[nm];
        if (s && out.indexOf(s) < 0) out.push(s);
      });
      return out.slice(0, 4).join(' · ');
    };
    /* 消息里的链接可点 */
    var linkify = function (t) {
      return esc(t).replace(/(https?:\/\/[^\s〕」』）)\]]+)/g, function (u) {
        return '<a href="' + u + '" target="_blank" rel="noopener">'
             + (u.length > 40 ? u.slice(0, 38) + '…' : u) + '</a>';
      });
    };
    /* 隔了 8 分钟以上就插一条时间 */
    var fmtTS = function (ms) {
      if (!ms) return '';
      var d = new Date(ms), n = new Date();
      var hm = ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
      return d.toDateString() === n.toDateString()
        ? hm : ((d.getMonth() + 1) + '月' + d.getDate() + '日 ' + hm);
    };
    var _sep = 0;
    function maybeSep(ms) {
      if (!ms || ms - _sep <= 8 * 60000) { if (ms) _sep = ms; return; }
      var t = document.createElement('div');
      t.className = 'timeline-t'; t.textContent = fmtTS(ms);
      log.appendChild(t); _sep = ms;
    }

    /* 原件里这行是 `let demo = true` ——「页面里那几条是离线预览用的样例，
       真数据一到就整个换掉」。这儿改成读 #chatlog 上的 `data-demo`（原件本来就在那儿写着它），
       为的是让**不带这个标记的页面**（比如这块的 demo.html：整段对话本身就是要留着看的）
       不会在第一次发消息时被清空。行为对原件那种页面完全一致。 */
    var demo = log.hasAttribute('data-demo'), streamEl = null;
    /* 那一排操作键（收藏/念/分享/更多）只跟着最后一条他的话走 —— 原来就是这么排的。
       清 demo 会把它一起清掉，所以先把模板留下来。 */
    var ACTS_HTML = (log.querySelector('.acts') || {outerHTML: ''}).outerHTML;

    function clearDemo() {
      if (!demo) return;
      log.innerHTML = ''; log.removeAttribute('data-demo'); demo = false;
    }

    /* ★ 0818 定的来路标：从别处发来的，在那句下面的图标旁边加 ᯇ⩊ᯇ；
       打电话的转录加 ꒪¯꒳¯꒪ —— 一眼能看出这句话是从哪儿来的。 */
    var SRC_MARK = {qq: 'ᯇ⩊ᯇ', call: '꒪¯꒳¯꒪'};
    function srcMark(src) {
      var m = SRC_MARK[src];
      if (!m) return null;
      var b = document.createElement('span');
      b.className = 'srcmark';
      b.textContent = m;
      b.title = src === 'qq' ? '这句是在另一头说的'
              : src === 'robot' ? '这句是隔着桌上那个身体说的'
              : '这句是打电话时说的';
      return b;
    }

    /* ★ 0807 改：**每一条他的话底下都摆一排**，不再是只有最后一条有 ——
       每一句下面都得有那排能点的键。
       ★ 点击的处理一个字没改：它本来就是 `b.closest('.acts').previousElementSibling`，
         相对定位 —— 所以每条都有一排的时候，每一排天然对着自己上面那句。
       ★ 名字仍叫 moveActs：外面的调用点不用动。 */
    function moveActs() {
      if (!ACTS_HTML) return;
      /* ★ 0807 定的：**一次回复只有最后一句底下有那一行** ——
         多少个泡泡，本质上都只是一次回复：一轮＝一条记录＝一个 cid，
         屏幕上拆成几个泡泡只是断句。所以按 cid 分组，只给每组最后那个挂一排。
         断组的三种情况：cid 变了、中间夹了用户的话、或者插了时间条／思考链（那都意味着新的一轮）。
         ★ 流式还没落库时几个泡泡的 cid 都是空的，空跟空算同一组，正好也是同一轮。 */
      var want = [];
      var group = null;
      [].slice.call(log.children).forEach(function (el) {
        if (!el.classList) return;
        if (el.classList.contains('acts')) return;                  /* 上一轮留下的，等下再算 */
        if (el.classList.contains('msg') && el.classList.contains('him')) {
          var cid = el.dataset.cid || '';
          if (group && group.cid !== cid) { want.push(group.last); group = null; }
          if (!group) group = {cid: cid, last: el};
          else group.last = el;
          return;
        }
        /* 用户的话、时间条、思考链、工具脚注 —— 遇上就收一组 */
        if (group) { want.push(group.last); group = null; }
      });
      if (group) want.push(group.last);

      var keep = new Set(want);
      log.querySelectorAll('.acts').forEach(function (a) {
        var prev = a.previousElementSibling;
        if (!prev || !keep.has(prev)) {
          var pl = a.querySelector('[data-act="play"]');    /* 正在念的先停掉，别留个野音频 */
          if (pl && pl._au) { try { pl._au.pause(); } catch (e) {} pl._au = null; }
          a.remove();
        }
      });
      want.forEach(function (el) {
        var a = el.nextElementSibling;
        if (!(a && a.classList && a.classList.contains('acts'))) {
          var box = document.createElement('div'); box.innerHTML = ACTS_HTML;
          a = box.firstElementChild;
          if (!a) return;
          el.after(a);
        }
        var st = a.querySelector('[data-act="star"]');
        if (st) st.classList.toggle('on', el.classList.contains('starred'));
        /* 0811 定的时间戳。挂在那排键最后，跟着这一轮最后那句走
           （一轮＝一条记录，拆成几个泡泡只是断句，所以时间也只报一次）。 */
        var tm = a.querySelector('time');
        if (!tm) { tm = document.createElement('time'); a.appendChild(tm); }
        var at = Number(el.dataset.ts || 0);
        tm.textContent = at ? fmtTS(at) : '';
        if (at) tm.dateTime = new Date(at).toISOString();
        /* 来路标挨着时间放（他在别处回的、在电话里说的，一眼看得出） */
        var sm = a.querySelector('.srcmark');
        var mk = SRC_MARK[el.dataset.src || ''];
        if (mk && !sm) { sm = srcMark(el.dataset.src); if (sm) a.insertBefore(sm, tm); }
        else if (mk && sm) { sm.textContent = mk; }
        else if (!mk && sm) { sm.remove(); }
      });
    }
    function toBottom() {
      if (bodyEl) bodyEl.scrollTop = bodyEl.scrollHeight;
    }

    function say(text, side, think, ts, src) {
      var at = ts || Date.now();
      maybeSep(at);
      var wrap = document.createDocumentFragment();
      if (think) {
        var tb = document.createElement('button');
        tb.className = 'thinkbar';
        tb.setAttribute('data-think', think);
        tb.innerHTML = '<svg class="i" viewBox="0 0 24 24"><path d="M12 8l0 4l2 2"/>'
          + '<path d="M3.05 11a9 9 0 1 1 .5 4m-.5 5v-5h5"/></svg>Thought process'
          + '<svg class="i cv" viewBox="0 0 24 24"><path d="M9 6l6 6l-6 6"/></svg>';
        wrap.appendChild(tb);
      }
      var d = document.createElement('div');
      d.className = 'msg ' + (side === 'me' ? 'me' : 'him');
      d.dataset.ts = String(at);          /* 那排键上的时间从这儿取（moveActs） */
      if (src) d.dataset.src = src;       /* 来路：qq / call / proactive…（moveActs 也读它） */
      d.innerHTML = linkify(text);        /* linkify 自带转义，不会漏 HTML 进来 */
      wrap.appendChild(d);
      /* 用户自己那句底下没有那排键，时间单挂一行贴着 */
      if (side === 'me') {
        var mt = document.createElement('div');
        mt.className = 'metime';
        var mk = srcMark(src);
        if (mk) mt.appendChild(mk);            /* 来路标在时间左边 */
        mt.appendChild(document.createTextNode(fmtTS(at)));
        wrap.appendChild(mt);
      }
      log.appendChild(wrap);
      toBottom();
      return d;
    }
    function setStat(t) {
      if (!stat) return;
      if (!t) { stat.hidden = true; stat.querySelector('.txt').textContent = ''; return; }
      stat.hidden = false; stat.querySelector('.txt').textContent = t;
      toBottom();
    }

    /* 脚注：一行「🍁 <NAME>翻了翻记忆 · 写了点东西 ›」，点开看他每个动作给出了什么、看到了什么。
       比原来那排小胶囊强 —— 胶囊只说了「做过」，说不出「做了什么」。
       枫叶用我们自己的 SVG，不用 emoji（Font Awesome Free 6 · canadian-maple-leaf, CC BY 4.0）。 */
    var MAPLE = '<svg viewBox="0 0 512 512"><path d="M383.8 351.7c2.5-2.5 105.2-92.4 105.2-92.4l-17.5-7.5c-10-4.9-7.4-11.5-5-17.4 2.4-7.6 20.1-67.3 20.1-67.3s-47.7 10-57.7 12.5c-7.5 2.4-10-2.5-12.5-7.5s-15-32.4-15-32.4-52.6 59.9-55.1 62.3c-10 7.5-20.1 0-17.6-10 0-10 27.6-129.6 27.6-129.6s-30.1 17.4-40.1 22.4c-7.5 5-12.6 5-17.6-5C293.5 72.3 255.9 0 255.9 0s-37.5 72.3-42.5 79.8c-5 10-10 10-17.6 5-10-5-40.1-22.4-40.1-22.4S183.3 182 183.3 192c2.5 10-7.5 17.5-17.6 10-2.5-2.5-55.1-62.3-55.1-62.3S98.1 167 95.6 172s-5 9.9-12.5 7.5C73 177 25.4 167 25.4 167s17.6 59.7 20.1 67.3c2.4 6 5 12.5-5 17.4L23 259.3s102.6 89.9 105.2 92.4c5.1 5 10 7.5 5.1 22.5-5.1 15-10.1 35.1-10.1 35.1s95.2-20.1 105.3-22.6c8.7-.9 18.3 2.5 18.3 12.5S241 512 241 512h30s-5.8-102.7-5.8-112.8 9.5-13.4 18.4-12.5c10 2.5 105.2 22.6 105.2 22.6s-5-20.1-10-35.1 0-17.5 5-22.5z"/></svg>';
    function toolNote(list) {
      var txt = toolDid(list);
      if (!txt) return;
      var n = document.createElement('div');
      n.className = 'toolnote';
      n.innerHTML = MAPLE + '<span>' + esc(NAME) + esc(txt) + ' ›</span>';   /* 名字＝顶上那个 NAME */
      n.addEventListener('click', function () { toolSheet(list); });
      log.appendChild(n); toBottom();
    }
    function toolSheet(list) {
      var ov = document.createElement('div');
      ov.className = 'toolwrap';
      ov.innerHTML = '<div class="toolcard"><h5>' + esc(NAME) + '这轮真实做了什么</h5>'
        + (list || []).map(function (t) {
            var nm = (t && t.name) || t || '';
            var lab = toolDid([t]) || String(nm).replace(/^mcp__[a-z_]+__/, '');
            return '<div class="one"><div class="lab">' + esc(lab) + '</div>'
              + (t && t['in']  ? '<div class="gv">给出：' + esc(String(t['in']).slice(0, 150)) + '</div>' : '')
              + (t && t.out    ? '<div class="sw">看到：' + esc(String(t.out).slice(0, 200)) + '</div>' : '')
              + '</div>';
          }).join('')
        + '<div class="bye">点任意处关掉</div></div>';
      ov.addEventListener('click', function () { ov.remove(); });
      document.body.appendChild(ov);
    }

    /* 库里存的是整段，流式吐的是一句句。
       所以从库里拉回来的要按 ||| 或空行拆回一句一个气泡，才跟现场直出长得一样。
       ★ 另一头过来的话全是 ||| 分段的 —— 不拆就是一坨竖杠。 */
    function splitSay(text) {
      var s = String(text == null ? '' : text);
      if (s.indexOf('|||') >= 0) {
        var segs = s.split('|||').map(function (x) { return x.trim(); }).filter(Boolean);
        if (segs.length) return segs.slice(0, 40);
      }
      var paras = s.split(/\n\s*\n/).map(function (x) { return x.trim(); }).filter(Boolean);
      return paras.length ? paras.slice(0, 40) : [s];
    }

    /* 他在说的时候，发送键就是停止键 —— 一个位置两件事，不再多长一颗按钮出来。
       图标换成方块（停），松开回箭头。钉死的那条回弹动效原样留着。 */
    var ICON_SEND = send ? send.innerHTML : '';
    var ICON_STOP = '<svg class="i" viewBox="0 0 24 24"><path d="M6 6h12v12h-12z" fill="currentColor" stroke="none"/></svg>';
    var busy = false;
    function setBusy(v) {
      busy = v;
      if (!send) return;
      send.innerHTML = v ? ICON_STOP : ICON_SEND;
      send.setAttribute('aria-label', v ? '让他停下' : '发送');
    }

    /* ══ 事件 → 屏幕。**只认事件，一个请求都没有** ══
       接真后端＝把你自己的流式事件翻译成这几种 type 喂进来，这一层照旧。 */
    function emit(type, d) {
      d = d || {};
      switch (type) {
        /* ★ 换了房间：屏幕清空、指针归零，从那一间的库里重拉。 */
        case 'room':
          if (log) log.innerHTML = '';
          document.documentElement.dataset.room = d.who || '';
          setStat('');
          break;
        case 'sent':    clearDemo(); say(d.text, 'me'); setStat('送出去了…'); streamEl = null; setBusy(true); break;
        case 'sending': setStat('送出去了…'); streamEl = null; setBusy(true); break;   /* 气泡界面自己画过了 */
        case 'recv':    setStat('✓ 到他那了'); break;
        case 'stage':   setStat(d.text === '翻记忆' ? '翻着记忆想你这句…' : '在想…'); break;
        case 'tool':    setStat(d.done ? toolCN(d.name) + ' ✓'
                                       : (d.detail ? '正在' + d.detail + '…' : '动手了 · ' + toolCN(d.name) + '…')); break;
        case 'os':      setStat('想好了，在写…'); break;
        case 'say':
          clearDemo();
          /* 思考链只挂在这一轮的第一句上 —— 一轮一个想法，不是每句一个 */
          streamEl = say(d.text, 'him', d.first ? d.think : '');
          setStat('');
          moveActs();          /* 同一轮的会自动并成一排，跟着最后吐出来的那句走 */
          break;
        case 'meta':    toolNote(d.tools); break;
        case 'newseg':
          say('（这段聊满四分之三啦，悄悄换了新的一段——我都记得你，放心聊。）', 'him');
          break;
        case 'resume':  clearDemo(); setStat('我上一条还没说完，线接回去了…'); setBusy(true); break;
        case 'stop':    setStat('停下了。'); setTimeout(function () { setStat(''); }, 1400); break;
        case 'end':
          setStat(''); setBusy(false);
          break;
      }
    }

    /* ══════════════ 思考链 sheet：跟手拖，三档吸附 ══════════════
       档位是 translateY 的百分比：0=拉满、40=一半、72=只露个头、100=关掉。
       只有头部可拖，正文照常滚，两者不打架。 */
    var sheet  = $('#thinksheet'),
        sscrim = $('#sheetscrim'),
        shead  = $('#sheethead');
    var SNAP = [0, 40, 72], CLOSED = 100, sy = CLOSED;

    function setSheet(pct, smooth) {
      if (!sheet) return;
      sy = pct;
      sheet.classList.toggle('dragging', !smooth);
      sheet.style.transform = 'translateY(' + pct + '%)';
      /* 遮罩跟着高度深浅走，拖到一半就该透一半 */
      if (sscrim) {
        sscrim.style.transition = smooth ? '' : 'none';
        sscrim.style.opacity = Math.max(0, (CLOSED - pct) / CLOSED * 0.92).toFixed(3);
        sscrim.style.pointerEvents = pct >= CLOSED ? 'none' : 'auto';
      }
      var chev = root.querySelector('#thinkbar .cv');
      if (chev) chev.style.transform = pct >= CLOSED ? '' : 'rotate(90deg)';
    }
    function sheetOpen(v) { setSheet(v ? SNAP[1] : CLOSED, true); }

    /* 委托：每条消息都可能带自己的想法，不再是页面上那一个写死的 thinkbar。
       带 data-think 的就把那一轮的内心 OS 填进抽屉；没带的（离线预览那条）保留写死的样例。 */
    var sbody = sheet ? sheet.querySelector('.sheetbody') : null;
    var demoThink = sbody ? sbody.innerHTML : '';
    document.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('.thinkbar');
      if (!b || !sheet) return;
      var t = b.getAttribute('data-think');
      if (sbody) {
        sbody.innerHTML = t
          ? t.split(/\n{2,}/).map(function (p) {
              return '<p>' + p.replace(/[&<>]/g, function (c) {
                return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }).replace(/\n/g, '<br>') + '</p>';
            }).join('')
          : demoThink;
        sbody.scrollTop = 0;
      }
      sheetOpen(true);
    });
    var sheetclose = $('#sheetclose');
    if (sheetclose) sheetclose.addEventListener('click', function () { sheetOpen(false); });
    if (sscrim) sscrim.addEventListener('click', function () { sheetOpen(false); });

    var dragging = false, y0 = 0, sy0 = 0, lastY = 0, lastT = 0, vel = 0;
    if (shead) {
      shead.addEventListener('pointerdown', function (e) {
        dragging = true; y0 = e.clientY; sy0 = sy;
        lastY = e.clientY; lastT = e.timeStamp; vel = 0;
        shead.setPointerCapture(e.pointerId);
        sheet.classList.add('dragging');
      });
      shead.addEventListener('pointermove', function (e) {
        if (!dragging) return;
        var h = sheet.offsetHeight || 1;
        var pct = sy0 + (e.clientY - y0) / h * 100;
        if (pct < 0) pct = pct / 3;              // 顶到头给点阻尼，不让它翻上去
        var dt = e.timeStamp - lastT;
        if (dt > 0) { vel = (e.clientY - lastY) / dt; lastY = e.clientY; lastT = e.timeStamp; }
        setSheet(Math.min(pct, CLOSED), false);
      });
      shead.addEventListener('pointerup', endSheetDrag);
      shead.addEventListener('pointercancel', endSheetDrag);
    }
    function endSheetDrag() {
      if (!dragging) return;
      dragging = false;
      /* 甩得快就顺着方向走一档，慢就吸最近的 */
      var targets = SNAP.concat([CLOSED]), t;
      if (vel > 0.6) {
        t = targets.find(function (v) { return v > sy + 1; });
        if (t == null) t = CLOSED;
      } else if (vel < -0.6) {
        t = targets.slice().reverse().find(function (v) { return v < sy - 1; });
        if (t == null) t = 0;
      } else {
        t = targets.reduce(function (a, b) { return Math.abs(b - sy) < Math.abs(a - sy) ? b : a; });
      }
      setSheet(t, true);
    }

    /* ══ 那颗星 · 逐帧（0820）══ 五个字符来回走，1.2 秒一轮。
       只在状态行露脸的时候才转，藏起来就停 —— 不留一个后台定时器空转。 */
    (function () {
      var el = $('#cspin');
      if (!el) return;
      var F = ['·', '✢', '✶', '✻', '✽', '✽', '✻', '✶', '✢', '·'];   /* 去五帧回五帧＝原件的十个关键帧 */
      var i = 0, t = 0;
      var host = stat;
      function tick() { el.textContent = F[i = (i + 1) % F.length]; }
      function run(on) {
        if (on && !t) { t = setInterval(tick, 120); }        /* 1.2s ÷ 10 帧 */
        else if (!on && t) { clearInterval(t); t = 0; }
      }
      if (host) {
        new MutationObserver(function () { run(!host.hidden); })
          .observe(host, {attributes: true, attributeFilter: ['hidden']});
        run(!host.hidden);
      }
    })();

    /* ══════════════ 那排键：收藏 · 念 · 分享 · 更多 ══════════════ */
    var chatPage = $('#p-chat') || log.parentNode;
    var popm = $('#popmenu');

    chatPage.addEventListener('click', function (e) {
      /* ⚠ 这里是聊天气泡那排（收藏/念/分享/更多），类名就是 .acts。
         0805 给别处那三个改名 .acts→.dacts 时把这一行也扫了，
         结果聊天页每次点击都在这儿 return，按钮全成了画上去的。别再改。 */
      var b = e.target.closest('.acts button'); if (!b) return;
      var act = b.dataset.act;
      if (act === 'star') {
        var host = b.closest('.acts'), tgt = host && host.previousElementSibling;
        var want = !b.classList.contains('on');
        b.classList.toggle('on', want);
        if (tgt) tgt.classList.toggle('starred', want);
        if (opts.onStar) opts.onStar(tgt, want);
        toast(want ? '收下了，连同这段思考链一起' : '取消收藏');
      } else if (act === 'play') {
        /* 念出声要看得见：键自己亮起来并呼吸，念完自己灭。 */
        var ph = b.closest('.acts'), pm = ph && ph.previousElementSibling;
        var ptxt = pm && pm.classList.contains('msg') ? pm.textContent : '';
        if (b.classList.contains('playing')) {
          b.classList.remove('playing');
          if (b._au) { try { b._au.pause(); } catch (err) {} b._au = null; }
          toast('停了');
          return;
        }
        if (!ptxt) return;
        b.classList.add('playing');
        if (opts.onPlay) opts.onPlay(ptxt, b);
        else { toast(NO_DOOR); setTimeout(function () { b.classList.remove('playing'); }, 1200); }
      } else if (act === 'share') {
        toast(NO_DOOR);
      } else if (act === 'more') {
        /* 三个点不再跟分享抢活 —— 它是别的动作的入口 */
        if (!popm) return;
        var r = b.getBoundingClientRect();
        var pr = app.getBoundingClientRect();
        var mleft = Math.min(r.left - pr.left, pr.width - 148);
        popm.style.left = mleft + 'px';
        popm.style.top  = (r.bottom - pr.top + 6) + 'px';
        /* 0807：让它从「三个点」那颗按钮底下长出来，不是从自己正中胀开。
           菜单挨着 pr.width - 148 那条边被推回来时，原点也跟着往右挪，所以按实际 left 算。 */
        popm.style.setProperty('--po', Math.round(r.left - pr.left - mleft + r.width / 2) + 'px 0');
        popm.classList.add('on');
        popm._for = b; popm._msg = null;   /* 0807：走的是「更多」这条路，清掉长按记的那条 */
        syncStarLabel();
        e.stopPropagation();
      }
    });

    /* 0807：这张菜单现在有两个来路 —— 长按某一条（popm._msg），或者那条底下那颗「更多」（popm._for）。
       所有动作统一问这一个函数「你要动的是哪一条」，别再各自去 closest('.acts')。 */
    function popMsgEl() {
      if (!popm) return null;
      if (popm._msg && popm._msg.isConnected) return popm._msg;
      var h = popm._for && popm._for.closest('.acts');
      var p = h && h.previousElementSibling;
      return (p && p.classList && p.classList.contains('msg')) ? p : null;
    }
    /* 菜单上那颗星的字要跟着当前这条的状态走 */
    function syncStarLabel() {
      if (!popm) return;
      var el = popMsgEl();
      var lb = popm.querySelector('[data-starlabel]');
      if (!lb) return;
      lb.textContent = (el && el.classList.contains('starred')) ? '取消收藏' : '收藏这句';
    }

    if (popm) {
      popm.addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b) return;
        var m = b.dataset.m;
        popm.classList.remove('on');
        /* copy / quote 是纯前端的事，不用惊动后端 */
        var _el  = popMsgEl();
        var _txt = _el ? _el.textContent : '';
        if (m === 'copy') {
          if (navigator.clipboard && _txt) navigator.clipboard.writeText(_txt);
          toast('复制了');
        } else if (m === 'quote') {
          if (_txt) { ta.value = '「' + _txt.slice(0, 60) + '」\n'; ta.focus(); }
        } else if (m === 'star') {
          if (!_el) { toast('没认出是哪一句'); return; }
          var on = !_el.classList.contains('starred');
          _el.classList.toggle('starred', on);
          moveActs();
          toast(on ? '收下了，连同这段思考链一起' : '取消收藏');
        } else if (m === 'hide') {
          /* 0818：整轮一起淡出，淡完从 DOM 里摘掉，位置也收回去 */
          if (!_el) return;
          var row = [_el];
          var nx = _el.nextElementSibling;
          if (nx && nx.classList && (nx.classList.contains('acts') || nx.classList.contains('metime'))) row.push(nx);
          var pv = _el.previousElementSibling;
          if (pv && pv.classList && pv.classList.contains('thinkbar')) row.push(pv);
          row.forEach(function (n) { n.classList.add('gone'); });
          setTimeout(function () { row.forEach(function (n) { n.remove(); }); moveActs(); }, 320);
          toast('撤走了。聊天记录里还看得到，记忆一条没少。');
        } else {
          toast(NO_DOOR);
        }
      });
      document.addEventListener('click', function (e) {
        if (!popm.classList.contains('on')) return;
        if (e.target.closest && e.target.closest('.popmenu, .acts button')) return;
        popm.classList.remove('on');
      });
    }

    /* ══ 长按任意一条＝对这条动手（0807）══
       0807 定的：收藏不能只有最新那句能点，以前的也要能点，两个聊天室都做。
       ★ 不新造菜单，长按弹现成的 popmenu —— 它比那排还多了引用、重说、只藏不删。 */
    (function () {
      if (!popm) return;
      var HOLD = 600;                       /* 跟原来同一个数，别自己另定 */
      var timer = 0, sx = 0, syy = 0, target = null;

      function openFor(el, x, y) {
        if (!el) return;
        var pr = app.getBoundingClientRect(), r = el.getBoundingClientRect();
        var px = (x != null ? x : r.left + 30), py = (y != null ? y : r.bottom);
        var left = Math.max(8, Math.min(px - pr.left - 60, pr.width - 148));
        popm.style.left = left + 'px';
        popm.style.top  = Math.max(8, Math.min(py - pr.top + 8, pr.height - 240)) + 'px';
        popm.style.setProperty('--po', Math.round(px - pr.left - left) + 'px 0');
        popm._msg = el; popm._for = null;      /* ★ 长按这条路，记的是气泡本身 */
        popm.classList.add('on');
        syncStarLabel();
      }
      function hit(e) {
        var t = (e.touches ? e.touches[0] : e);
        var el = t.target && t.target.closest ? t.target.closest('.msg') : null;
        /* 多选模式下点气泡是在挑，别抢；操作条上的按钮各干各的 */
        if (!el || chatPage.classList.contains('picking')) return null;
        if (t.target.closest('.acts, .thinkbar, a, button')) return null;
        return {el: el, x: t.clientX, y: t.clientY};
      }
      log.addEventListener('touchstart', function (e) {
        if (e.touches.length !== 1) return;
        var h = hit(e); if (!h) return;
        target = h.el; sx = h.x; syy = h.y;
        clearTimeout(timer);
        timer = setTimeout(function () { if (target) openFor(target, sx, syy); target = null; }, HOLD);
      }, {passive: true});
      var cancel = function () { clearTimeout(timer); target = null; };
      log.addEventListener('touchend', cancel);
      log.addEventListener('touchcancel', cancel);
      log.addEventListener('touchmove', function (e) {
        if (!target) return;
        var t = e.touches[0];
        if (Math.abs(t.clientX - sx) > 8 || Math.abs(t.clientY - syy) > 8) cancel();  /* 手在滚，不算长按 */
      }, {passive: true});
      /* 桌面：右键同样弹它 */
      log.addEventListener('contextmenu', function (e) {
        var h = hit(e); if (!h) return;
        e.preventDefault();
        openFor(h.el, h.x, h.y);
      });
    })();

    /* ══════════════ 加号菜单 ══════════════
       「翻空间 / 翻碎碎念 / 翻共读」原来是 pullShare()：挑今天的，今天没有就挑最近三条，
       连同那句场景提示（「陪用户一起看，哪条戳你就聊什么，别逐条汇报」）一起发过去。
       按的是「一起看」，不是「汇报」。
       ★ 预览页里这十五个入口都不接真东西 —— 结构原样留着，落点换成 opts.hooks。 */
    (function () {
      var psheet = $('#plussheet'), pscrim = $('#plusscrim'), grid = $('#plusgrid');
      if (!psheet || !grid) return;
      function open(v) {
        psheet.style.transform = v ? 'translateY(0)' : '';
        if (pscrim) pscrim.classList.toggle('on', v);
      }
      document.addEventListener('click', function (e) {
        var b = e.target.closest && e.target.closest('[data-sub="加号菜单"]');
        if (!b) return;
        e.stopPropagation(); e.preventDefault();
        open(true);
      }, true);
      if (pscrim) pscrim.addEventListener('click', function () { open(false); });
      var pclose = $('#plusclose');
      if (pclose) pclose.addEventListener('click', function () { open(false); });

      grid.addEventListener('click', function (e) {
        var b = e.target.closest('.pit'); if (!b) return;
        /* 收新消息：手动拉一趟增量 */
        if (b.dataset.act === 'sync') {
          open(false);
          if (hooks.sync) setTimeout(function () { hooks.sync(true); }, 120);
          else toast(NO_DOOR);
          return;
        }
        /* (0818) 打电话：通话页是自己一套状态机和音频管线，不寄在聊天层里 */
        if (b.dataset.act === 'call') {
          open(false);
          if (hooks.call) setTimeout(hooks.call, 140); else toast(NO_DOOR);
          return;
        }
        /* (0820) 哄睡：这一下也是「用户手势」，音频要在这一下里解锁 */
        if (b.dataset.act === 'lull') {
          open(false);
          if (hooks.lull) hooks.lull('chat'); else toast(NO_DOOR);
          return;
        }
        /* 挑照片/文件：关掉面板，把系统选择器叫起来（挑完停在输入框上头，不直接发） */
        if (b.dataset.pick) {
          open(false);
          var f = b.dataset.pick === 'photos' ? hooks.pickPhotos : hooks.pickFiles;
          if (f) setTimeout(f, 120);              /* 等这张纸落下去再弹选择器 */
          else toast(NO_DOOR);
          return;
        }
        var door = b.dataset.door;
        if (door) {
          open(false);
          if (hooks.door) setTimeout(function () { hooks.door(door); }, 60);
          else toast(NO_DOOR);
          return;
        }
        if (b.dataset.pull) {
          open(false);
          if (hooks.pull) hooks.pull(b.dataset.pull, b); else toast(NO_DOOR);
        }
      });
      /* 语音那颗跟加号并排，落点一样交给 hooks */
      root.querySelectorAll('.cbtn').forEach(function (b) {
        if ((b.getAttribute('data-sub') || '').indexOf('语音') < 0) return;
        b.addEventListener('click', function (e) {
          e.preventDefault(); e.stopPropagation();
          if (hooks.voice) hooks.voice(); else toast(NO_DOOR);
        });
      });
    })();

    /* ══════════════ 暂存条 ══════════════
       挑完先不发，停在输入框上头等配一句话 —— 选好了不直接发送。
       staged 是一排 {kind:'img'|'file', dataURL, name}。 */
    var bar = $('#stagebar');
    var staged = [];
    var FIC = '<span class="fic"><svg viewBox="0 0 24 24">'
      + '<path d="M14 3v4a1 1 0 0 0 1 1h4"/>'
      + '<path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2"/>'
      + '</svg></span>';
    /* 0807：每张给个自己的号（data-k）。drawStage 是整条 innerHTML 重建的，
       没有号的话「撤掉一张」会让剩下的全体重播一次入场 —— 那就成了抽搐。 */
    var stageSeq = 0;
    function drawStage() {
      if (!bar) return;
      bar.hidden = !staged.length;
      var had = {};
      bar.querySelectorAll('.chip[data-k]').forEach(function (c) { had[c.getAttribute('data-k')] = 1; });
      bar.innerHTML = staged.map(function (s, i) {
        if (!s.k) s.k = ++stageSeq;
        return '<div class="chip" data-k="' + s.k + '">'
          + (s.kind === 'img' ? '<img src="' + s.dataURL + '" alt="">' : FIC)
          + '<span class="nm">' + esc(s.name || '图片') + '</span>'
          + '<button class="x" data-drop="' + i + '" aria-label="不发了">'
          + '<svg viewBox="0 0 24 24"><path d="M18 6l-12 12"/><path d="M6 6l12 12"/></svg>'
          + '</button></div>';
      }).join('');
      bar.querySelectorAll('.chip[data-k]').forEach(function (c) {
        if (!had[c.getAttribute('data-k')]) c.classList.add('fresh');
      });
    }
    if (bar) bar.addEventListener('click', function (e) {
      var b = e.target.closest('[data-drop]'); if (!b) return;
      staged.splice(+b.getAttribute('data-drop'), 1);
      drawStage();
    });

    /* ══════════════ 输入条 ══════════════ */
    /* 输入框：回车只换行 */
    ta.addEventListener('input', function () {
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 110) + 'px';
    });

    function go() {
      if (busy) { emit('stop'); setBusy(false); if (opts.onStop) opts.onStop(); return; }
      var t = ta.value.trim();
      if (!t && !staged.length) return;   /* 0805：staged 现在是一排 */
      ta.value = ''; ta.style.height = '';
      emit('sent', {text: t});
      if (opts.onSend) opts.onSend(t);
    }
    if (send) {
      /* 发送键：钉死的那条 —— 按下 .9，回弹到 1.06，落回 1 */
      send.addEventListener('click', function () {
        send.classList.remove('pop');
        void send.offsetWidth;          // 强制重排，连点也能重放
        send.classList.add('pop');
      });
      send.addEventListener('click', go);
    }
    /* ★ 0810 翻案：**回车换行，不再是发送**。
         上一版这里定的是「回车＝发送、⇧回车换行」；在手机上打字的时候，
         回车当发送用会一直把半句话推出去。改成：
           回车 = 换行（浏览器默认，我们什么都不做）
           发送 = 点右边那颗按钮；桌面另给 ⌘/Ctrl+回车，习惯键盘的时候不用挪手
       两条旧规矩都留在这儿，免得哪天又被翻回去。 */
    ta.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || e.isComposing) return;
      if (e.metaKey || e.ctrlKey) { e.preventDefault(); go(); }   /* ⌘/Ctrl+回车才发 */
      /* 其余一律放行 —— 让它换行 */
    });

    return {
      emit: emit, say: say, splitSay: splitSay, setStat: setStat, setBusy: setBusy,
      moveActs: moveActs, toast: toast, toolNote: toolNote, clearDemo: clearDemo,
      sheetOpen: sheetOpen, stage: function (list) { staged = list || []; drawStage(); },
      fmtTS: fmtTS, toolCN: toolCN, toolDid: toolDid,
      busy: function () { return busy; }
    };
  }

  /* ══════════════ 演一轮 ══════════════
     把一段**编好的**对话按真实节奏喂进 emit()：
       送出去了 → ✓到他那了 → 翻着记忆想你这句 → 正在… → 想好了在写 → 一句句吐 → 脚注
     真接后端的时候，把这个换成你自己的事件源即可，界面这一层一个字都不用动。 */
  Chat.play = function (chat, turn, done) {
    var steps = [];
    steps.push([260,  function () { chat.emit('recv'); }]);
    /* 要动手翻东西的那种，状态条说的是「翻着记忆想你这句…」；不翻的就只是「在想…」 */
    steps.push([520,  function () { chat.emit('stage', {text: (turn.tools && turn.tools.length) ? '翻记忆' : ''}); }]);
    (turn.tools || []).forEach(function (t) {
      steps.push([700, function () { chat.emit('tool', {name: t.name, detail: t.detail}); }]);
      steps.push([900, function () { chat.emit('tool', {name: t.name, done: true}); }]);
    });
    steps.push([600,  function () { chat.emit('os'); }]);
    chat.splitSay(turn.text).forEach(function (seg, i) {
      steps.push([i === 0 ? 700 : 620, function () {
        chat.emit('say', {text: seg, think: turn.think, first: i === 0});
      }]);
    });
    if (turn.tools && turn.tools.length) {
      steps.push([340, function () { chat.emit('meta', {tools: turn.tools}); }]);
    }
    steps.push([120, function () { chat.emit('end', {ok: true}); if (done) done(); }]);

    var i = 0;
    (function next() {
      if (i >= steps.length) return;
      var s = steps[i++];
      setTimeout(function () { s[1](); next(); }, s[0]);
    })();
  };

  global.Chat = Chat;
})(window);
