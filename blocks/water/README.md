# 枫叶水面 · 滑动解锁

一片斜看下去的浅秋溪。叶子沉在河床上，另一些浮在水面，还有新的从天上飘下来、落水、荡开。
碰一下水就是一圈涟漪；风每隔几秒来一阵，推着涟漪也推着浮叶。
横着一拖，叶子被推开，锁就开了 —— 老式功能机「拨开落叶」那一下的现代版。

**全部是画出来的，没有一张图片素材。** 每片叶子都是运行时生成的矢量路径，
形状、颜色、叶柄长度每次开都不一样，所以整块东西只有几十 KB。

| 件 | 是什么 |
|---|---|
| [`maple-water.js`](maple-water.js) | 整个模拟和渲染。一个 IIFE，挂出 `window.MapleWater`（也支持 `module.exports`）。除 p5.js 外零依赖 |
| [`demo.html`](demo.html) | 一份完整能跑的锁屏：画布＋时钟＋滑动解锁，底下一条参数栏能现调现看。**双击就能看**，拿不准的时候读它 |

运行时依赖 **p5.js 1.9.x**（只用到 2D 画布那部分，不带 WebGL/sound 的构建也行）。
**p5 只走 CDN，不打包进仓库** —— 它是 LGPL，走 CDN 就够不着我们；顺带也省一兆。

> ★ 这一份跟内核用的是**同一个文件**。应用那边的开屏走 `/blocks/water/maple-water.js`，
> 不是自己另存一份 —— 各存一份迟早会漂移，到时候「只拿走积木」的人和用整个应用的人
> 看到的会是两套东西。

## 已知的一条（冷启动时偶发）

首次打开、p5 还是冷缓存的那一次，控制台**偶尔**会冒一条
`TypeError: Cannot read properties of undefined (reading 'width')`。

- **画面不受影响** —— 水面照常起来，滑动解锁照常。
- 0902 复核过：**改参数面板之前那一版也一样**，不是新引进来的。
- 热缓存下重现不了（同一页加一个 `window.onerror` 探针，连开都抓不到），
  所以**没有去猜着打补丁** —— 猜出来的守卫比这条警告更危险。
- 谁能稳定复现，欢迎开 issue 带上浏览器和是否首次加载。


## 用它

```html
<div id="stage" style="position:absolute;inset:0;touch-action:none"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.4/p5.min.js"></script>
<script src="maple-water.js"></script>
<script>
  const scene = MapleWater(document.getElementById('stage'), {
    density: 78, fall: 2.4, ripple: 1.1, wind: 1.8,
    windDirection: 'down', palette: 'autumn', paper: 3,
    onProgress: v => fill.style.transform = 'scaleX(' + v + ')',
    onUnlock:  u => root.classList.toggle('unlocked', u),
  });
  scene.relock();     // 重新锁上
  scene.destroy();    // 收工（关页面记得叫，别让它在后台烧电）
</script>
```

宿主元素要有真实宽高（画布铺满它，并跟着 `ResizeObserver` 走）。

## 旋钮

| 名字 | 默认 | 范围 | 干什么 |
|---|---|---|---|
| `density` | 78 | 0–90 | 水面上浮几片叶子。飘走了会从对岸补进来，所以这个数是**保持量**不是总量 |
| `fall` | 2.4 | 0–6 | 多久掉一片新的。0＝不掉，6≈每 0.1 秒一片（空中最多同时 10 片） |
| `ripple` | 1.1 | 0–4 | 涟漪压力。碰、拖、落叶、风，所有冲量的幅度都乘它。0＝死水，超过 2.5 水面开始显得毛躁 |
| `wind` | 1.8 | 0–4 | 风速。同时影响叶子漂移、涟漪播种和水面的整体摇摆 |
| `windDirection` | `down` | right/left/down/up | 风往哪吹 |
| `palette` | `autumn` | autumn/crimson/gold | 叶子配色 |
| `paper` | 3 | 0–3 | 宣纸纹的浓淡 |
| `grid` | 4.2 | — | 波场格子边长。**调大＝水纹变粗＋大幅省算力**（见下面「手机上卡」） |
| `sharp` | 1.5 | — | 像素密度倍率。同上 |
| `band` | 6 | — | 河床分带数。带越少台阶越明显 |
| `sway` | `off` | off/banded/whole | 河床晃不晃。**默认关死**，理由见下 |
| `reach` | 0.45 | 0–1 | 滑多远算到底（屏幕宽度的几成） |
| `onProgress(v)` | — | — | 每一个指针帧都会来一次，v 是 0–1。松手不到 1 会自己回弹 |
| `onUnlock(u)` | — | — | 解锁/重锁时来一次 |

