# 记忆字云

**一个字符 ＝ 一条记忆。** 它们聚成一个形状（枫叶 / 心 / 圆，**点一下画布就换下一片**），
彼此有关的连起来。切到「选记忆」之后，点一个字符，那条记忆显示在下面。

| 件 | 是什么 |
|---|---|
| [`glyph-cloud.js`](glyph-cloud.js) | **画布本身**：采样、形变、连线、透视、拾取。零依赖 |
| [`glyph-cloud.css`](glyph-cloud.css) | 画布容器和底下那张详情卡的样式 |
| [`glyph-ui.js`](glyph-ui.js) | **外壳层**：取数、详情卡、关联记忆、控制条、跟着换皮走。也是零依赖 |
| [`glyph-ui.css`](glyph-ui.css) | 外壳假设「宿主已经有」的那几条（`.subwrap` 的出血内边距等） |
| [`demo.html`](demo.html) | 160 条编出来的记忆 ＋ 整套外壳，双击就能看 |

两层可以分开用：只要画布就引前两个；要一整套现成的界面（详情卡、关联记忆、
缩放按钮、拖高矮）就把后两个也引上 —— 见下面「外壳层」。

## 用它

```html
<link rel="stylesheet" href="../base/tokens.css">
<link rel="stylesheet" href="glyph-cloud.css">
<div id="glyphwrap"><canvas id="glyphcv"></canvas></div>
<script src="glyph-cloud.js"></script>
<script>
const cloud = GlyphCloud.create(document.getElementById('glyphcv'), {
  memories: [{ id: 1, text: '第一次下雪那天', layer: 'L1', day: '2026-08-01' }, …],
  accent: '#b5533a',
  light: true,                    // 浅底还是深底 —— 字重会跟着换，见下
  onSelect: d => { … },           // ★ 给的是 {index, memory, glyph, relations}
  onReady: () => { … },           // ⚠ 它在 create() 返回**之前**调
});
cloud.setPick(true);              // 允许点选
cloud.setMemories(newList);       // 换一批
cloud.stats();                    // {n, links, w, h, cw}
cloud.shapeName();                // 这会儿聚成哪一片
cloud.destroy();                  // 收工
</script>
```

### 两个真的会绊人的地方

**① `onSelect` 给的不是记忆本身**，是 `{index, memory, glyph, relations}` ——
`memory` 才是你喂进去的那一条。（第一次接的时候我直接当记忆用了，页面上只显示出一个「·」。）

**② `onReady` 在 `create()` 返回之前调。** 那会儿你的 `const cloud` 还没赋上值，
在回调里碰 `cloud.xxx` 一定是 undefined。要报数就等下一帧，或者放进定时器。

## 外壳层（`glyph-ui.js` ＋ `glyph-ui.css`）

画布只管画。**图上不显示记忆正文** —— 图负责看见量、密度和关系，正文在图外面。
外壳层就是那个「外面」：一张详情卡、一栏关联记忆、一条控制条，加上跟着换皮走的配色。

它认死几个 id（样式也认这些 id），HTML 照抄这一段就行：

```html
<link rel="stylesheet" href="../base/tokens.css">
<link rel="stylesheet" href="glyph-cloud.css">
<link rel="stylesheet" href="glyph-ui.css">

<div class="subwrap">
  <div id="glyphwrap"><canvas id="glyphcv"></canvas></div>
  <div id="glyphrow">
    <div id="glyphgrab" role="separator" aria-label="拖这里调高矮"></div>
    <div id="glyphtip"></div>
    <div id="glyphbar">
      <button id="glyphzo" class="z" aria-label="缩小">−</button>
      <button id="glyphzi" class="z" aria-label="放大">＋</button>
      <button id="glyphrst" aria-label="回到默认"><svg viewBox="0 0 24 24">…</svg></button>
      <button id="glyphmode">纯看</button>
    </div>
  </div>
  <div id="glyphpick" hidden></div>
</div>

<script src="glyph-cloud.js"></script>
<script>
window.GLYPH_SOURCE = {
  list:   ()       => fetchJSON('/api/memories/cloud'),            // [memory] 或 {memories:[…]}
  near:   (id, k)  => fetchJSON(`/api/memories/cloud/${id}/near?k=${k}`),  // ★语义邻居
  full:   (id)     => fetchJSON(`/api/memories/cloud/${id}`),      // {text, ring}
  shapes: GlyphCloud.DEFAULT_SHAPES.slice(0, 3),                   // 这团字聚成什么
};
</script>
<script src="glyph-ui.js"></script>   <!-- ⚠ 一定在 GLYPH_SOURCE 之后 -->
```

`list / near / full` 返回值或 Promise 都行。**积木自己一个网络请求都不发** ——
发请求是你那半边的事，这三个函数就是那条缝。

它给你的东西：

