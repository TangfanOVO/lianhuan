# 装到哪儿 · 家在哪

连环的「家」是 `data/` 那个文件夹（聊天、记忆、信、日记、心情、空间、日历、共读批注，一份 SQLite）。
手机上装的只是窗口。先决定家放哪，再看下面对应的那一节。

| 装法 | 家在哪 | 要不要口令 | 怎么更新 |
| --- | --- | --- | --- |
| 浏览器版（打开链接就用） | 这台设备的浏览器（IndexedDB） | 不要 | 打开就是最新 |
| 一键托管（Render / Koyeb） | 平台上你那份 `data/` | 要，部署时填 | 平台从仓库重建 |
| 自己的服务器（Docker） | 服务器上的 `./data` | 要 | 拉新代码重建 |
| 电脑上跑，手机同一个 Wi-Fi | 电脑上的 `data/` | `--lan` 时要 | 拉新代码 |
| 安卓完整体 APK | 手机上应用的沙箱 | 不要 | 装新包 |
| 安卓壳 APK | 家在电脑或云上 | 看家那边 | 壳不用动 |

家之间搬：设置里导出 JSON，另一边导入。

## 浏览器版

线上：https://tangfanovo.github.io/lianhuan/local/ 。同一份 Python 后端在页面里跑（Pyodide），没有服务器。
iPhone 用 Safari 打开，分享 → 添加到主屏幕；安卓用 Chrome，菜单 → 安装应用。
第一次打开从本站拿十几 MB，之后由 Service Worker 缓存，第二次几秒就开。
模型直接从浏览器连：DeepSeek、OpenAI、智谱、硅基流动、OpenRouter、Kimi 都允许浏览器直连；key 在 设置 › 功能包 › 引擎 里填，存在这台设备里。
（这是别人家服务器的行为，会变。`node scripts/check-provider-cors.mjs` 复核一遍，CI 的 e2e 那条每次也会跑，变了会警告。）

**不连任何第三方 CDN**：Pyodide 和 p5 随包自托管。CSP 的脚本文件只认本站；现有大页面仍需
`'unsafe-inline'`，Pyodide 还需 `'wasm-unsafe-eval'` 与 `blob:`，事件属性由 `script-src-attr 'none'` 单独关死。
key 就在这个源的 IndexedDB 里，所以这个源上不能有别人的脚本 —— 这是这一版最要紧的一条边界。
代价是这份产物有二十来 MB，静态托管要放得下。
颜文字抽屉和通话这一版不带。源码在 `apps/local/`，自己出一份：`cd apps/local && npm run build`，把 `dist/` 整个放到任何静态托管上。

## 安卓完整体

后端和前端都在 APK 里，家在应用沙箱。

⚠ 没配固定签名钥匙时，Actions 出的是 debug 包：新包装不到旧包上，换版本要卸载，**卸载 ＝ 家没了**。
先导出再换。配好钥匙就能覆盖升级。装法、备份规则和配钥匙的步骤见 [android-full/README.md](../android-full/README.md)。

## iOS · 加到主屏

1. 起服务：`python -m core.server --lan`（会提醒你风险）
2. iPhone 用 **Safari** 打开那个地址（Chrome 加不了主屏）
3. 分享 → 加到主屏幕

加完就是个 app：没有地址栏、自己的图标、能离线打开壳。

★ **必须是 https 或 localhost**，Service Worker 才会注册。局域网 IP 走 http 的话，
壳的离线缓存不生效 —— 界面照样能用，只是断网打不开。

★ 换了图标要**删掉主屏那个重新添加**，iOS 认缓存。

## 安卓 · 封成 APK

PWA 直接「添加到主屏幕」就能用。

**最省事：** `android/` 里那个不到 1MB 的 WebView 壳，Releases 的「apk」标签下有 Actions 自动打好的包
（debug 签名，能装能用，不能上架），装上填你服务的地址就行。它不含前端，前端改了不用重打。

