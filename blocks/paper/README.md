# 纸感材质

一套「东西是贴在纸上的」的质感。**纯 CSS，零 JavaScript，零后端。**

撕边纸 · 格纹胶带 · 票根（左右打孔） · 明信片（航空邮件斜条边 ＋ 邮票齿孔 ＋ 盖销波浪）
· 折起来的日记 · 标本卡 · 小册标签

先打开 [`demo.html`](demo.html) 看看是不是你要的。

## 拿走它

三步：

```html
<link rel="stylesheet" href="base/tokens.css">   <!-- 底座，见下 -->
<link rel="stylesheet" href="paper/paper.css">
```

```html
<!-- 撕边纸要这个滤镜。放页面里任何地方，它自己不显示 -->
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <filter id="pp-torn" x="-5%" y="-10%" width="110%" height="120%">
    <feTurbulence type="fractalNoise" baseFrequency="0.014 0.36" numOctaves="3" seed="7" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="6" xChannelSelector="R" yChannelSelector="G"/>
  </filter>
</svg>
```

```html
<div class="pp-note">
  <div class="pp-paper"></div>       <!-- 底下那张被扭出撕口的纸 -->
  <span class="pp-tape a"></span>    <!-- 胶带，a 在左上 b 在右上，加 .blue 换色 -->
  <p class="pp-place">城南旧书店</p>
  <p class="pp-text">正文…</p>
</div>
```

## 它要什么

只要底座（`base/tokens.css`）里这几个变量：

```
--card  --card2  --ink  --sub  --hint  --line  --accent  --spring-pop
```

**不用底座也行**，自己给这几个变量赋值就够了。亮色暗色都跟着底座走，你不用写第二套。

## 有哪些类

| 类 | 是什么 |
|---|---|
| `.pp-note` ＋ `.pp-paper` | 撕边纸。纸是绝对定位的一层，内容在它上面 |
| `.pp-tape` `.a` `.b` `.blue` | 格纹胶带，斜着压在角上 |
| `.pp-ticket` | 票根，左右打孔、中间撕线 |
| `.pp-pc` `.r1` `.r2` | 明信片外框（航空斜条边），r1/r2 是两个歪法 |
| `.pp-front` / `.pp-seal` / `.pp-cancel` | 正面图 / 圆邮戳 / 盖销波浪 |
| `.pp-fold` `.pp-item` `.pp-sum` `.pp-body` | 折起来的日记。给 `.pp-item` 加 `.on` 就展开 |
| `.pp-rows` `.pp-row` | 一条条票根线 |
| `.pp-specs` `.pp-spec` | 标本卡，贴纸样 |
| `.pp-books` `.pp-book` | 小册标签 |
| `.pp-rest` / `.pp-more` | 「还有 N 条 ›」那种文字链 |

## 两个真咬过人的坑（改之前先读）

**① CSS 背景的第一层在最上面。** 明信片的航空斜条边是 `padding-box` 和 `border-box`
两层叠出来的 —— **纸必须写在斜条前面**，写反了斜条会铺满整张、把信压在底下。

**② 邮票齿孔别用 mask。** 原来是五层 `mask-composite`，在手机上会把整张图咬没。
现在改成用纸的颜色在四边叠一圈半圆 —— 视觉一样，图一定在。

## 一条设计上的分寸

`.pp-rest` / `.pp-more`（「还有 6 枚 ›」）是**列表被截断**那一路：文字链、13px、重点色、后缀 `›`。
另一路是**打开一整件东西**：整行 ＋ 右侧 chevron（`.pp-sum` 那种）。

**别混用。** 混着用，人就分不清哪些是「展开更多」哪些是「点进去」。

## 字体

正文那几处指定了 **LXGW WenKai**（霞鹜文楷，SIL OFL 1.1）。没装会自动落到宋体 / Georgia，
不影响布局。要装自己去拿，我们不打包字体文件。

## 无障碍

`prefers-reduced-motion` 下那些歪着的纸片会自动摆正（文件末尾那段）。别删。
