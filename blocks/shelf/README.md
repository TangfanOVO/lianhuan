# 书房 · 书脊

一本书就是一个入口。九宫格换成三排真书架 —— 书立着、按下去会被抽出来一点、
板子一格一格厚、上层右边横躺着一本、工具那格站着一个机器人摆件、在读那本露一条书签在外面。

| 件 | 是什么 |
|---|---|
| [`shelf.css`](shelf.css) | 书脊、板子、花纹、手感。**跟应用里那一段是同一份**，见下面「两份的事」 |
| [`shelf.js`](shelf.js) | 渲染器。零依赖，给一份书目画出书架；不给就画默认那一架 |
| [`demo.html`](demo.html) | 双击就能看。里头那一架是**原型稿的 markup 原样照搬**，脚本用默认 config 重画一份一样的 |

## 用它

```html
<link rel="stylesheet" href="../base/tokens.css">
<link rel="stylesheet" href="shelf.css">
<div id="shelfzone"></div>
<div id="extras"></div>
<script src="shelf.js"></script>
<script>
// 什么都不传 ＝ 画默认那一架（Shelf.HOME）
Shelf(document.getElementById('shelfzone'), {
  fitTo: document.querySelector('.wrap'),      // 跟着谁缩放（默认取父元素）
  onPick: (id, item) => location.hash = id,
});

// 架子外头那两块单独取用 —— 它们不进 zoom
var x = document.getElementById('extras');
x.appendChild(Shelf.desk(Shelf.HOME.desk, () => openCurrentBook()));
x.appendChild(Shelf.out(Shelf.HOME.out,  () => go('write')));
</script>
```

换自己的书目就传一份 config（传了 `shelves` 或 `bays` 就完全按你的来）：

```js
Shelf(host, {
  shelves: [{                                  // 上层：一格，通栏
    label: '一起做的', plank: 13,               // ★ 板厚是手写的，不是算出来的
    books: [{ id:'read', name:'在读', w:58, h:190, pattern:'plain', headBar:15,
              current:true, sub:'一起看书' }],
    laid:  [{ id:'meme', name:'梗典', w:48, length:170, pattern:'dot',
              head:'card2', headBar:14, open:'memepage' }],   // 横躺在这格右端
  }],
  bays: [                                      // 下面那排：几格并排
    { label:'工具', width:112, plank:9,
      books:[{ id:'work', name:'工作本', w:52, h:172, head:'card2', headBar:10, twin:true }],
      bot:  { id:'bot', name:'机器人', open:'botpage' } },     // 摆件，不是书
    { label:'捡到的', plank:9, marginLeft:'auto', marginRight:'16px',
      books:[{ id:'code', name:'代码架', w:46, h:158, pattern:'hatch', head:'card2' }] },
  ],
});
```

### 一件东西

| 字段 | 意思 |
|---|---|
| `id` `name` | 认它用的 id、书脊上竖着写的名字 |
| `w` `h` | 厚度、高度（px）。**不同的书给不同的数，一排才像真书架** |
| `pattern` | `plain` `rule` `rule2` `dot` `hatch` `grid` 六种封面花纹 |
| `headBar` | 书头那道色带多高 |
| `head` | `soft`＝跟重点色走 · `card2`＝素的 |
| `twin` | 书头下面再加一道细带（精装书那种） |
| `tag` | 底部一条重点色标记 |
| `current` | 在读 —— 顶上露一条书签 |
| `length` | 只有横躺（`laid`）的书用；不给就等于 `h`（**书倒下来不会变短**） |
| `sub` `open` `cell` | 这本书通向哪儿 —— 原样落成 `data-sub` / `data-open` / `data-cell` |

### 一格架子

| 字段 | 意思 |
|---|---|
| `label` | 板子底下那行小标 |
| `books` | 立着的那几本 |
| `laid` | 横躺在右端的那本（`margin-left:auto` 自己顶到右边） |
| `bot` | 机器人摆件。**它不是一本书**，见下面第 ③ 条 |
| `plank` | 板子多厚（px）。**原稿是一格一格手写的**：13 / 10 / 9 / 9 |
| `width` `marginLeft` `marginRight` | 下面那排并排时的排布 |
| `todo` | 虚线空位（原稿 0807 之后不用了，接口留着） |

`Shelf.desk({title, note})` 摊在桌上那本、`Shelf.out({jump, name, where})` 别处的门 —— 各返回一个按钮元素。

## 四件不显眼但别改的事

**① 板子的厚度是手写的**，不是算出来的：13 / 10 / 9 / 9。
书多的架子板子更厚 —— 这一下是整块东西看起来像真家具的原因，但具体几 px 是一格一格定的。
没给 `plank` 时才退回旧的 `8 ＋ 件数` 兜底，那只是别让人传漏了就没板子。

**② 躺着那本的名字要倒着串。** 整本 `rotate(90deg)` 之后，竖排的第一个字会落到右边；
不倒过来读出来就是反的（原稿里「梗典」写成「典梗」就是这么来的）。
`shelf.js` 里那一行 `.split('').reverse().join('')` 就是干这个的。
⚠ **别再去 CSS 里给 `.sf-laid .sf-nm` 加一层 `writing-mode:horizontal-tb` ＋ `rotate(-90deg)`**——
0902 加过一次，跟这儿的倒串撞成双重反转，字反而认不出。二选一，这儿选的是原稿那条。

**③ 机器人不是一本书。** 它是 46×46 的摆件（`.sf-bot`，一枚内联 SVG 线稿），手感跟书是两回事：
书按下去是「被抽出书架」（`--pull` 18px 上移 ＋ 歪 1.4 度），
它按下去是「被戳了一下」（只抬 5px ＋ 歪 7 度）。同一条 `--spring-pop` 曲线，不同的语义。
别为了省事把它做成一根书脊。

**④ 尺寸是比例，不是像素。** 原稿按 440 画布画的（内容宽 408），手机上只有 361～398。
一个个改尺寸会失真，所以**整块等比 zoom**（`shelf.js` 末尾那几行）。
⚠ 元素隐藏时量到的宽是 0，照着 0 缩会把整架书缩没 —— 小于 100 一律不理。
`.sf-desk` / `.sf-out` 在 zoom 之外（原稿里它们也在架子容器外面），所以它们自己撑满宽度。

## 两份的事（改之前先读）

`shelf.css` 跟应用 `index.html` 里那一段是**同一份**。应用是单文件零构建，没法引外链，
所以物理上存了两份。**改任何一处都要两边一起改** —— `tests/test_core.py::test_shelf_css_is_identical_in_both_places`
钉了一条，两份对不上就红。

## 名字的一层桥

积木层管重点色叫 `--accent`，应用那边从第一版起就叫 `--maple`。
`base/tokens.css` 里搭了别名（`--maple: var(--accent)`），所以**只拿积木走的人不用改一行**；
换配色只改 `--accent` 一处。

除此之外要的 token：`--card --card2 --ink --sub --hint --line --thread --cast --shadow --shadow-lift`
`--maple-soft --pull --press --spring-pop --r`，都在 `base/tokens.css` 里。

## 出处

书架这套（书脊、板子、花纹、板厚、书目、机器人线稿）是原创。
`.sf-desk` / `.sf-out` 里那几枚线条图标来自 **Tabler Icons（MIT）**，已全部内联，署名见仓库 `UPSTREAM.md`。
