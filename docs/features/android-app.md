# 安卓 App

## 功能介绍

- 安卓手机可以装“通德”App：桌面图标、全屏打开，和普通 App 一样。下载地址 `https://tongde.pages.dev/tongde.apk`（约 12 KB）。
- App 只是一个“壳”，里面打开的就是网站。网站更新后，App 里马上就是新版，不用重新下载。只有改壳本身（网址、跳转规则、图标）时才要重新打包。
- 哪里会出现“下载安卓 App”：
  - 安卓手机上，浏览器**不支持一键安装**时（国产浏览器、火狐等）：「今天」页顶部横幅点“安装”、游客首页和「我的」页卡片点“下载安卓 App”，都会直接下载，并弹一行提示“下载好后点开安装，手机提醒时选‘继续安装’”。
  - 安卓 Chrome、Edge 支持一键安装时，仍然用一键安装（装成网页 App，不用下载）。
  - 微信、QQ 里下载不了安装包，还是先提示“在浏览器打开”。
  - `?install` 整页上，安卓的按钮是“下载安卓 App”。
- 在 App 里打开时，横幅、安装卡片、整页都不显示。
- 不上应用商店。安装时手机会提示“未知来源 / 有风险”，华为、荣耀、小米的纯净模式会拦得更凶，要用户点“继续安装”。

## 详细设计

| 位置 | 内容 |
|---|---|
| `android/` | 安卓壳项目，不用 AndroidX、不用 Capacitor，只用系统自带的 `WebView` 和主题，所以安装包很小。`applicationId` = `de.sprachbruecke.tongde`（发出去以后不能改，改了就是另一个 App） |
| `android/app/src/main/java/.../MainActivity.java` | 打开 `https://tongde.pages.dev/`；User-Agent 末尾加 `TongdeApp/版本`（网页据此不显示安装提示）；`http/https` 链接都在 App 里打开（包括 Stripe 付款页）；`intent://`、`alipays://`、`weixin://`、`mailto:` 等交给对应 App，没装就提示，`intent://` 有 `browser_fallback_url` 时退回网页；下载链接交给浏览器；主页面打不开时显示“连不上服务器 / 重试”；返回键先在网页里后退；切到后台时把 cookie 写盘（不用重新登录） |
| `android/app/src/main/res/` | 启动背景 `drawable/splash.xml`（蓝底 `#1f4e78` + 图标，深色模式 `drawable-night/` 用 `#0f1b26`），在 `values*/styles.xml` 里当 `windowBackground`；安卓 12 以上系统自己画启动画面，底色由 `values-v31/` 的 `windowSplashScreenBackground` 定，不设会是白色。WebView 背景透明，网页画出来之前露出启动背景，接着是网页自己的启动画面（`index.html` 的 `#splash`，同色），从点开到页面出来不闪白 |
| `android/app/build.gradle` | minSdk 24（安卓 7）、targetSdk 34、compileSdk 34，AGP 8.5.2。签名读 `android/keystore.properties`（或环境变量 `TONGDE_STORE_PASS` 等） |
| `android/build-apk.bat` | 电脑上双击打包：低优先级、单进程跑 Gradle，结果复制到 `static/tongde.apk`，再跑 `tools/apk_version.py` 写 `static/tongde.json`（版本号取自 `build.gradle`，更新说明取自 `android/release-notes.txt` 第一段；不进 git，随 `static/` 上传） |
| App 内更新 | `/api/app/version` 返回 `{version, code, notes, url}`（读 `static/tongde.json`，没有时 `version` 为 null）。`core.js` 的 `checkAppUpdate()` 只在 App 里（UA 带 `TongdeApp/版本`）启动时检查，比 `versionName` 新就在「今天」页顶部显示横幅（版本号 + 更新说明，“更新”和 ×，点 × 后这个版本 7 天内不再提示）；「我的」页底部显示“App 版本 x · 检查更新”。更新 = 打开 `/tongde.apk`，App 的下载监听交给浏览器下载，用户点开覆盖安装。这是网页功能，所以 1.0 / 1.1 不用重装也能收到提示 |
| `app.py` 的 `/tongde.apk` | 下载安装包（`application/vnd.android.package-archive`，不缓存）。安装包不进 git，随 `deploy.bat` 打包的 `static/` 一起上传 |
| `static/js/core.js` | `installKind()` 多一种 `apk`（安卓、不在微信 QQ 里、浏览器没给一键安装）；`doInstall()` 用 `<a download>` 下载；`IN_TONGDE_APP` 时当作已安装 |

**电脑上的打包环境**（不在仓库里）：Java 17（`D:\java\java-17.0.1`）、Android SDK 在 `D:\android-sdk`（`platforms;android-34`、`build-tools;34.0.0`，打包时 Gradle 自己补装了 platform-tools）、Gradle 8.7 在 `D:\android-sdk\gradle-8.7`。`android/local.properties` 写 `sdk.dir=D:/android-sdk`（不进 git）。

**签名密钥**：`android/release.jks`（PKCS12）+ `android/keystore.properties`（密码），都不进 git，另有一份在 `backups/android-key/`。**丢了就没法给已经装了的用户覆盖更新**，只能让他们卸载重装，要和数据库备份一样另存一份（比如网盘）。

**改壳以后发新版**：`android/app/build.gradle` 里 `versionCode` 加 1、`versionName` 改大（App 内更新按 `versionName` 比较，要用 1.2、1.3 这样的数字），改 `android/release-notes.txt` 第一段写这次更新了什么，双击 `android\build-apk.bat`，再跑 `deploy.bat`。部署后 App 里的用户下次打开就会看到更新提示。

**没验证的**：
- 真手机上装没装过（安装拦截、桌面图标）。
- 付款：Stripe 付款页里点支付宝 / 微信支付能不能跳到对应 App，付完能不能回到 App 并开通会员。Stripe 在手机网页上的微信支付可能只给二维码，在同一台手机上没法扫。
- 深色模式下状态栏颜色、WebView 的 `prefers-color-scheme` 跟不跟系统。
- 有的手机系统 WebView 很旧，页面可能有显示问题。

## 变更记录

- 2026-11-06：第一版。自己写的 WebView 壳（没用 Capacitor，省掉 npm 依赖，安装包 12 KB），本机打包签名，放在服务器 `/tongde.apk`；安卓上浏览器不能一键安装时，安装提示改成直接下载 App。
- 2026-11-08：1.1（versionCode 2）。启动背景从白色改成蓝底 + 图标，WebView 透明，和网页的启动画面接上，打开时不再白屏。签名和 1.0 相同，可以覆盖安装；已装的 App 不会自己更新，要重新下载 `/tongde.apk`。真手机上没看过。
- 2026-11-08：App 内更新提示：打包时生成 `static/tongde.json`，`/api/app/version` 给最新版本，App 里有新版时首页显示横幅、「我的」页能检查更新，下载交给浏览器。这是网页功能，已经装了的 1.0 / 1.1 都能用。本地浏览器只检查了版本比较和横幅显示（模拟不了 App 的 User-Agent），真手机上没试过下载和覆盖安装。
