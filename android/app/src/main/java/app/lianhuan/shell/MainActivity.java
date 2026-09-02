package app.lianhuan.shell;

/*
 * 连环的安卓壳 —— 一个 WebView，指向你自己跑的连环服务。
 *
 * 它只做四件事，一件不多：
 *   1. 全屏打开你填的服务地址（首次打开会先问你地址）
 *   2. 返回键 = 网页后退（页面里那套安卓返回桥就是为这个准备的）
 *   3. 页面要麦克风（打电话）时，替它把系统权限要下来
 *   4. 长按标题区三下…没有标题区 —— 改地址：在页面里随便一处**长按 1.2 秒**会弹设置
 *
 * 没做的也说清楚：推送不在这个壳里。Web Push 要浏览器/HTTPS 那套；
 * 壳里塞个后台轮询在国产 ROM 上活不过半小时，装了等于骗你。
 * 想要锁屏推送：Chrome 开 HTTPS 的站点、添加到主屏幕（README 有步骤）。
 */

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.LinearLayout;

public class MainActivity extends Activity {

    private WebView web;
    private SharedPreferences prefs;
    private ValueCallback<Uri[]> filePick;          // <input type=file> 的回调
    private static final int REQ_FILE = 11;
    private static final int REQ_MIC = 12;
    private PermissionRequest pendingMic;
    private long downAt = 0;                        // 长按计时（改地址入口）

    @Override
    @SuppressLint("SetJavaScriptEnabled")
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        prefs = getSharedPreferences("lianhuan", MODE_PRIVATE);

        web = new WebView(this);
        setContentView(web);

        // debug 构建开 WebView 远程调试（chrome://inspect / CDP）——
        // 真机验收时电脑能连进来看页面、点 DOM。release 包不开。
        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            WebView.setWebContentsDebuggingEnabled(true);
        }

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);   // 通话页的提示音、TTS 自动播

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                // 只有自己服务上的页面留在壳里；外面的链接丢给系统浏览器
                String base = serverBase();
                String url = req.getUrl().toString();
                if (base != null && url.startsWith(base)) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, req.getUrl()));
                } catch (Exception ignored) { }
                return true;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                // 页面要麦克风（打电话）。先要系统权限，拿到了再放行给页面。
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
                // 发照片 / 发文件那两颗要走系统选择器
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

        // 长按 1.2 秒改服务器地址（壳上没有别的按钮，这是唯一的门）
        web.setOnTouchListener((v, ev) -> {
            switch (ev.getActionMasked()) {
                case android.view.MotionEvent.ACTION_DOWN: downAt = System.currentTimeMillis(); break;
                case android.view.MotionEvent.ACTION_MOVE: downAt = 0; break;                 // 滑动不算
                case android.view.MotionEvent.ACTION_UP:
                    if (downAt > 0 && System.currentTimeMillis() - downAt > 1200) askServer(false);
                    downAt = 0;
                    break;
            }
            return false;                                    // 事件照常给页面
        });

        // ★ Android 13+ 的返回走 OnBackInvokedDispatcher —— targetSdk 36 在 Android 16 上
        //   预测式返回默认开，老的 onBackPressed() **根本不会被调用**，
        //   用户按返回直接回了桌面（0831 真机上抓的）。两条路都留：新系统走这个回调，
        //   老系统走下面的 onBackPressed()。
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                () -> {
                    if (web.canGoBack()) web.goBack();
                    else finish();
                });
        }

        String base = serverBase();
        if (base == null) askServer(true);
        else web.loadUrl(base + "/");
    }

    private String serverBase() {
        String v = prefs.getString("server", null);
        if (v == null) return null;
        return v.replaceAll("/+$", "");
    }

    private void askServer(boolean first) {
        EditText in = new EditText(this);
        in.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        in.setHint("http://192.168.x.x:8420");
        String cur = prefs.getString("server", "");
        in.setText(cur.isEmpty() ? "http://localhost:8420" : cur);
        LinearLayout box = new LinearLayout(this);
        box.setPadding(48, 24, 48, 0);
        box.addView(in, new LinearLayout.LayoutParams(-1, -2));

        new AlertDialog.Builder(this)
            .setTitle("连环在哪台电脑上？")
            .setMessage("填电脑上服务的地址。\n· 同一 Wi-Fi：http://电脑的IP:8420\n"
                        + "· USB 连着电脑（adb reverse）：http://localhost:8420")
            .setView(box)
            .setCancelable(!first)
            .setPositiveButton("好", (d, w) -> {
                String v = in.getText().toString().trim();
                if (v.isEmpty()) { if (first) askServer(true); return; }
                if (!v.startsWith("http")) v = "http://" + v;
                prefs.edit().putString("server", v).apply();
                web.loadUrl(v.replaceAll("/+$", "") + "/");
            })
            .show();
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
        // 返回键 = 网页后退。页面那套「安卓返回桥」（history/popstate）接得住这个。
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }
}
