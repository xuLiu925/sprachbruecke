# 安全防护

## 功能介绍

用户看不到的保护措施，防止别人攻击网站或盗用账号。

- **安全响应头**：别的网站不能把通德嵌进自己的页面里骗用户点击（点击劫持）；页面只运行通德自己的脚本，就算哪里漏了 XSS，也加载不了外来脚本。
- **管理员保护**：服务器的数据库万一丢失、重新建成空库，不会让第一个注册的陌生人成为管理员。
- **用户名不能冒充**：新注册的用户名只能用英文字母、数字、汉字和 `_ . -`，大小写不同也算重名（有了 `liuxu` 就不能再注册 `Liuxu`）。以前注册的用户名不受影响。
- **在线发音限次**：登录用户每人每小时最多新取 300 条（缓存里有的不算，管理员不限），超了这一次退回设备语音。防止有人刷接口让谷歌封了服务器 IP，所有人都没有在线发音。
- 登录限速、验证码邮件限次、改密码作废旧会话见 [email-register.md](email-register.md) 和 [single-login.md](single-login.md)。

## 详细设计

### 涉及的文件

| 文件 | 作用 |
|---|---|
| `app.py` | `security_headers()`：每个响应加 `Content-Security-Policy`、`X-Frame-Options: DENY`、`X-Content-Type-Options: nosniff`、`Referrer-Policy` |
| `static/js/boot.js` | 启动页面（原来是 `index.html` 里的内联 `<script>boot();</script>`，CSP 不允许内联脚本） |
| `tts.py` | `user_fetch_ok()`：每个用户最近一小时新取的次数（内存里，重启清零），上限 `USER_FETCH_PER_HOUR` |
| `auth.py` | `check_username()` 用 `USERNAME_RE` 限制字符，`username_taken()` 不分大小写查重名；`ADMIN_LOCK`：管理员第一次被认出时，在数据库文件旁边写 `vocab.db.admin_lock`；有这个文件而用户表是空的时，注册返回 503 |

### CSP

`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`

- 样式允许内联：`index.html` 里有很多 `style="..."`。
- **以后加外部资源**（CDN 脚本、网络字体、外部图片、别的接口）要先改 `app.py` 的 `CSP`，不然会被浏览器拦下。新代码不能写内联 `<script>`、`onclick="..."` 属性、`eval`。
- 跳到 Stripe 付款页是页面跳转，不受 CSP 限制。

### 管理员保护

管理员仍然是编号最小的用户（`is_admin()`）。空库时第一个注册的人会成为管理员，所以：

- 已经有过管理员的服务器，数据库旁边有 `vocab.db.admin_lock`（`.gitignore` 的 `vocab.db*` 已排除）。
- 数据库是空的、又有这个文件 → 拒绝注册，服务器日志打印提示。正确做法是从备份恢复 `vocab.db`；确实要从头开始，手动删掉这个文件再注册。

### 已知限制

- 绕过 Worker 直接访问快速隧道链接的人能伪造 IP，按 IP 的限制挡不住（见 CLAUDE.md 待办第 59 项 ④）。
- 会话 cookie 没设 `Secure`：Tailscale 用 http 访问，设了会登不上。

## 变更记录

- 2026-11-04：新增安全响应头（CSP 等）和管理员保护文件。接口测试通过；本地浏览器切换全部 27 个页面、朗读，没有 CSP 拦截和控制台报错。没部署。
- 2026-11-04：新注册的用户名限制字符、大小写不同算重名；登录用户的在线发音每小时最多新取 300 条。接口测试通过，没部署。
