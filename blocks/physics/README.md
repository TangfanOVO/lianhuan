# 物理

会动的那些。都是**只算不画**或者只用 SVG／CSS 画，不带渲染框架。

| 件 | 状态 | 依赖 | demo |
|---|---|---|---|
| [`silk-rope.js`](silk-rope.js) 丝线叠卡 | ✅ 能用 | 零依赖 | [demo.html](demo.html) |
| [`paper-clip.js`](paper-clip.js) 纸夹桌面 | ✅ 能用 | 零依赖 | [demo-paper.html](demo-paper.html) |
| [`stack.js`](stack.js) 散落成摞 | ✅ 能用 | 零依赖 | [demo-stack.html](demo-stack.html) |
| 枫叶水面 | ✅ 搬到 [`../water/`](../water/) 了 | p5.js（走 CDN） | [demo](../water/demo.html) |
| 记忆字云 | ⏸ 还在应用里，没拆出来 | 零依赖 | — |

（0830：水面和字云的来源都查实了 —— 水面是原创，字云的算法出自 ThreeUI（MIT，
版权行在 [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md)）。
「来源没核清」那个名单已经清零，水面先拆出来了，字云排在后面。）

---

## 丝线叠卡

卡片挂在绳子上，风一吹会飘。**不是排在网格里**——它们被线牵着。

- 手指扫过去，线会晃，卡片跟着荡
- 悬停某根线：它上面的卡片抬起来，别的线暗下去
- 点一下：那根线绷紧、顶栏底栏淡下去；**再点一下才真的进去**（两段式，防误触）
- 三种线形：`drape` 垂丝（从上边垂下）· `blinds` 横渡（左右穿插）· `lantern` 灯串（会强制暗色）
- 可以打开拖动：卡片拖到哪儿挂哪儿，位置记在本机

底下是 Verlet 积分 ＋ 位置约束，每帧四次松弛。渲染只有一条 SVG path 和 CSS transform。

### 用它

```html
<link rel="stylesheet" href="../base/tokens.css">
<link rel="stylesheet" href="silk-rope.css">

<div class="silkstage" data-stage>
  <svg data-svg aria-hidden="true"></svg>
  <div class="silkcard" data-card="0"><b>标题</b><i>小字</i></div>
  <!-- …一共 13 张 -->
  <div class="silkhint" data-hint></div>
</div>

<script src="silk-rope.js"></script>
<script>
  const silk = SilkRope(document.querySelector('[data-stage]'), {
    onOpen: el => location.href = el.dataset.href
  });
</script>
```

也可以不传 `onOpen`，听事件：

```js
stage.addEventListener('silk:open', e => console.log(e.detail.card));
```

两条路都会走 —— 事件好接好测，回调好写。

### 选项

| | |
|---|---|
| `onOpen(el)` | 点第二下时叫 |
| `chrome` | `{header, footer, shell, body}`，都可选。量高度用，以及聚焦时把顶栏底栏淡下去 |
| `isActive()` | 这块现在看得见吗。`false` 就停算（省电）。默认永远 `true` |
| `layout` | 覆盖默认线形 `{drape, blinds}` |
| `mode` | `'drape'` / `'blinds'` / `'lantern'` |
| `wind` | 0～2.4，默认 .7 |
| `drag` | `true` = 卡片能拖着走 |
| `storage` | localStorage 前缀，默认 `'silk'`；传 `null` 什么都不存 |

方法：`setWind` `setDrag` `setMode` `setThread` `reset` `rebuild` `repaint` `destroy`。

★ 换了重点色之后要叫一次 `repaint()`，线的颜色才跟着走。

### ⚠️ 关于「13 张」

默认线形里 `pos` 是 **13 个手调出来的坐标**，`ropes[].via` 用的是**数组下标**。

**删掉一张卡，后面每张都会错位一格。** 要改数量，`pos` 和 `via` 得一起改，
或者整套传自己的 `layout`。这不是 bug —— 那些坐标是一个一个挪出来的。

