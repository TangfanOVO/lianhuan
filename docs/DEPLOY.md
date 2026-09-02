# 装到手机上

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

## 数据在哪

| 装法 | 数据 | 要密码吗 |
|---|---|---|
| 纯本地（默认） | 你手机 / 你机器上的一个 `.db` 文件 | 不要 |
| 自建服务器 | 你服务器上 | **要** |

搬家：`GET /api/export` 拿一个 JSON，`POST /api/import` 灌回去。就一个文件。

## 一键部署到云上

仓库根目录有 `Dockerfile` 和 `render.yaml`。README 顶上那两颗按钮：

- **Render**：`https://render.com/deploy?repo=https://github.com/TangfanOVO/lianhuan` —— 读 `render.yaml`，问你口令和 key，起一个免费的 web service
- **Koyeb**：`https://app.koyeb.com/deploy?type=git&repository=github.com/TangfanOVO/lianhuan&branch=main&name=lianhuan&builder=dockerfile&ports=8420;http;/…` —— 照 Dockerfile 建，环境变量在它的页面上填

两家免费档都是**休眠 ＋ 不持久磁盘**：够试、够给朋友玩，要长期住就换付费档并把 `/app/data` 挂成持久盘。
不管在哪儿，数据都在 `/app/data`（SQLite、上传、`secrets.json`），备份就是这个目录。

容器一律按 `--lan` 起：所有请求都当成「从网络来的」，进门要 `LIANHUAN_PASSWORD`。
登记 MCP 和一键装 Engawa 这两条只认本机，云上不开放 —— 它们会在机器上起进程。

## Docker（自己的服务器）

```bash
cp .env.example .env        # 填 key；再加一行 LIANHUAN_PASSWORD=你的口令
docker compose up -d        # 数据落在 ./data
```

前面挂 Caddy / nginx 做 https，iPhone 才能把它加成带离线壳的主屏 app。
