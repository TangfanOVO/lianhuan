package app.lianhuan.full;

/*
 * 连环的安卓完整体 —— 后端（Python）在这个进程里跑，前端在 WebView 里开它。
 * 数据在应用自己的沙箱里（filesDir/data），不连任何电脑或云。
 *
 * 跟隔壁那个壳（android/）比，只多了一件事：开机先把后端起在 127.0.0.1:8420，
 * 等它应答了再把页面打开。其余（返回键、麦克风、选文件）一样。
 */

import android.annotation.SuppressLint;
import android.app.DownloadManager;
import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.webkit.PermissionRequest;
import android.webkit.CookieManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.URLUtil;
import android.webkit.WebViewClient;
import android.widget.Toast;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {

    private static final int PORT = 8420;
    private static final String BASE = "http://127.0.0.1:" + PORT;

    private WebView web;
    private ValueCallback<Uri[]> filePick;
    private static final int REQ_FILE = 11;
    private static final int REQ_MIC = 12;
    private PermissionRequest pendingMic;
    /** 这次启动的随机票。★ 系统下载管理器是独立进程，不共享 WebView 的 Cookie，
        所以下载请求要自己把票带上，否则后端回 401，存下来的是一句错误 JSON。 */
    private volatile String androidToken = "";

    @Override
    @SuppressLint("SetJavaScriptEnabled")
    protected void onCreate(Bundle b) {
        super.onCreate(b);

        web = new WebView(this);
        setContentView(web);

        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true);
        }

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        // 给页面一个「我在壳里」的记号。★ 只追加，不覆盖 —— 页面里那句 /Android/i 的判断照旧成立。
        s.setUserAgentString(s.getUserAgentString() + " LianhuanShell/1");

        /* 下载。★ 0903 真机验出来的：WebView 里 <a download> 配 blob: 什么都不会发生，
           而页面还会提示「下载好了」—— 假成功比坏掉更糟。
           这里接住下载，交给系统的下载管理器：存进公共「下载」文件夹、发通知、告诉用户文件名。 */
        web.setDownloadListener((url, ua, disposition, mime, len) -> {
            try {
                String name = URLUtil.guessFileName(url, disposition, mime);
                DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
                if (!androidToken.isEmpty()) {
                    req.addRequestHeader("Cookie", "lh_android=" + androidToken);
                }
                req.setMimeType(mime);
                req.setTitle(name);
                req.setDescription("连环的备份");
                req.setNotificationVisibility(
                    DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
                ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(req);
                Toast.makeText(this, "存好了：手机的「下载」文件夹 / " + name,
                               Toast.LENGTH_LONG).show();
            } catch (Throwable e) {
                // ★ 宁可吵，也不要再来一次假成功
                Toast.makeText(this, "没存下来：" + e, Toast.LENGTH_LONG).show();
            }
        });
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                String url = req.getUrl().toString();
                if (url.startsWith(BASE)) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, req.getUrl()));
                } catch (Exception ignored) { }
                return true;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                for (String r : request.getResources()) {
                    if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r)) {
                        if (checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)
                                == android.content.pm.PackageManager.PERMISSION_GRANTED) {
                            request.grant(request.getResources());
                        } else {
                            pendingMic = request;
                            requestPermissions(
                                new String[]{android.Manifest.permission.RECORD_AUDIO}, REQ_MIC);
                        }
                        return;
                    }
                }
                request.deny();
            }

            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb,
                                             FileChooserParams p) {
                if (filePick != null) filePick.onReceiveValue(null);
                filePick = cb;
                try {
                    startActivityForResult(p.createIntent(), REQ_FILE);
                } catch (Exception e) {
                    filePick = null;
                    return false;
                }
                return true;
            }
        });

        if (android.os.Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                () -> {
                    if (web.canGoBack()) web.goBack();
                    else finish();
                });
        }

        web.loadDataWithBaseURL(null,
            "<html><body style='font-family:sans-serif;color:#6b5f57;background:#f7f2ea;"
            + "display:flex;height:100vh;align-items:center;justify-content:center;margin:0'>"
            + "<div>连环起来中…</div></body></html>", "text/html", "utf-8", null);

        bootBackend();
    }

    /** 起后端：Python 在本进程里跑 uvicorn，起来了就开首页。第一次开要几秒（解压 Python 包）。 */
    private void bootBackend() {
        new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(this));
                com.chaquo.python.PyObject boot = Python.getInstance().getModule("android_boot");
                boot.callAttr("start", getFilesDir().getAbsolutePath(), PORT);
                String token = boot.callAttr("token").toString();
                androidToken = token;
                for (int i = 0; i < 100; i++) {          // 最多等 20 秒
                    if (alive()) {
                        runOnUiThread(() -> CookieManager.getInstance().setCookie(
                            BASE, "lh_android=" + token + "; Path=/; HttpOnly; SameSite=Strict",
                            ok -> {
                                CookieManager.getInstance().flush();
                                if (ok) web.loadUrl(BASE + "/");
                                else show("本机认证票没放好，完整体没有打开。请截图发给作者。");
                            }));
                        return;
                    }
                    Thread.sleep(200);
                }
                runOnUiThread(() -> show("后端没起来。把这个页面截图发给作者。"));
            } catch (Throwable e) {
                runOnUiThread(() -> show("后端起不来：" + e));
            }
        }, "lianhuan-boot").start();
    }

    private boolean alive() {
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(BASE + "/manifest.json").openConnection();
            c.setConnectTimeout(300);
            c.setReadTimeout(300);
            int code = c.getResponseCode();
            c.disconnect();
            return code == 200 || code == 401; // 401 = 后端已起，只是在等原生层放随机票
        } catch (Exception e) {
            return false;
        }
    }

    private void show(String msg) {
        web.loadDataWithBaseURL(null,
            "<html><body style='font-family:sans-serif;padding:24px;color:#6b5f57;background:#f7f2ea'>"
            + android.text.Html.escapeHtml(msg) + "</body></html>", "text/html", "utf-8", null);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] grants) {
        if (code == REQ_MIC && pendingMic != null) {
            if (grants.length > 0 && grants[0] == android.content.pm.PackageManager.PERMISSION_GRANTED) {
                pendingMic.grant(pendingMic.getResources());
            } else {
                pendingMic.deny();
            }
            pendingMic = null;
        }
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        if (code == REQ_FILE && filePick != null) {
            filePick.onReceiveValue(
                WebChromeClient.FileChooserParams.parseResult(result, data));
            filePick = null;
            return;
        }
        super.onActivityResult(code, result, data);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
