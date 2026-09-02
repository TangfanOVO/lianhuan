# 零件

底栏 · 抽屉 · 滑上来的二级页 · 全局搜索 · 遮罩 · bottom sheet 的样子。

| | 状态 |
|---|---|
| 样式（`parts.css`） | ✅ 全都在 |
| 开关逻辑（`parts.js`） | ✅ 能用，不到 100 行 |
| **sheet 的三档吸附拖动**（`Parts.sheet`） | ✅ 能用，[demo.html](demo.html) 能试 |

## 用它

```html
<link rel="stylesheet" href="../base/tokens.css">
<link rel="stylesheet" href="parts.css">

<button data-open="settings">设置</button>
<div class="sub" id="settings">
  <button data-close>返回</button>
  <div class="subwrap">…</div>
</div>
<div class="scrim"></div>

<script src="parts.js"></script>
<script>const parts = Parts();</script>
```

挂一次就好，之后加页面只写 HTML，不用再写 JS。

## 二级页是一摞

层层往上叠，返回一次退一层。**不这么做的话**，从二级页里再点进三级页，
返回会一次退到底 —— 那是最常见的返回 bug。

## 动效

页面切换位移 14px / .2s；二级页进 .3s、**退 .22s**（退比进快，不然像卡住了）；
遮罩 .24s。曲线全在底座的 `--e-out` / `--e-in` 里。

★ **跟手拖动的时候必须把 transition 关掉**，不然手指和面板会脱节。

## sheet 的拖动

```html
<div class="scrim" id="scrim"></div>
<aside class="sheet" id="sheet">
  <div class="sheethead"><div class="grabber"></div><header><h4>标题</h4></header></div>
  <div class="sheetbody">…正文自己滚…</div>
</aside>
<script>
  const s = Parts.sheet({ sheet: document.getElementById('sheet'), scrim: document.getElementById('scrim') });
  s.open(true);          // 打开，落在一半
  s.set(72, true);       // 直接定到某一档
  s.pct();               // 现在在哪
</script>
```

它做的事，也是它的规格：

- 三档吸附（`translateY` 百分比）：**0 拉满 / 40 一半 / 72 只露头 / 100 关掉**，打开落在 40
- 拖动**跟手**，不是拖完才动
- 松手吸最近一档；**甩得快（速度 > .6 px/ms）就顺方向直接过一档**
- 往上顶过头给阻尼（`pct / 3`），别让它翻上去
- 遮罩透明度跟着高度线性走，点遮罩关掉
- **只有头部可拖**（`.sheethead`），正文照常滚，两者不打架

这段是从应用的思考链面板整段平移过来的，只把写死的 id 换成传进来的元素。改这边之前先想想那边。
