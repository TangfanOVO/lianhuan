# 连环 · 安卓壳

一个不到 1MB 的 WebView 壳，指向你自己电脑上跑的连环服务。
它不是「app 版连环」—— 连环全部在你电脑那份服务里，这个壳只是让手机开它像开一个 app。

## 它做的四件事

1. 全屏打开你填的服务地址（第一次打开会问你）
2. 返回键 = 网页后退（页面里那套安卓返回桥接得住）
3. 页面打电话要麦克风时，替它把系统权限要下来
4. 想改地址：在页面里随便一处**长按 1.2 秒**，设置框会弹出来

## 装

```
cd android
echo "sdk.dir=你的AndroidSDK路径" > local.properties
gradle assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

- 要 Android SDK（platform 36 + build-tools）和 JDK 17~21。
  ★ JDK 太新（25+）会在 `JdkImageTransform` 上炸 —— `gradle.properties` 里
  `org.gradle.java.home=` 指一个 JDK 21 就好（本仓库这份就是这么写的）。
- 小米/红米装的时候要在开发者选项里打开「USB 安装」，装时手机上还会弹一次确认。

## 服务地址填什么

| 手机和电脑的关系 | 填 |
|---|---|
| 同一个 Wi-Fi | `http://电脑的局域网IP:8420` |
| USB 连着电脑 | 先在电脑跑 `adb reverse tcp:8420 tcp:8420`，然后填 `http://localhost:8420` |
| 服务挂了公网 https | 直接填那个地址 |

## 推送？——实话

**这个壳里没有推送，是故意的。**

- Web Push（他主动找你时弹锁屏）要走浏览器＋HTTPS＋系统推送通道那一整套，
  WebView 壳里没有这条路。
- 「壳里塞个后台轮询」在国产 ROM 上活不过半小时就被杀了 —— 装了等于骗你。

想要锁屏推送，走正路：把服务挂到 HTTPS（cloudflared 之类），手机 **Chrome** 打开、
**添加到主屏幕**，从主屏图标进去，在 设置 › 通知与频率 里打开「推到手机上」。
安卓上这条链是完整的；iPhone 同样步骤，要 iOS 16.4 以上。
