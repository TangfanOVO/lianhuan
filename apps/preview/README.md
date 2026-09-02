# 连环 · 应用空壳预览

**这是什么**：`core/web/index.html` 的一份**副本**，构建时在页顶追加一条常驻横条，写明「这里没有后端」。
发到 GitHub Pages 的 `/app/` 下（见 `.github/workflows/pages.yml`），让人不装任何东西就能看到应用长什么样。

**这不是什么**：不是 demo 账号、不是演示数据、不是接了一半的后端。所有 `/api/*` 都是 404，
页面按它自己的降级逻辑显示空状态——空的时候就是空的，预览不冒充接通。

## 什么是真的

- 五个页（聊天 / 记事 / 主页 / 记忆 / 书房）的排版、切换、空状态
- 开屏（含那层枫叶水面，p5 走的是应用自己写的 CDN 地址）、主页的丝线、书房
- 设置里的外观项——存在本机 `localStorage`，只在这台机器、这个浏览器里生效

## 什么是假的 / 不能用

| 入口 | 在预览里 |
|---|---|
| 发消息（按钮、⌘/Ctrl+回车） | 拦下并说明原因；输入框里的字**还在**，不伪造回复 |
| 打电话 | 拦下并说明原因 |
| 颜文字抽屉 | 资源在 `optional/kaomoji_drawer/`，静态托管拿不到；控制台会有几条 `/kaomoji/` 的 404，是预期的 |
| 桌宠 | 素材本来就不随仓库分发（`core/web/pet/README.md`），这里也没有；聊天页右下角那个空图标就是它没素材时的样子，是应用本身的表现 |
| 哄睡、推送、离线壳 | 没有后端 / 副本故意不带 `sw.js` 和 `manifest.json` |

## 本地看一眼

```
cd apps/preview
npm run dev          # = 构建 + python3 -m http.server 8425 --directory dist
```

然后开 http://localhost:8425 。只构建不起服务：`npm run build`。

## 构建做了什么（`scripts/build.mjs`）

1. 白名单拷贝 `core/web/` 里的 `index.html`、`icons/`、`html2canvas.min.js`，和开屏那层水用的 `blocks/water/maple-water.js` 到 `dist/`；
   **不拷 `sw.js` / `manifest.json`**——装一个指着错地方的 Service Worker 比不装糟得多。
2. 只在副本上做纯文本替换（源文件一个字节不动），每处都断言命中次数，对不上就报错退出：
   补 `<!doctype html>` / `<html>` / `<head>` / `<body>`；删掉 `optional/` 里的颜文字样式表链接；
   摘掉 Service Worker 注册；把站根绝对路径（图标、出图脚本、manifest）改成相对或摘掉；
   末尾追加 `banner.js`。
3. 简单解析一遍确认标签配平，再写 `dist/README.txt`。

`banner.js` 单独成文件：横条、让位（横条高度写进 `--static-bar`，body / `.app` / 开屏跟着下移）、
两个入口的捕获阶段拦截。想改横条文案或拦截范围，改它就行。

## 许可

AGPL-3.0-only，与完整的连环应用相同。
