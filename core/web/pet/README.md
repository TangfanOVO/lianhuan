# 桌宠素材放这儿

**这个目录是空的，是故意的。** 机制全在（拖动、记位置、按 `/api/mood` 换姿势、CSS 动画驱动），
素材一张不带 —— 原来那只的角色是别家公司的吉祥物，**商标不是许可证能解决的事**，
自己机器上放着玩没问题，跟着开源分发不行。

## 自己放

丢进来，按状态名命名（少几张也行，缺的落回 `idle`；一张都不放，那个位置就不显示）：

```
idle.svg  idle-look.svg  idle-yawn.svg  idle-bubble.svg
happy.svg  wake.svg  sleeping.svg  typing.svg
headphones.svg  annoyed.svg  jump.svg  shy.svg
```

SVG 自带 CSS 动画也行（会被包进 `<img>`，样式不污染页面）。GIF 也认。

## 思路跟记忆星图是同一套

那边出厂三片形状 —— **心、圆、枫叶** —— 想换整组传进去就行：

```js
GlyphCloud.create(canvas, { shapes: [{ d: '<path d>', box: 24, name: '你的' }] });
```

这儿也一样：**内置的只是个起点，换成什么都行。** 自己画、自己找、生成一套都行，
命名对上就能用 —— 机制不认得图里是谁。
