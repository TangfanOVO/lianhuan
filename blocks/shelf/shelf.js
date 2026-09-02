/* 书房 · 书脊 —— 把一架书目画成书架
   ════════════════════════════════════════════════════════════════════
   零依赖。给它一份书目，它画出书架：书立着、板子一格一格厚，
   上层右边横躺着一本、工具那格站着一个机器人摆件、在读那本露一条书签。
   点一本＝进那个入口。

   ★ 尺寸、板厚、花纹、书目，**全部照搬原型稿那一架，一个数都没改**：
     · 板子厚度是原稿一格一格手写的（13 / 10 / 9 / 9）——不是算出来的。
       没给 `plank` 时才退回旧的 `8 + 本数`，那只是兜底。
     · 躺下的书：长度就是它站着时的高度（一本书倒下来不会变短）；
       书身 rotate(90deg)，名字**倒着串**才读得顺（见 laid() 里那一行）。
     · 机器人不是一本书 —— 它是 46×46 的摆件，按下去是「被戳了一下」，
       跟书那套「被抽出来」是两种手感（CSS 里 .sf-bot vs .sf-spine）。
     · 书头色带压住花纹，用 card 兜底混出不透明的一层（别用半透明的 maple-soft）。

   ★ 门的语义照旧：一本书＝一扇门，属性名 `data-sub` / `data-open` / `data-cell`
     一个没改，所以原来接这些属性的代码照样能开门。onPick 是额外给的方便。
   ════════════════════════════════════════════════════════════════════ */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Shelf = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /* 六种花纹，对应 shelf.css 里的 .sf-plain / .sf-rule / … */
  var PATTERNS = ['plain', 'rule', 'rule2', 'dot', 'hatch', 'grid'];

  /* 一本书的默认尺寸。原稿里每本各有各的比例，这只是没给值时的兜底。 */
  var DEF = { w: 50, h: 176, pattern: 'plain', headBar: 13, head: 'soft' };

  /* 线条图标全部内联（Tabler，MIT，见仓库 UPSTREAM.md）。
     ★ 机器人那枚是原稿里手画的线稿，不是任何公司的吉祥物。 */
  var ICON = {
    book: '<svg class="i" viewBox="0 0 24 24">'
        + '<path d="M19 4v16h-12a2 2 0 0 1 -2 -2v-12a2 2 0 0 1 2 -2h12"/>'
        + '<path d="M19 16h-12a2 2 0 0 0 -2 2"/><path d="M9 8h6"/></svg>',
    chevDesk: '<svg class="i" viewBox="0 0 24 24" style="width:17px;height:17px;color:var(--hint)">'
        + '<path d="M9 6l6 6l-6 6"/></svg>',
    mail: '<svg class="i" viewBox="0 0 24 24" style="width:19px;height:19px;color:var(--maple);flex:none">'
        + '<path d="M3 7a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v10a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-10"/>'
        + '<path d="M3 7l9 6l9 -6"/></svg>',
    chevOut: '<svg class="i" viewBox="0 0 24 24" style="width:16px;height:16px;color:var(--hint)">'
        + '<path d="M9 6l6 6l-6 6"/></svg>',
    /* 摆件那张脸：脑袋、两只 V 形眼睛、两只耳朵、脖子、梯形底座 */
    bot: '<svg class="sf-botface" viewBox="0 0 40 40" aria-hidden="true">'
        + '<rect x="8.5" y="7" width="23" height="18.5" rx="3.5"/>'
        + '<path d="M14.5 14.2l2.2 2.4l2.2 -2.4"/>'
        + '<path d="M21.1 14.2l2.2 2.4l2.2 -2.4"/>'
        + '<path d="M6.2 13.5v5"/><path d="M33.8 13.5v5"/>'
        + '<path d="M20 25.5v3.2"/>'
        + '<path d="M15.6 28.7h8.8l2.6 4.3h-14z"/></svg>'
  };

  /* ══ 默认 config ＝ 原型稿那一架，一本不多一本不少（对外就是 `Shelf.HOME`）══
     四格：一起做的（四本立着 ＋ 梗典横躺）/ 我一个人的 / 工具（工作本 ＋ 机器人）/ 捡到的。
     板厚 13 / 10 / 9 / 9 是手写的。想换书目就自己传一份，别改这里。 */
  var HOME = {
    shelves: [{
      label: '一起做的', plank: 13,
      books: [
        { id: 'read',   name: '在读',     w: 58, h: 190, pattern: 'plain', headBar: 15, current: true, sub: '一起看书' },
        { id: 'notes',  name: '共读笔记', w: 50, h: 168, pattern: 'rule',  headBar: 11, twin: true,     sub: '共读笔记' },
        { id: 'listen', name: '唱片',     w: 46, h: 178, pattern: 'dot',   headBar: 18,                 sub: '一起听' },
        { id: 'xhs',    name: '小红书',   w: 46, h: 200, pattern: 'hatch', headBar: 13, tag: true,      sub: '一起看小红书' }
      ],
      laid: [
        { id: 'meme', name: '梗典', w: 48, length: 170, pattern: 'dot', head: 'card2', headBar: 14, open: 'memepage' }
      ]
    }],
    bays: [
      { label: '我一个人的', plank: 10, books: [
        { id: 'fish', name: '钓鱼图鉴', w: 54, h: 182, pattern: 'grid',  head: 'card2', headBar: 12, cell: 'fish', open: 'fishpage' },
        { id: 'trip', name: '旅行手帐', w: 44, h: 164, pattern: 'rule2', head: 'card2', headBar: 16, twin: true,   open: 'tripspage' }
      ] },
      { label: '工具', width: 112, plank: 9, books: [
        { id: 'work', name: '工作本', w: 52, h: 172, pattern: 'plain', head: 'card2', headBar: 10, twin: true, sub: '工作本' }
      ], bot: { id: 'bot', name: '机器人', open: 'botpage' } },
      { label: '捡到的', plank: 9, marginLeft: 'auto', marginRight: '16px', books: [
        { id: 'code', name: '代码架', w: 46, h: 158, pattern: 'hatch', head: 'card2', headBar: 12, open: 'toolpage' }
      ] }
    ],
    /* 架子外头那两块：摊在桌上的那本、通别处的那扇门。它们不进 zoom（原稿也在 zone 外面） */
    desk: { title: '摊在桌上', note: '翻一下…' },
    out:  { jump: 'write', name: '信', where: '在记事' }
  };

  function el(tag, cls, style) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (style) e.setAttribute('style', style);
    return e;
  }

  /* 内联 SVG 字符串 → 元素。字符串全是上面写死的常量，不吃外部数据。 */
  function ico(markup) {
    var box = document.createElement('span');
    box.innerHTML = markup;
    return box.firstElementChild;
  }

  function faces(t) {
    return 'sf-' + (PATTERNS.indexOf(t.pattern) >= 0 ? t.pattern : 'plain')
         + (t.head === 'card2' ? ' sf-hc2' : ' sf-hsoft');
  }

  /* 门：属性名跟原稿一个字不改，接这些属性的老代码照样能开门 */
  function doors(node, t) {
    if (t.id) node.setAttribute('data-id', t.id);
    if (t.cell) node.setAttribute('data-cell', t.cell);
    if (t.sub) node.setAttribute('data-sub', t.sub);
    if (t.open) node.setAttribute('data-open', t.open);
  }

  function wire(node, t, onPick) {
    if (onPick) node.addEventListener('click', function () { onPick(t.id, t); });
  }

  /* 一本立着的书 */
  function spine(b, onPick) {
    var t = Object.assign({}, DEF, b);
    var btn = el('button', 'sf-spine ' + faces(t), 'width:' + t.w + 'px;height:' + t.h + 'px');
    btn.type = 'button';
    doors(btn, t);
    btn.appendChild(el('span', 'sf-hd', 'height:' + t.headBar + 'px'));
    if (t.twin) btn.appendChild(el('span', 'sf-hd2'));
    var nm = el('span', 'sf-nm');
    nm.textContent = t.name || '';
    btn.appendChild(nm);
    if (t.tag) btn.appendChild(el('span', 'sf-tag'));
    if (t.current) btn.appendChild(el('span', 'sf-rib'));      /* 在读那本露在外面的书签 */
    wire(btn, t, onPick);
    return btn;
  }

  /* 横躺在架子右边的那本：外壳是 长×厚，里头那层还是 厚×长 再转 90 度 */
  function laid(b, onPick) {
    var t = Object.assign({}, DEF, b);
    var len = t.length || t.h;                 /* 躺下来不会变短 */
    var btn = el('button', 'sf-laid', 'width:' + len + 'px;height:' + t.w + 'px');
    btn.type = 'button';
    btn.setAttribute('aria-label', t.name || '');
    doors(btn, t);
    var inner = el('span', faces(t),
      'width:' + t.w + 'px;height:' + len + 'px;'
      + 'left:' + ((len - t.w) / 2) + 'px;top:' + ((t.w - len) / 2) + 'px');
    inner.appendChild(el('span', 'sf-hd', 'height:' + t.headBar + 'px'));
    var nm = el('span', 'sf-nm');
    /* ★ 名字要**倒着串**：书身整个 rotate(90deg) 之后，竖排的第一个字会落到右边，
       不倒过来读出来就是反的（原稿里「梗典」写成「典梗」就是这么来的）。
       别再去 CSS 里给 .sf-laid .sf-nm 加一层反转 —— 两边都改就是双重反转。 */
    nm.textContent = (t.name || '').split('').reverse().join('');
    inner.appendChild(nm);
    btn.appendChild(inner);
    wire(btn, t, onPick);
    return btn;
  }

  /* 架子上的机器人摆件。★ 它不是一本书，所以不套 .sf-spine 那套「抽出来」的手感：
     书是被抽出书架（--pull 上移 ＋ 歪 1.4 度），它是被戳了一下（只抬 5px ＋ 歪 7 度）。 */
  function bot(b, onPick) {
    var t = Object.assign({}, b);
    var btn = el('button', 'sf-bot');
    btn.type = 'button';
    btn.setAttribute('aria-label', t.name || '机器人');
    doors(btn, t);
    btn.appendChild(ico(ICON.bot));
    wire(btn, t, onPick);
    return btn;
  }

  /* 一格架子：一排东西 ＋ 一块板 ＋ 一行小标。
     top＝上层那格（带 .sf-bay 的外边距）；下面那排的三格是裸 div，只有 flex 定位。 */
  function bay(cfg, onPick, top) {
    var style = '';
    if (!top) {
      style = 'flex:none';
      if (cfg.width) style += ';width:' + cfg.width + 'px';
      if (cfg.marginLeft) style += ';margin-left:' + cfg.marginLeft;
      if (cfg.marginRight) style += ';margin-right:' + cfg.marginRight;
    }
    var box = el('div', top ? 'sf-bay' : '', style);
    var row = el('div', 'sf-row');
    (cfg.books || []).forEach(function (b) { row.appendChild(spine(b, onPick)); });
    (cfg.laid  || []).forEach(function (b) { row.appendChild(laid(b, onPick)); });
    if (cfg.bot) row.appendChild(bot(cfg.bot, onPick));
    if (cfg.todo) {                            /* 虚线空位。原稿 0807 之后不用了，接口留着 */
      var t = el('div', 'sf-todo');
      var n = el('span', 'sf-nm');
      n.textContent = cfg.todo;
      t.appendChild(n);
      row.appendChild(t);
    }
    box.appendChild(row);
    /* ★ 板厚：原稿一格一格手写的（13 / 10 / 9 / 9）。没给就退回旧的「8 ＋ 件数」兜底。 */
    var n = (cfg.books || []).length + (cfg.laid || []).length
          + (cfg.bot ? 1 : 0) + (cfg.todo ? 1 : 0);
    box.appendChild(el('div', 'sf-plank', 'height:' + (cfg.plank || (8 + n)) + 'px'));
    if (cfg.label) {
      var lab = el('div', 'sf-lab');
      lab.textContent = cfg.label;
      box.appendChild(lab);
    }
    return box;
  }

  /* 摊在桌上＝当前在读那本，一按直接进正文（不用先过书架）。
     ★ 原项目那份在 <i> 上挂着 id="deskBook" 供回填；积木不注册裸 id，
       要回填自己拿 host.querySelector('.sf-desk i').textContent = … */
  function desk(cfg, onPick) {
    cfg = cfg || {};
    var btn = el('button', 'sf-desk');
    btn.type = 'button';
    btn.setAttribute('data-desk', '');
    btn.appendChild(el('span', 'edge'));
    var ic = el('span', 'ic', 'margin-bottom:0;margin-left:6px');
    ic.appendChild(ico(ICON.book));
    btn.appendChild(ic);
    var mid = el('span', '', 'flex:1');
    var b = document.createElement('b');
    b.textContent = cfg.title || '摊在桌上';
    var i = document.createElement('i');
    i.textContent = cfg.note || '';
    mid.appendChild(b); mid.appendChild(i);
    btn.appendChild(mid);
    btn.appendChild(ico(ICON.chevDesk));
    if (onPick) btn.addEventListener('click', function () { onPick('desk', cfg); });
    return btn;
  }

  /* 别处的门：描边，不跟书房自己的东西抢 */
  function out(cfg, onPick) {
    cfg = cfg || {};
    var btn = el('button', 'sf-out');
    btn.type = 'button';
    if (cfg.jump) btn.setAttribute('data-jump', cfg.jump);
    if (cfg.name) btn.setAttribute('data-jumpname', cfg.name);
    btn.appendChild(ico(ICON.mail));
    var nm = document.createElement('b');
    nm.setAttribute('style', 'flex:1;font-size:14.5px;font-weight:600');
    nm.textContent = cfg.name || '';
    btn.appendChild(nm);
    var where = el('span', '', 'font-size:11.5px;color:var(--hint)');
    where.textContent = cfg.where || '';
    btn.appendChild(where);
    btn.appendChild(ico(ICON.chevOut));
    if (onPick) btn.addEventListener('click', function () { onPick(cfg.jump || 'out', cfg); });
    return btn;
  }

  /* ── 对外 ────────────────────────────────────────────────── */
  function Shelf(host, opts) {
    opts = opts || {};
    /* 没给书目就画默认那一架 */
    var cfg = (opts.shelves || opts.bays) ? opts : Object.assign({}, HOME, opts);
    var W0 = opts.canvasWidth || 408;          /* 原稿的内容宽。缩放以它为基准 */
    host.innerHTML = '';

    (cfg.shelves || []).forEach(function (c) { host.appendChild(bay(c, opts.onPick, true)); });

    if ((cfg.bays || []).length) {
      var row2 = el('div', 'sf-row2');
      cfg.bays.forEach(function (c) { row2.appendChild(bay(c, opts.onPick, false)); });
      host.appendChild(row2);
    }

    /* ★ 整块等比缩放，不重排。原稿按 440 画布画的（内容宽 408），
         手机上只有 361～398 —— 一个个改尺寸会失真，所以整体 zoom。
       ⚠ 隐藏时量到的宽是 0，照着 0 算会把整架书缩没 —— 小于 100 一律不理。 */
    function fit(w) { if (w > 100) host.style.zoom = Math.min(1, w / W0); }
    var watch = opts.fitTo || host.parentElement;
    if (watch && typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(function (es) { fit(es[0].contentRect.width); }).observe(watch);
      fit(watch.clientWidth - 32);             /* 先按 padding 折一次，别等回调 */
    }
    return { fit: fit, el: host };
  }

  /* 架子外头那两块单独取用 —— 它们在原稿里也在 zoom 之外，别塞进 host。 */
  Shelf.desk = desk;
  Shelf.out = out;
  Shelf.HOME = HOME;
  return Shelf;
});
