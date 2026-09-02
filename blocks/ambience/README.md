# 漂浮物

背景里飘着的那些小东西。十种，可以多选，密度和速度各一个把手。

| 件 | 是什么 |
|---|---|
| [`ambience.js`](ambience.js) | 图标表 ＋ 渲染。零依赖 |
| [`ambience.css`](ambience.css) | 十行 ＋ 一个 `@keyframes`。**跟应用里那段是同一份**，tests 钉着 |
| [`demo.html`](demo.html) | 双击就能看，十种都能点 |

## 用它

```html
<link rel="stylesheet" href="../base/tokens.css">
<link rel="stylesheet" href="ambience.css">
<div class="stage" style="position:relative;overflow:hidden">
  <div id="fly"></div>
  <div style="position:relative;z-index:1">…你的内容…</div>
</div>
<script src="ambience.js"></script>
<script>
  const fly = Ambience(document.getElementById('fly'),
                       { kinds: ['maple','snow'], count: 9, speed: 1 });
  fly.set({ count: 20 });     // 改哪个给哪个
  fly.kinds                   // [['maple','枫叶'], …] 照它长选择器
  fly.clear();                // 不要了
</script>
```

宿主要 `position:relative`（或 absolute）并且 `overflow:hidden`；内容层的 `z-index` 要比它高。

| 参数 | 默认 | 说明 |
|---|---|---|
| `kinds` | `['maple']` | `maple flower heart bubble rain snow star note fish firefly` |
| `count` | 9 | 0–30。0 ＝ 不要 |
| `speed` | 1 | 0.3–2.6。往右 ＝ 飘得快 |

## 三件小事

**① 多选时轮着来，不是随机。** 随机会出现「选了三种，结果某一种一片都没落下」。

**② 速度是除法，延迟也要跟着缩。** `dur = (13 + rand*15) / speed`；
延迟不缩的话，一拉快画面前几秒是空的。

**③ 它是纯装饰。** `aria-hidden="true"` 是自动加的，读屏会跳过；
`prefers-reduced-motion` 下应用那边整个停掉动画，你自己接的时候记得也留一手。

## 图标出处（要署名的那条在这儿）

| 哪个 | 来自 | 许可 |
|---|---|---|
| 枫叶 | Font Awesome Free 6 · `canadian-maple-leaf` | **CC BY 4.0 —— 必须署名** |
| 花瓣 · 爱心 · 泡泡 · 雨 · 雪 · 星 · 音符 · 小鱼 | Tabler Icons | MIT |
| 萤火 | 自己画的一个圆点 | — 图标库里没有「一点光」这种东西 |

版权正文在仓库根的 [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md)。
**带走这块积木＝带走那份声明**，别落下。
