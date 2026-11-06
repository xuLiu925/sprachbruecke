package de.sprachbruecke.tongde;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

/**
 * 通德安卓 App: 全屏 WebView 打开网站, 网站更新后这里自动是新版。
 * 只有改这个壳(网址、跳转规则、图标)时才要重新打包。
 * - 网页里的 https 链接都在 App 里打开(包括 Stripe 付款页)
 * - alipays:// weixin:// intent:// mailto: 等交给手机上对应的 App
 * - User-Agent 末尾加 "TongdeApp/版本", 网页据此不显示“装到桌面”
 */
public class MainActivity extends Activity {
    static final String HOME = "https://tongde.pages.dev/";
    private WebView web;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        web = new WebView(this);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);   // 自动朗读
        s.setUserAgentString(s.getUserAgentString() + " TongdeApp/" + BuildConfig.VERSION_NAME);

        CookieManager cm = CookieManager.getInstance();
        cm.setAcceptCookie(true);
        cm.setAcceptThirdPartyCookies(web, true);

        web.setWebChromeClient(new WebChromeClient());   // 有它 alert / confirm / prompt 才会弹出来
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                return openOutside(r.getUrl());
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (r.isForMainFrame()) showOffline();
            }
        });
        // 网页里点到要下载的文件(比如新版安装包): 交给浏览器下载
        web.setDownloadListener((url, ua, cd, mime, len) -> openOutside(Uri.parse(url), true));

        if (saved != null) web.restoreState(saved);
        else web.loadUrl(HOME);
    }

    /** true = 已经交给别的 App 处理, WebView 不用打开 */
    private boolean openOutside(Uri u) {
        return openOutside(u, false);
    }

    private boolean openOutside(Uri u, boolean force) {
        String scheme = u.getScheme() == null ? "" : u.getScheme().toLowerCase();
        if (!force && (scheme.equals("http") || scheme.equals("https"))) return false;
        try {
            if (scheme.equals("intent")) {
                Intent it = Intent.parseUri(u.toString(), Intent.URI_INTENT_SCHEME);
                it.addCategory(Intent.CATEGORY_BROWSABLE);
                it.setComponent(null);
                it.setSelector(null);
                try {
                    startActivity(it);
                } catch (ActivityNotFoundException e) {
                    String fallback = it.getStringExtra("browser_fallback_url");
                    if (fallback != null) web.loadUrl(fallback);
                    else Toast.makeText(this, "手机上没装对应的 App", Toast.LENGTH_SHORT).show();
                }
                return true;
            }
            startActivity(new Intent(Intent.ACTION_VIEW, u).addCategory(Intent.CATEGORY_BROWSABLE));
        } catch (Exception e) {   // 没装支付宝 / 微信, 或者链接格式不对
            Toast.makeText(this, "手机上没装对应的 App", Toast.LENGTH_SHORT).show();
        }
        return true;
    }

    private void showOffline() {
        String html = "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
                + "<body style='font-family:sans-serif;text-align:center;padding:30vh 24px 0;color:#555'>"
                + "<p style='font-size:18px'>连不上服务器</p><p>看看网络，或者过一会儿再试</p>"
                + "<button style='margin-top:16px;padding:12px 32px;font-size:16px;border:0;border-radius:10px;"
                + "background:#1f4e78;color:#fff' onclick=\"location.href='" + HOME + "'\">重试</button></body>";
        web.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onPause() {
        super.onPause();
        web.onPause();
        CookieManager.getInstance().flush();   // 登录状态马上写盘, 被系统杀掉也不用重新登录
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
    }
}
