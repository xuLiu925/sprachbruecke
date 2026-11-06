# 装到手机桌面（PWA）

## 功能介绍

- 网站可以“安装”到手机桌面：桌面上出现“通德”图标（深蓝底白色拱桥），点开后全屏显示，没有浏览器地址栏，用起来和普通 App 一样。
- **「今天」页顶部横幅**“装到桌面，打开更快”：登录后、用手机浏览器打开、还没装时显示。点 × 后本机 7 天内不再出现。
- 游客首页最下面和「我的」页也有“装到手机桌面”卡片。
- 点“安装”（横幅、两张卡片都一样）：
  - 浏览器支持一键安装（安卓 Chrome、Edge）：直接弹系统的安装确认。
  - 不支持：从底部弹出面板，只显示**当前浏览器**的步骤。按 UA 区分：安卓 Chrome / Edge、一加 / OPPO、小米、华为、vivo、夸克、UC、QQ 浏览器、百度、三星、火狐；iPhone 的 Safari、iOS 16.4 及以上的其他浏览器（也能从分享菜单添加）、更老系统的其他浏览器（要换 Safari）；微信 / QQ 等 App 里（先在浏览器 / Safari 中打开）；认不出来的用通用步骤。只有必须换浏览器时才有“复制链接”。**各家菜单的名字和位置都没在真机上验证过**，国产浏览器的“添加到桌面”可能只是快捷方式，有的要先在系统设置里开“桌面快捷方式”权限。
  - 从桌面图标打开时，横幅和卡片都不显示。
- **安装引导整页**：只在打开 `https://tongde.pages.dev/?install` 时显示（发给别人用，电脑上也显示），内容和上面的步骤一样。点“先在网页里用”关掉。不再自动弹出。
- 连不上服务器时，打开页面显示“连不上服务器 / 重试”，而不是浏览器自带的断网页。
- **不能离线学习**：所有内容和学习记录都在服务器上，断网时什么都做不了。

只有 HTTPS 网址能安装（`tongde.pages.dev` 和 `workers.dev` 都可以）。Tailscale 的 `http://100.x.x.x` 不行。

## 详细设计

| 文件 | 作用 |
|---|---|
| `static/manifest.json` | 名称、图标、`display: standalone`、主题色 `#1f4e78`，`start_url` 和 `scope` 都是 `/` |
| `static/icons/` | `icon-192.png`、`icon-512.png`（圆角）、`maskable-512.png`（满底，图案缩到安全区里，安卓会自己裁成圆形等形状）、`apple-touch-icon.png`（180，满底） |
| `tools/make_icons.py` | 生成上面四个图标，纯 Python，不用 PIL；要改图案就改这个脚本再重跑 |
| `static/sw.js` | Service Worker。只处理打开页面（`navigate`）：取不到时返回内置的断网页。**什么都不缓存**，所以改前端不用改它，也不会出现旧版页面 |
| `app.py` | `/sw.js` 路由：Service Worker 要在网站根目录才能管整个网站；返回 `Cache-Control: no-cache` |
| `static/index.html` | `<link rel="manifest">`、图标、苹果的 `apple-mobile-web-app-*`；「我的」页的 `#installBox` |
| `static/js/core.js` | 注册 Service Worker；记下 `beforeinstallprompt`（`installEvent`）；`showInstall()` 决定横幅（`#hInstall`，`localStorage` 的 `sb_installSnooze` = 到什么时候前不显示）和两张卡片显不显示；`doInstall()` 能一键装就装，否则 `openInstallSheet()` 弹 `#isheet`；`installGuide()` 按 UA 返回步骤（`BRAND_BROWSERS` 表 + 苹果 / 安卓 Chrome 等分支，`copy` = 要不要复制链接，`arrow` = App 内的右上角箭头）；`installGate()` 整页（`#gate`）只在 `?install` 时显示。`beforeinstallprompt` 常常晚几秒才来，整页等 1.5 秒（`installWaited`）再决定显示手动步骤，免得先闪一下 |

为什么不缓存页面：试过把页面和 JS 存下来（断网时从缓存打开），结果打开后是空壳，数字全是“-”，比直接说“连不上”更让人困惑。真要离线学习得把词库和进度存到本机再同步（待办 7b 第 9 条），是另一件事。

## 变更记录

- 2026-11-03：新增。接口测试检查了 `/sw.js`、manifest 和图标；本地浏览器看过 Service Worker 注册成功、「我的」页卡片、服务器停掉后打开显示断网页。还没部署，没在真手机上装过（安卓按钮、苹果添加到主屏幕、桌面图标样子都没实际看过）。
- 2026-11-03：已部署，用户在真手机上装成功。加安装引导整页（`?install` 链接）。
- 2026-11-03：安装引导整页改成登录后才自动出现（游客先试用，见 `guest-trial.md`），`?install` 链接不变。
- 2026-11-03：游客首页加“装到手机桌面”卡片（`#wInstallBox`，`core.js` 的 `wInstall` 和 `showInstall()`）。
- 2026-11-06：用户反馈普通浏览器一打开就是整页“看看怎么装”、还要复制链接，太麻烦。整页不再自动弹出（只留 `?install`）；改成「今天」页顶部横幅（× 后 7 天不提示）+ 底部步骤面板；按浏览器（含国产浏览器、iOS 版本）显示步骤，只有必须换浏览器时才让复制链接。「我的」页卡片改成固定说明 + 按钮。