## demo 里怎么调

demo 底下那条参数栏就是原项目设置页那两行搬过来的，四样：

| 界面上 | 实际动的 |
|---|---|
| **开屏画质** 顺滑 / 均衡 / 精细 | `grid` `sharp` `band` 三个一起走（见下表） |
| **枫叶** 全谱 / 偏红 / 偏金 | `palette` = `autumn` / `crimson` / `gold` |
| 滑杆 **密** | `density`，8–90 步长 2 |
| 滑杆 **急** | `wind`，0–4 步长 0.1 |

画质三档到底是哪几个数：

| 档 | `grid` | `sharp` | `band` |
|---|---|---|---|
| 顺滑 `smooth` | 7.5 | 1 | 4 |
| 均衡 `balanced` | 6 | 1 | 5 |
| 精细 `fine` | 4.2 | 1.5 | 6 |

性能三项**故意不单独暴露**：它们只有「更快还是更细」一个方向，
分开给等于逼人先理解波场网格。卡就往左推一档。

没设过的时候跟着屏幕走：窄屏（短边 <520）默认均衡＋`density 48`＋`fall 1.6`，
宽屏默认精细＋`density 78`＋`fall 2.4`。**滑杆显示的就是真会用上的那个默认值**，不摆样子。

选择存在 `localStorage['lh.water']`，刷新还在。
攒参数的顺序是：默认 → 减弱动效降级 → 存档覆盖 —— 手动拧过的风速会盖掉降级值，
这是照原项目的顺序来的。

**「现在看一眼」**：画质那三项要在建场时就定下来，热补没用，所以这颗按钮是
`destroy()` 之后拿当前这套参数重建一个。应用那边开屏只在启动时放一次，
所以那边这颗按钮做的是重新载入整页。

调试把手（控制台里直接用）：

```js
__water.opts()     // 这一刻会传给引擎的那份
__water.scene()    // 引擎手里那份（.config 是合并完的结果）
__water.peek()     // 等于按「现在看一眼」
```

## 两条真踩过的坑（原作者在手机上逐条调出来的）

**① 手机上卡。** 真凶是每帧的两处开销，跟「有没有做成可调」无关：
波场是 `W/grid` 个格子，`stepField` 和 `renderField` 每帧各走一遍全部格子；
再加上像素填充。窄屏（<520）换顺滑档：格子 17,177→8,505（少 50.5%），
像素 684,516→304,500（少 55.5%）。`grid` 只让水纹粗一点，**叶子和构图一点不动**。

```js
const narrow = Math.min(innerWidth, innerHeight) < 520;
{ density: narrow ? 48 : 78, fall: narrow ? 1.6 : 2.4,
  grid: narrow ? 6 : 4.2, sharp: narrow ? 1 : 1.5, band: narrow ? 5 : 6 }
```

**② 河床别晃。** 三档都试过：`banded` 分层晃有台阶（层与层之间跳，只有手机看得见 ——
3 倍屏＋`sharp:1`，一像素偏移被拉成三像素宽的锯齿）；`whole` 整片晃虽然每帧只画一次、
理论上更省，但实测就是卡。所以定案 `off`：河床钉死，水的活儿全交给涟漪和浮叶。

## 加载失败怎么办

p5 或这个文件没加载上 = **不许白屏**。应用那边的做法：
2.6 秒还没起来就退回「碰一下就进」，再 3.2 秒到点自己走。
你自己接的时候也留一条这样的退路。

## 减弱动效

```js
if (matchMedia('(prefers-reduced-motion: reduce)').matches)
  Object.assign(opts, { fall: 0, wind: 0.3, ripple: 0.6 });
```

## 出处

原创。设计与实现都是这个项目自己的，没有抄别人的作业。
