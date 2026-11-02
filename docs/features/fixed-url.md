# 固定入口网址

## 功能介绍

服务器用的是 Cloudflare 快速隧道，链接（`*.trycloudflare.com`）在隧道重启后会变。固定入口用一个免费的 Cloudflare Worker 做中转：

- 用户永远访问 Worker 的网址（`https://名字.账号名.workers.dev`），收藏、登录状态、浏览器里的设置都不会因为隧道换链接而失效。
- 隧道断了会自动重启，拿到新链接后自动告诉 Worker，一般 1 分钟内恢复。
- 服务器连不上时，用户看到“服务器暂时连不上，请过一两分钟再刷新”，不是报错页面。

## 详细设计

### 涉及的文件

| 文件 | 内容 |
|---|---|
| `cloudflare/worker.js` | Worker 代码：转发请求；`POST /__tunnel` 改当前链接；连不上时显示提示页 |
| `tunnel.sh` | 服务器上守护隧道：cloudflared 退出就重启，链接变了就同步，每 10 分钟再同步一次 |
| `deploy_phone.sh` | 第一次部署时生成 `.worker_token`；把 tmux 会话 `sb-tunnel` 换成运行 `tunnel.sh` |

服务器上的文件（不进版本库）：

| 文件 | 内容 |
|---|---|
| `.worker_url` | Worker 网址，要手动写一次 |
| `.worker_token` | 改链接用的密钥，部署时自动生成，和 Worker 的 `SET_TOKEN` 一样 |
| `.tunnel_url` | 最近一次同步成功的链接 |
| `tunnel_sync.log` | 隧道启动和同步记录 |

### 做法

- Worker 把当前链接存在 KV（键 `url`），每个 Worker 实例缓存 30 秒，省 KV 读取次数。
- 改链接要带请求头 `X-Tunnel-Token`，链接必须是 `https://xxx.trycloudflare.com`，别人不能把入口指到别的网站。
- 转发时保留方法、请求头、请求体和 cookie；不自动跟随跳转，`Location` 里的隧道地址改成相对路径。
- 隧道返回 502 / 530 或连不上时，清掉缓存并显示提示页。下一次请求会重新读 KV，链接刚换时能更快恢复。

### 关键取舍

- **不买域名**：用户 2026-11-02 决定继续用服务器和快速隧道，不买域名。Worker 免费额度每天 10 万次请求，几十个用户够用。
- **不发邮件通知新链接**：换链接会让用户退出登录、丢掉本机设置，Stripe 的付款通知也要固定网址。

### 配置步骤（只做一次）

Cloudflare 网页上的按钮名称可能和下面写的不完全一样。

1. 在 <https://dash.cloudflare.com> 免费注册并登录。
2. **建 KV**：左侧菜单「存储和数据库」→「Workers KV」→ 新建，名字填 `sb_tunnel`。
3. **建 Worker**：「Workers 和 Pages」→ 创建 → 从 Hello World 开始 → 名字填 `sprachbruecke` → 部署。
4. **贴代码**：打开这个 Worker →「编辑代码」→ 删掉原来的代码，粘贴 `cloudflare/worker.js` 的全部内容 → 部署。
5. **绑定 KV**：Worker 的「绑定」→ 添加 → KV 命名空间，变量名填 `TUNNEL`，选 `sb_tunnel`。
6. **加密钥**：先在 Xshell 里运行 `cat ~/sprachbruecke/.worker_token`，复制输出。再到 Worker 的「设置」→「变量和机密」→ 添加，类型选「密钥」，名字填 `SET_TOKEN`，值粘贴刚才复制的内容。
7. **告诉服务器 Worker 网址**：在 Xshell 里运行下面的命令，把网址换成 Worker 页面上显示的那个：
   `echo https://sprachbruecke.账号名.workers.dev > ~/sprachbruecke/.worker_url`
8. 等 1 分钟后打开 Worker 网址，能看到通德就配置好了。同步记录可以用 `cat ~/sprachbruecke/tunnel_sync.log` 查看。

### 已知限制

- `workers.dev` 和 `trycloudflare.com` 在国内能不能稳定访问还不确定，要找国内的人实测。打不开的话，要买域名挂到 Cloudflare。
- 隧道断开到恢复之间（最长约 1 分钟）用户打不开页面。
- 服务器重启后 `tunnel.sh` 不会自己启动，要等开机自启（CLAUDE.md 待办第 22 项）。
- 服务器看到的访问者 IP 仍然是 127.0.0.1。Worker 会加 `X-Real-IP` 请求头，但后端还没有用。

## 变更记录

- 2026-11-02：新增。已部署，在 Cloudflare 上配置好了：同步成功，经 Worker 访问首页和 `/api/me` 正常，不带密钥改链接返回 403。还没在浏览器里登录试过，也没测过隧道重启后能不能自动恢复。
