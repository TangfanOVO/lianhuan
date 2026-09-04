# home —— 一整页主页 · **六种排法**（当换肤的画布用）

一个**完整的假主页**：顶栏、在一起的天数、便签、正在听、六格 tile、健康、
四颗小圆入口、空间、底栏（4 个去处 ＋ 中央一片家徽）。

同一份内容有**六种排法**，在 demo 顶上那排按钮里切：

| 排法 | 长什么样 | 物理在哪 |
|---|---|---|
| **方块** `tiles` | 卡片一格一格排着，中间有缝线穿过 | 纯 CSS，零 JS |
| **垂丝** `drape` | 卡片挂在从上边垂下来的丝线上，风一吹会飘 | [`../physics/silk-rope.js`](../physics/silk-rope.js) |
| **横渡** `blinds` | 同上，线改成左右穿插 | 同上 |
| **灯串** `lantern` | 同上，线上挂灯；**会强制切暗色**（纸底上那点暖光看不见） | 同上 |
| **纸夹** `paper` | 七张纸夹在桌面上，会翻角、会飘 | [`../physics/paper-clip.js`](../physics/paper-clip.js) |
| **散摞** `stack` | 五摞纸片散在桌上，点一摞它摊开 | [`../physics/stack.js`](../physics/stack.js) |

方块那一版底下还有一颗「**排一排主页**」：按住往上下拖，松手就是新顺序，存在本机。

它不是给你直接上线的页面，是给「配色与明暗」那种预览页当**画布**用的：
色板上摆一堆色块，谁也看不出换了之后长什么样；把整页主页摆在旁边，按一下就全变了 ——
而且**六种排法下都跟着变**，从顶栏的头像圈到底栏的枫叶，一个不落。

**页面里的字全是编的** —— 名字、天数、留言、歌、书、步数、空间那一句，
都是随手写的占位，不对应任何真人。页面上自己写着这句话（开关条上一行 ＋ 方块底下一行），
别把它删掉。

顶栏那个名字默认是中性的「伙伴」，写在 `demo.html` 开头那一行 `var NAME = '伙伴';` ——
**整页只有这一处**，改它就换成你自己的名字（头像小圆里那个字自动取名字的头一个字）。
`home.css` 里一个名字也没有。

零依赖、零网络，双击 `demo.html` 就能看。

---

## 这一块有哪几个文件

| | 干什么 |
|---|---|
| `demo.html` | 整页的 markup ＋ demo 自己那点外壳（换主题／换排法的开关条） |
| `home.css` | 方块那一版的全部样式 ＋ 六种排法共用的那几条（§10） |
| `home.js` | 换排法 ＋ 排一排。**一行物理都没有** |
| `sort.css` | 「排一排主页」那一页 |

## 拿去用

```html
<link rel="stylesheet" href="../base/tokens.css">
<link rel="stylesheet" href="../physics/silk-rope.css">   <!-- 要丝线那三种才需要 -->
<link rel="stylesheet" href="../physics/paper-stack.css"> <!-- 要纸夹／散摞才需要 -->
<link rel="stylesheet" href="home.css">                   <!-- ★ 必须排在上面两份之后 -->
<link rel="stylesheet" href="sort.css">                   <!-- 要「排一排」才需要 -->
…
<script>
  window.__paperStageHost = '[data-home="paper"]';
  window.__stackStageHost = '[data-home="stack"]';
</script>
<script src="../physics/silk-rope.js"></script>
<script src="../physics/paper-clip.js"></script>
<script src="../physics/stack.js"></script>
<script src="home.js"></script>
```

markup 整段抄 `demo.html`（那就是这一页的全部结构，没有别的地方藏东西）。
**只要方块一种排法的话**，physics 那五行全不用引，`home.js` 也不用 —— 方块是纯 CSS 的。

页面要给 `home.js` 的东西（少哪个就少哪种排法，不报错）：

```
.app            壳，position:relative
#body           滚动容器（id 别改名，syncPad 和丝线的 chrome.body 都认它）
.app > .top     顶栏      .tabbar  底栏
#p-home 里四个排法容器：[data-home="tiles" | "silk" | "paper" | "stack"]
.app 上两层底纸墙：[data-wall-paper] [data-wall-stack]
开关：任意多个 [data-home-style="tiles|drape|blinds|lantern|paper|stack"]
排一排：[data-sort] 那颗按钮 · #sortpage · #sortlist · [data-close="sortpage"]
```

对外：`window.Home = {layout, setLayout, syncPad, rebuild, repaint, applyOrder}`；
切完排法在 `document` 上派一个 `home:layout` 事件（`detail.layout`）。

**进去** 六种排法走同一个口子：页面上定义 `window.openEntry(name)`，返回 `true` 表示
「这一下我接管了」。丝线走 `home.js` 的 `onOpen`，纸夹和散摞走它们自己那两块 ——
两边都是先找这个函数。丝线另外还在舞台上派 `silk:open` 事件，爱接哪个接哪个。