### 三个真咬过人的坑

**① `.silkcard` 的 transition 只许写那三个属性。** 写 `all` 会把 JS 每帧算出来的
`transform` 也套上过渡 —— 风立刻糊成一团，卡片像在泥里游。

**② 容器宽度是 0 时不能算。** 这块可能被放在还没展开的 tab 里、或者一个此刻不可见的面板里，
那时 `clientWidth` 是 0，所有几何都会算成零、卡片被扔到画外，看着像「渲染坏了」。
现在会挂一个 `ResizeObserver` 等到有宽度再算。

**③ `open` 回调里绝不能抛错。** 它跟 `styles()` 在同一行链上，抛了会把后面的活一起带走。
真栽过：`styles()` 里一个未定义变量，结果焦点清了、回调却从没跑过，看着像「点了没反应」。
现在两处都包了 try。

### 无障碍

`prefers-reduced-motion` 下只算 90 帧就停：让卡片落到位，然后不再动。


---

## 纸夹桌面

七张纸夹在桌面上，风一吹会翻角、会飘。点一下浮起，**再点一下才进去**（两段式，防误触）。

- 每张纸自己的相位和阵频（不按 index 排队），所以吹起的次序是乱的、节奏也各不相同
- 翻角是实时算的：`foldAt()` 给出折痕和背面的多边形，正文那一行会**自己让开**
  （算出最深折角时纸背在这一行的最左点，超了就省略号）
- 撕口锯齿、胶带、铁夹都是画出来的，没有图片素材

```html
<link rel="stylesheet" href="../base/tokens.css">
<link rel="stylesheet" href="paper-stack.css">
<div class="hcanvas" data-paperstage>…七张 [data-slip]…</div>
<script src="paper-clip.js"></script>
```

DOM 结构照 `demo-paper.html` 抄 —— 每张纸是一个 `<button data-slip>`，
里面按 z 序是：阴影 → 边 → 白面 → 折痕阴影 → 卷起的背 → 胶带 → 正文。
**位置、转角、毛边写在内联 style 里**（原设计稿就是那样导出的），几何靠 JS 每帧改 transform。

## 散落成摞

五摞纸片散在桌上。点一摞**它摊开**，再点一张才进去。

两条硬约束（原设计交接里用「⚠」标出来的，别动）：

1. **摞内转角必须单调递减。** 名字在纸左边、转轴在纸中心 —— 一负一正的相邻两张
   会让左边缘上下摆（净空那一项变成两头相减，约 −9px），再加多少步距都补不回来。
2. **五摞各是一层 `inset:0` 的全屏容器**，容器一律 `pointer-events:none`、只有纸片 `auto`。
   否则最后一层会把前面四层的点击区全盖住（当初只有最后一摞点得动）。

```html
<div class="hcanvas" data-stackstage>…五个 [data-stack]，每摞若干 [data-leaf]…</div>
<script src="stack.js"></script>
```

## 两块共用的一件事：舞台在不在

两个循环每帧都先问一句「舞台现在看得见吗」，看不见就跳过（省电，也避开
**在容器还隐藏时初始化 → 量到的宽是 0 → 几何全算成零** 那个经典坑）。

- 单独用：不用管，它看舞台自己
- 嵌进一个有多种排法的应用：把 `window.__paperStageHost` / `window.__stackStageHost`
  指到你那个排法容器的选择器，切走时它们就停机

★ 0830 之前这里写死找应用自己的容器 —— 积木单独拿出去时永远不初始化，
纸上的字被翻角那层整个盖住。**这就是「积木必须能单独跑」要用 demo 去验的原因。**

## 风

三块（丝线/纸夹/散摞）吃同一个键 `localStorage['silk.wind']`，默认 `0.7`。
往上推纸夹更飘；散摞那边有 `Math.min(1.4, W)` 的封顶，所以往上推看不出、往下拉才明显 ——
那个封顶是原设计定的，留着。