想要真能上架、能拿系统权限的 APK：

**Bubblewrap**（Google 官方，免费）

```bash
npm i -g @bubblewrap/cli
bubblewrap init --manifest https://你的域名/manifest.json
bubblewrap build
```

**PWABuilder**（微软，网页上点几下）：把地址贴进 pwabuilder.com，选 Android，下载。

两个都是把你的 PWA 包成 TWA（Trusted Web Activity）—— **本质上还是这个网页**，
所以你改了网页，装了 APK 的人下次打开就是新的，不用重新发版。

### ★ 密钥别塞进 APK

TWA 里的 WebView 跟浏览器一样不适合放 key。要在安卓上直连模型，
用**原生 Keystore** 存，通过一个薄薄的原生桥递给网页 —— 别写在 JS 里、
别放 localStorage、别打进 apk 资源。

反编译一个 apk 是几分钟的事。

## 自己的服务器

```bash
pip install -r requirements.txt
LIANHUAN_PASSWORD='你自己的长口令' python -m core.server --lan --port 8420
```

前面挂 nginx / Caddy 做 https。`--lan` 开门后，连来自 `127.0.0.1` 的反代请求也必须登录；
不能拿回环地址当免密凭据。HTTPS 反代另设 `LIANHUAN_COOKIE_SECURE=1`。

反代要按真实来源限流时，可把它的 socket 地址显式写进 `LIANHUAN_TRUSTED_PROXIES`（逗号分隔），
这时才会读取它传来的 `X-Forwarded-For`。会起进程的 MCP/安装接口在开门模式下默认全关；只有**没有反代**、
确认浏览器直连后端时，才可设 `LIANHUAN_ALLOW_LOCAL_COMMANDS=1` 让本机页面使用。

★ 部署脚本里**别把 token 写进命令行**。`ps` 就能看见。用环境变量文件或者系统密钥库。

## 一键托管（Render / Koyeb）

仓库根目录有 `Dockerfile` 和 `render.yaml`，README 顶上那两颗按钮就是读它们的：

- **Render**：`https://render.com/deploy?repo=https://github.com/TangfanOVO/lianhuan` —— 读 `render.yaml`，问你口令和 key，起一个免费 web service
- **Koyeb**：README 按钮会预建 `PORT`、空的 `LIANHUAN_PASSWORD` 输入项和 HTTPS Cookie 开关；必须在页面里填自己的长口令再部署

**口令自己想一句，至少 16 个字符。** 服务端当场检查：太短，或者用了文档里的占位串（`改成你的口令`、`changeme` 那些），
它拒绝启动，不会「先跑着回头再改」。登录连错 5 次，那个来源地址锁 10 分钟。
★ 部署链接里**不预填口令** —— 写进公开 README 的字，全世界都读得到。

容器一律按 `--lan` 起：所有请求（包括反代送来的回环请求）都要 `LIANHUAN_PASSWORD`。
数据在 `/app/data`（SQLite、上传、`secrets.json`），备份就是这个目录。
两家免费档都是**休眠 ＋ 不持久磁盘**：够试、够给朋友玩；要长期住就换付费档，把 `render.yaml` 里 `disks` 那段放开，挂到 `/app/data`。
登记 MCP、一键装 Engawa 这两件会在机器上起进程，只认本机，云上不开放。

## Docker（自己的服务器）

```bash
cp .env.example .env        # 填 key；再加一行 LIANHUAN_PASSWORD=你自己那句长口令
docker compose up -d        # 数据落在 ./data
```

前面挂 Caddy / nginx 做 https，iPhone 才能把它加成带离线壳的主屏 app。
同时在 `.env` 里设 `LIANHUAN_COOKIE_SECURE=1`；若确实是仅限可信局域网的明文 HTTP，显式设为 `0`。

## 搬家

`GET /api/export` 拿一个 JSON，`POST /api/import` 灌回去。就一个文件；设置里有按钮。