## 换肤

一页里没有一个写死的颜色（唯一的例外见下），全部走 `base/tokens.css` 的 token。

```js
document.documentElement.setAttribute('data-theme', 'dark');  // 亮 / 暗 / 不写＝跟随系统
Accent.set('#6f8f6a');                                        // 换重点色，见 base/accent.js
Home.repaint();                                               // ★ 换完重点色叫一下
```

`Home.repaint()` 那一行不是可选的：丝线的颜色是**建线那会儿钉在 path 上的**，
不重刷一遍，线不会跟着重点色走。

> 唯一没走 token 的颜色：`.disc`（转碟）里的 `#241f1c`，那是黑胶盘本身的墨色 ——
> 唱片在亮皮暗皮下都是黑的，它不该跟着换肤走。原件就是这个值，照搬未改。

**灯串是个例外**：它会强制切暗色，出来时把原来那套还回去。这件事**只有一个主人**，
在 `silk-rope.js` 的 `applyMode()` 里 —— 所以 `home.js` 离开丝线时也会叫一次 `setMode`，
它才有机会还回去。别在自己的页面里再记一份「原来是哪套主题」，两处各记一份必然打架。

## 存在本机的键

| 键 | 谁写的 | 存什么 |
|---|---|---|
| `silk.home` | `home.js` | 上次选的排法 |
| `home.order` | `home.js` | 方块那一版的板块顺序 |
| `silk.wind` | 三块物理共用 | 风力（0～2.4，默认 0.7） |
| `silk.mode` `silk.drag` `silk.pos.*` | `silk-rope.js` | 见 physics 那份 README |

## ⚠️ 几条真会咬人的

| 地方 | 为什么 |
|---|---|
| **丝线那版必须是 13 张 `.silkcard`** | 默认线形里 `pos` 是 13 个手调出来的坐标，`ropes[].via` 用的是**数组下标**。`cards.length < 13` 会让整块提前退出，删一张后面每张都错位一格。要撤一个入口，**给它加 `hidden`，不许删 DOM**。 |
| 画布的父容器必须是 `.hstage` | `paper-clip.js` / `stack.js` 的 `fit()` 量的是 `host.parentElement.clientWidth`，还要往它身上写 height。中间少一层、或者那一层写死 440 宽，`k` 就永远等于 1，再窄的屏也不缩。 |
| `__paperStageHost` / `__stackStageHost` | 两块物理每帧拿这个选择器问「我现在看得见吗」。不设就只看舞台自己 —— 切走了还在空转。 |
| `.body` 上那三个 class 换页也要重算 | `nopad` / `fullbleed` / `homefull` 都挂在**所有页共用**的 `.body` 上。切到别的页不摘掉，那一页的内容会贴到最左边、连上下滚都被 `overflow` 锁死。宿主换页时调一次 `Home.syncPad()`。 |
| `.app` 的 `overflow:hidden; overflow:clip` 两行并排 | `hidden` 只是不给滚动条，**元素本身仍是滚动盒**，手指照样能把整页推走一屏（「排一排」那一页就停在右边一屏处）。`clip` 才是「不产生滚动盒」。老浏览器停在 `hidden`。 |
| `.body` 的 `overflow-x` 显式钉死 | 只写 `overflow-y`，另一轴就从 `visible` 被顶成 `auto` —— 白送一条横向滚动。 |
| `.thread path` 的 `vector-effect:non-scaling-stroke` | 缝线用了 `preserveAspectRatio="none"`，不加这条，SVG 一被横向拉伸笔画粗细就变形。 |
| `.disc` 默认 `animation-play-state:paused` | 一直转的圆盘看着就是个加载菊花，会被当成程序卡住了没响应。真在放歌才加 `.disc.on`。 |
| `.top .me` 必须带 `.top` 限定 | `me` 是个到处在用的类名（聊天气泡也叫 `.msg.me`）。裸写会把 999px 胶囊漏到别的地方去。 |
| `.sortitem` 的 `touch-action:none` | 不写它，手指在条目上一竖着划会先被判成滚页面，`pointermove` 直接断掉 —— 拖不动。 |
| 底栏就 4 个 tab | 不是随便定的：Material 3 说 3–5，微信说不超过 4，Apple HIG 说不许有溢出 tab、底栏放**去处不是动作**。 |

## 「排一排」认行的规矩

拖的是**行**，不是单张卡：一个大纸条、一张独占的卡、或者并排两块的 `.grid` 各算一行，
每行连同它后面那根 `.thread` 连线一起搬 —— 版式（哪些成对、哪些独占、线怎么穿）一点不散。

跳过这几个，它们不是板块：

- `.daycount`（顶上那个大数字）
- `[data-sort]`（最底下那颗「排一排」按钮本身）
- `.thread`（线跟着它前面那行走）
- `.fakenote`（「这些字都是编的」那一行 —— 这一条是积木自己加的，原件里没有）

