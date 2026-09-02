# 第三方声明

连环用到了下面这些别人的东西。**它们的版权属于各自的作者**，许可原文抄在这儿 ——
MIT 那句「上述版权声明和本许可声明应包含在软件的所有副本中」说的就是这份文件存在的理由。

> 核验时间：2026-08-30。版权行是当天从各自上游仓库的 LICENSE 抄下来的原文。
> 谁要是改了名字或年份，以上游为准 —— 发行前照着链接再看一眼最省事。

---

## MIT 许可的那些

| 组件 | 用在哪 | 版权行（原文） |
|---|---|---|
| [ThreeUI](https://github.com/MengTo/threeui) | 记忆字云：采样与形变配对的算法出自它的「Morphing Glyph Cloud」 | `Copyright (c) 2026 Meng To` |
| [Tabler Icons](https://github.com/tabler/tabler-icons) | 界面上几乎所有线条图标（全部内联成 SVG） | `Copyright (c) 2020-2026 Paweł Kuna` |
| [html2canvas](https://github.com/niklasvh/html2canvas) | 聊天存长图 | `Copyright (c) 2012 Niklas von Hertzen` |
| [fuyue-kaomoji-drawer](https://github.com/TangfanOVO/fuyue-kaomoji-drawer) | 颜文字抽屉（整套内置在 `optional/kaomoji_drawer/`） | `Copyright (c) 2026 TangfanOVO` |
| [ears](https://github.com/Eveacla11/ears) | 通话的上行链（录音 → 识别 → 情感标签）照它写的 | `Copyright (c) 2026 Eve` |
| [Nocturne-Memory-Core](https://github.com/Pyruslili/Nocturne-Memory-Core) | 记忆分层里的「近场日记」那一层 | `Copyright (c) 2026 P0lar1zzZ` |
| [journey-cards](https://github.com/nonchaiovo/journey-cards) | 出门页的数据契约 | `Copyright (c) 2026 nonchaiovo`（MIT，0831 实核） |

上面这些共用同一份 MIT 正文：

```
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 别的许可

| 组件 | 用在哪 | 许可 | 要注意的 |
|---|---|---|---|
| [Font Awesome Free 6](https://fontawesome.com) | 一枚图标 | 图标部分 **CC BY 4.0** | **必须署名**：图标来自 Font Awesome Free，https://fontawesome.com ，CC BY 4.0 |
| [LXGW WenKai 霞鹜文楷](https://github.com/lxgw/LxgwWenKai) | 中文字体 | **SIL OFL 1.1** | 字体文件随发行时要带上 OFL 原文；不得单独售卖字体 |
| [p5.js](https://p5js.org) | 水面待机 | **LGPL-2.1** | **不打包**，走 CDN；加载失败自动降级。要改成随包发行的话，先读 LGPL 对静态链接那几条 |

---

## 还欠着的（诚实记账）

- （journey-cards 已核完 —— 0831 补了链接和版权行，这条清了。）
- 字体和 p5 走的是「不打包」这条路，所以这份文件里只写了义务、没抄正文；
  哪天决定把它们随包带走，正文要一起搬进来。