| | |
|---|---|
| **点画布** | 换下一片形状（三片循环）。切到「选记忆」之后改成挑字符 |
| **纯看 / 选记忆** | `#glyphmode`，激活态是一圈内描边 |
| **关联记忆** | 「说的是同一件事」那一栏；点一条跳过去，**同时那几条会朝选中那条飘过来**（`setRelated`） |
| **读全文 ›** | 后端只给了截断的 `text` 和全长 `len` 时才出现 |
| **＋ / −** | 按住不放连发（×1.28，每 110ms 一档）|
| **重置** | 视角、缩放、平移、选中一起归零；**不动拖出来的高度**（那是偏好，不是视图状态）|
| **拖把手** | 调图的高矮（150px ~ 72vh），存 `localStorage` |
| **换皮** | 盯 `<html>` 的 `data-skin` / `data-theme`，变了就重新配色 |

配色是反着来的：**整团字符走 `--maple`（重点色）**，不是灰 —— 这样剪影本身就带着
应用的身份。高亮不能也用同一个红（一片红里挑七个不够看），所以从 `--maple`
**推导**出更深的一档（深底上则是更纯更亮的一档），换皮之后自己跟着算。
底浅还是深不看 `data-theme`，按 `--bg` 的感知亮度算 —— 一个应用可能有好几套皮。

## 一个字符对一条记忆（这一条是这份实现跟原型最大的差别）

原型是「形状面积和字号决定采样多少个点」—— 那样点数是画布说了算，
接上真数据就会出现**多一个空位或少一条记忆**。这里反过来：
**先按记忆条数解出字号，再采样**（`solveFS()`），所以严格一一对应。
demo 里那 160 个字符对着 160 条编出来的记忆，一个不多一个不少 —— 就是这条在起作用。

数字要跟你别处的统计对得上 —— 一边写 1080 一边画 1071，人一眼就看出来了。

## 数据从哪来

积木本身不发请求。要接后端的话，这三条是应用那边用的形状
（也就是上面 `GLYPH_SOURCE` 那三个函数各自该去问谁）：

```
GET /api/memories/cloud            → {n, layers:{L1:…}, memories:[{i,id,text,len,layer,day,tags}]}
GET /api/memories/cloud/{id}       → 一条的全文
GET /api/memories/cloud/{id}/near  → {items:[{id, sim}]}  跟它有关的
```

「有关」怎么算随你：应用那份用的是 2-gram 重合度（零依赖）；
上游那套用向量近邻。**形状一致，规模小的时候效果够。**

## 浅底上为什么要换字重

发丝笔画在 7px 上画出来几乎全是抗锯齿的半覆盖像素 —— 深底上读作发光，
**浅底上就是没画上去**。这是覆盖率问题，调透明度治不好。
所以每一档字形都备了两个字重（`FACES` 里的 `w` / `wl`），`light` 一开就换。

## 形状 —— 可以整组换掉

出厂八片（枫叶／心／圆／星／云／猫／月／叶）。**传 `shapes` 就换成你自己的**：
`demo.html` 里传的是前三片 —— 枫叶 ＋ 心 ＋ 圆。

```js
GlyphCloud.create(cv, {
  memories: …,
  shapes: [
    { name: '一颗星', box: 24, d: 'M12 2l3.1 6.3…' },   // box ＝ 这个 path 的 viewBox 边长
    { name: '我的标', box: 512, d: '…' },
  ],
});
GlyphCloud.DEFAULT_SHAPES   // 出厂那几片，想在它基础上加就拿这个
```

★ **想放哪家模型的标、自家的 logo，自己贴进来就是了** —— 那是你的机器、你的选择。
仓库里不预置任何厂商的商标，因为**分发别人的商标跟用别人的代码不是一回事**：
MIT 那种「署名就能用」对商标不适用。你自己给自己贴，跟我们打包发出去，是两码事。

⚠ **至少要两片**（只给一片时引擎会自动复制一份当第二片）。
关系是「一对字符在**两个**剪影里都挨得近」才连的，所以形状少于两片时连线没有对照面。

★ **0830 换过一次**：原来头两片是 Claude 和 Claude Code 的 logo。在原项目里自己用没问题，
但一个开源项目默认拿别家的商标当装饰形状，会让人以为它是那家出的 ——
**商标不是许可证能解决的事**（MIT 那种「署名就能用」不适用于商标）。所以换成了中性的。

枫叶那片是 Font Awesome Free 6 的 `canadian-maple-leaf`（CC BY 4.0，**要署名**，
声明在 [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md)）；心和圆是这儿自己写的。

## 出处

采样与形变配对的算法出自 **ThreeUI** 的 Text on a Path II — Study 08
「Morphing Glyph Cloud」（Meng To，MIT）。**连线、透视深度、拾取与高亮**
是这个项目新增的。版权行在 `THIRD_PARTY_NOTICES.md`。

## 两份的事

`glyph-cloud.js` 和 `.css` 跟应用 `index.html` 里那两段是**同一份**
（应用单文件零构建，引不了外链）。改一处要改两处，`tests/` 里钉着。
`glyph-ui.js` 同理 —— 它是应用那份外壳的照搬版，只换了两处：取数收成
`GLYPH_SOURCE`（积木不发请求），高度偏好从服务端的 PREF 换成 `localStorage`。

⚠ `glyph-ui.css` **里没有** `#glyphwrap` / `#glyphrow` / `#glyphpick` 那一大段 ——
那 100 行已经原样在 `glyph-cloud.css` 里了（逐行 diff 过，规则一个字节不差）。
再抄一遍就是同一组规则加载两次。所以两份都要引，别只引一个。
