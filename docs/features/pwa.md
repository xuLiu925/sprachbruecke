# 装到手机桌面（PWA）

## 功能介绍

- 网站可以“安装”到手机桌面：桌面上出现“通德”图标（深蓝底白色拱桥），点开后全屏显示，没有浏览器地址栏，用起来和普通 App 一样。
- 游客首页最下面也有“📲 装到手机桌面”卡片：浏览器给了安装许可（安卓 Chrome、Edge）时按钮是“安装到桌面”，点了直接弹系统安装确认；否则是“看看怎么装”，打开安装引导整页。
- 「我的」页最上面有“装到手机桌面”卡片：
  - 安卓 Chrome、Edge 等支持一键安装的浏览器，卡片上会有“安装到桌面”按钮。
  - 苹果手机：提示用 Safari 点“分享”，再选“添加到主屏幕”。
  - 微信、QQ 内置浏览器装不了：提示先点右上角“…”，选“在浏览器打开”。
  - 其他浏览器：提示从浏览器菜单里选“添加到主屏幕”或“安装应用”。
  - 已经从桌面图标打开时，这张卡片不显示；电脑上浏览器不提供安装时也不显示。
- **安装引导整页**：登录后用手机浏览器打开、还没装的时候，先整页显示“通德 / 安装到桌面”，按浏览器显示对应的装法（安卓按钮、苹果三步、微信 QQ 右上角箭头 + “在浏览器打开”、其他浏览器菜单步骤，需要换浏览器时有“复制链接”）。点“先在网页里用”就关掉，这次打开不再出现，下次打开还会出现。发给别人的链接用 `https://tongde.pages.dev/?install`：带 `?install` 时电脑上也显示。装好后从桌面图标打开不显示。
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
| `static/js/core.js` | 注册 Service Worker；记下 `beforeinstallprompt`（`installEvent`）；`showInstall()` 按浏览器决定卡片显示什么；`installGate()` 安装引导整页（`#gate`）：`gateWanted()` = 不是从桌面打开 且（带 `?install` 或 已登录 且 手机触屏 且 这次没点过跳过，`sessionStorage` 的 `sb_gateSkip`）。`beforeinstallprompt` 常常晚几秒才来，来了再把步骤换成按钮 |

为什么不缓存页面：试过把页面和 JS 存下来（断网时从缓存打开），结果打开后是空壳，数字全是“-”，比直接说“连不上”更让人困惑。真要离线学习得把词库和进度存到本机再同步（待办 7b 第 9 条），是另一件事。

## 变更记录

- 2026-11-03：新增。接口测试检查了 `/sw.js`、manifest 和图标；本地浏览器看过 Service Worker 注册成功、「我的」页卡片、服务器停掉后打开显示断网页。还没部署，没在真手机上装过（安卓按钮、苹果添加到主屏幕、桌面图标样子都没实际看过）。
- 2026-11-03：已部署，用户在真手机上装成功。加安装引导整页（`?install` 链接）。
- 2026-11-03：安装引导整页改成登录后才自动出现（游客先试用，见 `guest-trial.md`），`?install` 链接不变。
- 2026-11-03：游客首页加“装到手机桌面”卡片（`#wInstallBox`，`core.js` 的 `wInstall` 和 `showInstall()`）。
