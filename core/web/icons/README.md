# 家徽

默认是**枫叶**。来自 Font Awesome Free 6（`canadian-maple-leaf`，CC BY 4.0）——
用了要署名，见根目录 `UPSTREAM.md`。

## 换成你自己的

**界面里那个**（顶栏那枚）走 `blocks/base/crest.js`，内置六个：

```js
Crest.list();            // maple 枫叶 / paper 一张纸 / moon 月亮 / house 屋子 / knot 结 / leafy 叶
Crest.set('moon');       // 换一个，记在本机
Crest.set({ viewBox:'0 0 24 24', path:'M…', fill:true });   // 用你自己的 path
```

**加到主屏那个**（这个目录里的图）得另外换 —— 系统读的是文件，不是 JS：

| 文件 | 干嘛的 |
|---|---|
| `icon.svg` | 浏览器标签页。矢量，随便放大 |
| `icon-180.png` | iOS 加到主屏 |
| `icon-192.png` / `icon-512.png` | 安卓、以及 manifest |
| `icon-512-maskable.png` | 安卓自适应图标。**四周要留安全区**——它会被裁成圆的 |

换完记得同步改 `manifest.json` 里的 `theme_color` 和 `background_color`，
不然启动那一下的底色会跟你的图不搭。

★ **iOS 认死文件名和缓存**：换了图标之后要把主屏那个删掉重新添加，不然还是旧的。
