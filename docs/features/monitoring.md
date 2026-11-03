# 运行稳定性：waitress、出错提醒、守护和自动清理

## 功能介绍

- **waitress**：网站改用 waitress 运行（纯 Python 的正式 WSGI 服务器，8 个线程），不再用 Flask 自带的开发服务器。没装 waitress 时自动退回开发服务器，网站照样能用。
- **出错提醒**：接口出了没处理的错误（返回 500）时，给管理员发一封邮件，带出错的接口和错误详情。同一个接口的同一种错误一小时只发一封。
- **守护**：服务器上一直运行的小程序，每分钟检查一次：
  - 本机服务连续 3 次打不开 → 自动重启服务，发邮件（附带重启前的日志）。
  - 固定网址每 5 分钟查一次，连续 3 次打不开而本机服务正常 → 重启 Cloudflare 隧道（新链接会自动同步给固定入口），发邮件。
- **自动清理**：每小时检查一次，日志文件超过 5 MB 只留最后 1 MB；在线发音缓存超过 300 MB 删掉最久没用的。

提醒邮件发给管理员绑定的邮箱；管理员没绑定邮箱时发给发信邮箱自己。没配置发信时只写进日志。

**发现不了的情况**：手机关机、没电、断网、Termux 被系统杀掉时，守护本身也停了，发不出提醒。

## 详细设计

| 文件 | 作用 |
|---|---|
| `app.py` | 启动时先试 `waitress.serve(threads=8)`，导入失败用 `app.run()`；`got_request_exception` 信号接到 `alerts.report_error()` |
| `alerts.py` | `notify(kind, subject, body)` 发提醒；`report_error()` 在后台线程发信，不拖慢请求。限频记录在 `.alert_state`（网站和守护共用，按 `kind` 一小时一封）。错误按路由模板分类（`/api/words/<int:wid>`），不按具体编号 |
| `tools/watchdog.py` | 守护，tmux 会话 `sb-watch`，输出写 `watchdog.log`。重启服务的命令和 `boot.sh` 一样；重启隧道 = `pkill` 掉 cloudflared，由 `tunnel.sh` 重新启动 |
| `boot.sh` | 开机时启动 `sb-watch` |
| `deploy_phone.sh` | 每次部署都重启 `sb-watch`（用上新代码）；`flask` 或 `waitress` 没装时 `pip install -r requirements.txt` |

清理：`trim_log()` 原地改写文件（`tee -a` 还开着它，不能换新文件），从完整的一行开始保留；`prune_cache()` 按访问 / 修改时间删最旧的，删到上限的八成。清理的日志：`server.log`、`boot.log`、`tunnel_sync.log`、`watchdog.log`。

部署时服务会停几秒，守护要连续 3 次（约 3 分钟）失败才处理，不会误重启。

## 变更记录

- 2026-11-03：新增。接口测试通过（假的发信：报错发一封、一小时内不重复；日志裁剪和缓存清理）；本地用 waitress 启动过，页面和接口正常。还没部署，服务器上的 waitress 安装、守护的重启和邮件还没实际验证。
