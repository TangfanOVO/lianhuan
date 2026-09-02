# 那条线

通话时屏幕中间那条线。**线是一条线** ——

- **谁在说，线就往谁那头写。** 两个人的波形长得不一样：一头是连着的一道涌
  （合成的声音是连续的），另一头是线上面一串小齿（识别是一颗一颗字回来的）。
  这个区别本身就是「现在轮到谁」，不用再画一个头像去说明。
- **他在想的时候，线在他那头一笔写出一片叶子。** 一支笔从左往右走，
  编好一片落回水平线，往右一段再编下一片。**笔走到哪儿＝想了多久**
  （第一片约 1 秒，第三片约 5 秒）。他一开口，尾巴追着头 0.34 秒把线拆干净。

零依赖。**不碰麦克风、不发任何请求** —— 音量由宿主喂进来，要不要开麦是宿主的事。

## 用

```html
<link rel="stylesheet" href="../base/tokens.css">
<link rel="stylesheet" href="thread.css">
<div class="threadwrap"><canvas id="thread"></canvas></div>
<script src="../base/crest.js"></script>
<script src="thread.js"></script>
<script>
  var t = Thread(document.getElementById('thread'), { leaf: Crest.def('maple') });
  t.setPhase('listening');       // 谁在说
  t.setLevel(0.6);               // 有真音量就喂；不喂就用一条合成包络
</script>
```

| | |
|---|---|
| `setPhase(p)` | `idle` / `connecting` / `incoming` / `ringing` / `listening` / `thinking` / `speaking` / `ended` |
| `setLevel(v)` | 0～1。喂进来的音量 400 毫秒内优先；断供就落回合成包络 |
| `setLeaf(def)` | 换一片叶子。给 `Crest.def('leafy')`，或自己的 `{viewBox, path}` |
| `retheme()` | 宿主换肤之后叫一声，重读 `--ink` / `--thread` / `--maple`（或 `--accent`） |
| `destroy()` | 收工 |

## 叶子从哪来

默认拿 `blocks/base/crest.js` 里那片枫叶（Font Awesome Free 6 的 canadian-maple-leaf，
CC BY 4.0，**要署名**，见 `UPSTREAM.md`）。`Crest` 里还有纸、月亮、屋子、结、叶 ——
`setLeaf(Crest.def('moon'))` 就换掉。也可以整段贴自己的 path。

★ 叶柄留着。没叶梗那片东西像鸡爪 —— 试过。

## 换肤

颜色全从 CSS 变量读：`--ink`（谁在说的那一头）、`--thread`（另一头，沉进纸里）、
`--maple` 或 `--accent`（写叶子的那支笔）。宿主改了变量之后叫一次 `retheme()`。

`prefers-reduced-motion` 下自动降成一条安静的线：不飘、不出波包、叶子一次画完。
