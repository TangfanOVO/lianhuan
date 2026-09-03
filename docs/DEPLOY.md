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
第一次打开从 CDN 拿十几 MB，之后由 Service Worker 缓存，第二次几秒就开。
模型直接从浏览器连：DeepSeek、OpenAI、智谱、硅基流动、OpenRouter 都允许浏览器直连；key 在 设置 › 功能包 › 引擎 里填，存在这台设备里。
颜文字抽屉和通话这一版不带。源码在 `apps/local/`，自己出一份：`cd apps/local && npm run build`，把 `dist/` 整个放到任何静态托管上。

## 安卓完整体

后端和前端都在 APK 里，家在应用沙箱。装法和细节见 [android-full/README.md](../android-full/README.md)。

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
python -m core.server --port 8420
```

前面挂 nginx / Caddy 做 https。**开在公网上就要加认证** ——
默认那条纯本地的路子没有密码，因为手机锁屏就是锁；服务开在公网上，
知道地址就能进。

★ 部署脚本里**别把 token 写进命令行**。`ps` 就能看见。用环境变量文件或者系统密钥库。

## 一键托管（Render / Koyeb）

仓库根目录有 `Dockerfile` 和 `render.yaml`，README 顶上那两颗按钮就是读它们的：

- **Render**：`https://render.com/deploy?repo=https://github.com/TangfanOVO/lianhuan` —— 读 `render.yaml`，问你口令和 key，起一个免费 web service
- **Koyeb**：`https://app.koyeb.com/deploy?type=git&repository=github.com/TangfanOVO/lianhuan&branch=main&name=lianhuan&builder=dockerfile&ports=8420;http;/&env[PORT]=8420` —— 照 `Dockerfile` 建，环境变量在它的页面上填

**口令自己想一句，至少 16 个字符。** 服务端当场检查：太短，或者用了文档里的占位串（`改成你的口令`、`changeme` 那些），
它拒绝启动，不会「先跑着回头再改」。登录连错 5 次，那个来源地址锁 10 分钟。
★ 部署链接里**不预填口令** —— 写进公开 README 的字，全世界都读得到。

容器一律按 `--lan` 起：所有请求都当成「从网络来的」，所以进门要 `LIANHUAN_PASSWORD`。
数据在 `/app/data`（SQLite、上传、`secrets.json`），备份就是这个目录。
两家免费档都是**休眠 ＋ 不持久磁盘**：够试、够给朋友玩；要长期住就换付费档，把 `render.yaml` 里 `disks` 那段放开，挂到 `/app/data`。
登记 MCP、一键装 Engawa 这两件会在机器上起进程，只认本机，云上不开放。

## Docker（自己的服务器）

```bash
cp .env.example .env        # 填 key；再加一行 LIANHUAN_PASSWORD=你自己那句长口令
docker compose up -d        # 数据落在 ./data
```

前面挂 Caddy / nginx 做 https，iPhone 才能把它加成带离线壳的主屏 app。

## 搬家

`GET /api/export` 拿一个 JSON，`POST /api/import` 灌回去。就一个文件；设置里有按钮。
