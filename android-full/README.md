# 连环 · 安卓完整体

后端（Python）和前端都在这个 APK 里。装上就是一整个连环：不连电脑、不连云，家在应用自己的沙箱里。

| | |
|---|---|
| 装 | Releases 里的 [apk-full](https://github.com/TangfanOVO/lianhuan/releases/tag/apk-full) 标签下，Actions 每次改了后端或这个工程都会放一个新包（debug 签名，能装能用，不能上架；覆盖安装报签名不一致就先卸载旧的） |
| 家在哪 | 手机上应用自己的沙箱（`files/data/`）：SQLite、上传的图、`secrets.json` 都在这儿。卸载就没了 |
| 搬家 | 设置里导出 JSON，到另一边导入 |
| 接模型 | 设置 › 功能包 › 引擎，填接口地址和 key。key 存在沙箱里，不出手机 |
| 更新 | 装新包。它不像浏览器版那样自动更新 |
| 第一次打开 | 要解开 Python 那些包，等几秒；之后一两秒 |

## 跟隔壁那个壳的区别

`android/` 那个壳不到 1MB，只是一个指向你电脑或云上服务的窗口，家在那边。
这个完整体几十 MB，家在手机里。两个工程互不影响。

## 自己打

```
cd android-full
echo "sdk.dir=你的AndroidSDK路径" > local.properties
gradle assembleDebug
```

要 Android SDK（platform 36）、JDK 17～21，和一个 **3.12** 的 python3（Chaquopy 要求构建机的 Python 跟包里的同一个小版本）。
构建前 `syncPython` 会从仓库根把 `core/ optional/ seed/` 同步进 `build/python-src`，后端不在这里复制第二份。

## 包里跟电脑版不一样的两处

- `pydantic` 钉 1.x、`fastapi` 钉 0.115：pydantic 2 的核心是 Rust 写的，没有安卓轮子。后端全套测试在 1.x 下照过。
- 不带推送（pywebpush）：推送是浏览器那套，装在手机里的完整体用不上。