清单是**打开那一下照主页此刻的真实样子现生成的**，所以以后往方块里加了新格子，
它自己会出现在清单里，不用再手写死一份。名字取 `data-sub`（那才是这一格叫什么），
拿卡片里的标题当名字会出现「白墙」「纸上的河」这种，看不出是哪一格。

## demo 外壳做过的两处让步（**不属于这块积木**）

`demo.html` 顶上那条换主题／换排法的开关条是原件里没有的东西，它吃掉一截高度，
所以 demo 自己的 `<style>` 里有两条补偿 —— `home.css` 一个字没改：

1. **`--demoh`**：开关条的真实高度量出来写进 CSS 变量，`.app` 从 `100dvh` 里减掉它。
   不减，底栏就整条落到屏幕外面。
2. **纸夹／散摞在 demo 里竖着能滚**：原件的 `.body.nopad` 是 `clip`（主页钉死一屏，
   参考机型 440×894 正好装得下 748 的画布）。这一页头上多了开关条，那点余量没了，
   与其硬裁不如让它滚 —— physics 那两个 demo 撞到同一件事，处理办法也是这个。

真上线时这两条都不需要：壳上面没有别的东西。

## 照搬自哪儿

结构和样式整段搬自应用那半边跑了几个月的原型（`proto.html`），每一节都标了原件行号：

| | 原件 |
|---|---|
| 顶栏 / 方块 / 纸夹 / 散摞 / 丝线 / 底栏 markup | `2183-2212` / `2215-2341` / `2342-2433` / `2434-2441` / `2442-2463` / `2787-2804` |
| 六颗排法按钮（属性和文案一个字没动） | `3064-3072` |
| `applyHome()` / `syncPad()` | `12497-12574` |
| 「排一排」那一页 | `4060-4086` |
| 「排一排」的拖拽和落位 | `5478-5595` |
| `.body.nopad` / `.body.fullbleed` / `.app.homefull` | `343-378` / `361-364` / `231` |

纸夹的七张纸、散摞的五摞卡、两层各 135 张的底纸墙，是从
[`../physics/demo-paper.html`](../physics/demo-paper.html) 和
[`../physics/demo-stack.html`](../physics/demo-stack.html) **整行搬的**（那两份本身也是
从原件平移过去的）—— 位置、转角、透明度、胶带、毛边，一个数没动。重画一定不对。

没有一处是这儿新画的，除了：

- `.fakenote` —— 页面底下那行「这些字都是编的」。原件那一页装的是真数据，
  搬进开源积木得把这件事说清楚。
- `@keyframes spin` 补了一帧 `from`。原件是单帧 `to{…}`（浏览器里合法），
  但积木层自检要求每个 `@keyframes` 至少首尾两帧。行为完全相同。
- `[data-home="silk"] .silkstage{margin:0 -16px}` 加了个前缀。原件那条是裸的
  （`proto.html` 是整个应用的样式表，舞台只有主页一处）；积木可能被塞进别的容器，
  那时这 16px 是错的。

跟原件不一样的只有两处，都在 `home.js` 里写清了为什么：**灯串的暗色由谁管**（见上面「换肤」），
和**「排一排」多滤掉一个 `.fakenote`**（见上面「认行的规矩」）。

没搬过来的（要用的话去原件那几行整段取）：`.nwdoor`（出门走走那扇门）、
`.avapick`（设置页那个大圆）、`.iconbtn.withtx` —— 都不属于这一页。

## 许可

MIT（见同目录 `LICENSE`）。

底栏中央那片枫叶是 **Font Awesome Free 6 · canadian-maple-leaf**，
Icons 走 **CC BY 4.0**，署名在仓库 `UPSTREAM.md`。它的 path 不在这块里，在 `base/crest.js`。
线条图标是 **Tabler Icons**（MIT）。

## 收起某几块（0904）

「排一排主页」里每行右边那颗眼睛：**从主页收起 / 放回**。她的原话：
「有人不需要健康什么的，让他们自己关」。

- **只藏不删。** 收起来的那一行**留在清单里**（变淡、划掉），随时点回来；数据一个字没动。
- 存本机 `home.hidden`（一串 `data-blk`），刷新还在。
- 用的是 `hidden` 属性，不是 `display:none` —— 垂丝/横渡/灯串那三种排法的绳子是照
  DOM 里挂着的卡算的，[`../physics/silk-rope.js`](../physics/silk-rope.js) 认的正是 `hidden`，
  认得出来才不会在绳上留一个空尖角。
- 收完会叫一次 `silk.rebuild()` / `paperFit()` / `stackFit()` —— 卡少了，几何要重量。
- 对外：`window.Home.applyHide()`（宿主自己改了 `home.hidden` 之后叫一下）。

★ **只管方块那一版。** 另外五种排法各有各的坐标，不参与。
