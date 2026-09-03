# 连环 · 安卓完整体

后端（Python）和前端都在这个 APK 里。装上就是一整个连环：不连电脑、不连云，家在应用自己的沙箱里。

> ## ⚠ 先读这一段，再决定要不要拿它存东西
>
> 完整体的家（聊天、记忆、日记、心情、日历）**就在这个应用的沙箱里**。所以：
>
> - **卸载这个 app ＝ 家一起没了。** 不像壳那样数据在电脑或云上。
> - 当前 Releases 的 `apk-full` 已使用固定正式签名，新版可以直接覆盖安装并保留数据。
> - 更新前仍建议去 设置 › 搬家 导出一份 JSON；换手机、误卸载和系统备份失败都需要它。
> - 如果装过旧的 `TESTONLY` 包，第一次切换要先导出、卸载测试包、安装正式包、再导入；从正式包开始，后续版本才可直接覆盖。
>
> 如果以后下载到文件名带 `TESTONLY` 的包，那是签名配置失效时的测试产物，不要拿它替换正式版。

| | |
|---|---|
| 装 | Releases 的 [apk-full](https://github.com/TangfanOVO/lianhuan/releases/tag/apk-full) 标签下 |
| 家在哪 | 手机上应用自己的沙箱（`files/data/`）：SQLite、上传的图、`secrets.json` 都在这儿 |
| 搬家 / 备份 | 设置 › 搬家，导出一个 JSON；换机、重装都靠它 |
| 接模型 | 设置 › 功能包 › 引擎，填接口地址和 key。key 存在沙箱里，不出手机 |
| 更新 | 正式签名的包：直接覆盖安装，数据留着。debug 包：只能卸载重装（先导出） |
| 第一次打开 | 要解开 Python 那些包，等几秒；之后一两秒 |

## 系统备份

manifest 里开了自动备份（`allowBackup` ＋ `backup_rules.xml` / `data_extraction_rules.xml`），
所以换手机直传、或者系统云备份还原，都能把这份家接回来。**模型 key（`secrets.json`）排除在外** ——
那东西不该跟着备份上云。

这层不是保险箱：要用户自己开着备份、要能连上、不同厂商 ROM 行为还不一样。**导出那个 JSON 才是正路。**

## 正式签名与续签（已经配置）

本仓库已经配置固定发布密钥，证书 SHA-256 钉在 `SIGNING_FINGERPRINT.txt`。Actions 每次打包都会验证
实际证书；钥匙缺失、指纹为空或不匹配都会停止正式发布。维护时继续使用同一套 Secret，不要重新生成另一把。

下面是给新 fork 首次配置时看的步骤。本仓库本身已经完成，不需要重复执行。

在自己机器上生成一把，然后把它交给 Actions：

```bash
keytool -genkeypair -v -keystore lianhuan.jks -alias lianhuan \
        -keyalg RSA -keysize 4096 -validity 10000
base64 -i lianhuan.jks | pbcopy        # Linux: base64 -w0 lianhuan.jks
```

到 GitHub 仓库 → Settings → Secrets and variables → Actions，加四条：

| Secret | 填什么 |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | 上面 base64 出来的一整串 |
| `ANDROID_KEYSTORE_PASSWORD` | 生成时设的 keystore 口令 |
| `ANDROID_KEY_ALIAS` | `lianhuan` |
| `ANDROID_KEY_PASSWORD` | key 的口令（没单独设就填 keystore 那个） |

★ **那个 `.jks` 文件自己收好，别提交进仓库，也别弄丢。** 丢了就再也签不出「同一个 app」，
所有装着旧版的人都得卸载重装 —— 也就都会丢一次数据。

首次配置时，先在本机从这同一把 keystore 算出指纹：

```bash
keytool -list -v -keystore lianhuan.jks -alias lianhuan | grep 'SHA256:'
```

把冒号后的值去掉冒号和空格，写进 `android-full/SIGNING_FINGERPRINT.txt` 并提交；再配上面四条 Secret。
流水线在指纹文件缺失、为空或不匹配时都会直接失败，不会发布一个无法延续升级链的正式包。

## 跟隔壁那个壳的区别

`android/` 那个壳不到 1MB，只是一个指向你电脑或云上服务的窗口，家在那边，
所以它换签名重装也不丢东西。这个完整体几十 MB，家在手机里，签名就是命根子。两个工程互不影响。

## 自己打

```bash
cd android-full
echo "sdk.dir=你的AndroidSDK路径" > local.properties
gradle assembleDebug
```

要 Android SDK（platform 36）、JDK 17～21，和一个 **3.12** 的 python3（Chaquopy 要求构建机的 Python 跟包里的同一个小版本）。
构建前 `syncPython` 会从仓库根把 `core/ optional/ seed/ blocks/` 同步进 `build/python-src`，后端不在这里复制第二份。

版本号从环境变量来：`LH_VERSION_CODE`（CI 用 run_number）、`LH_VERSION_NAME`；本机不传就是 1 / 0.1。

## 包里跟电脑版不一样的两处

- `pydantic` 钉 1.x、`fastapi` 钉 0.115：pydantic 2 的核心是 Rust 写的，没有安卓轮子。后端全套测试在 1.x 下照过。
- 不带推送（pywebpush）：推送是浏览器那套，装在手机里的完整体用不上。
