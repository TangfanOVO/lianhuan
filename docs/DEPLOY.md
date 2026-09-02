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

PWA 直接「添加到主屏幕」就能用。想要真 APK（能上架、能拿系统权限）：

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
