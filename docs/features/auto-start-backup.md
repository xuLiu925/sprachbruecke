# 开机自启和自动备份

## 功能介绍

- **开机自启**：服务器重启后，自动启动服务、隧道（经固定入口访问的网址不变）和每日备份，并重新关掉 Android 12 的幽灵进程限制。
- **每天自动备份**：每小时检查一次，当天还没备份就备份一份，保留最近 7 天。
- **部署前备份**：每次部署前备份一份，保留最近 10 份。
- **拉到电脑**：在电脑上双击 `backup.bat`，把服务器上的每日备份下载到 `backups\server\`（只下载电脑上还没有的），电脑上保留最近 30 份。

## 详细设计

### 涉及的文件

| 文件 | 内容 |
|---|---|
| `tools/backup_db.py` | `daily` / `deploy` 两种备份，压缩，清理旧的备份 |
| `boot.sh` | 开机脚本，部署时复制到 `~/.termux/boot/sprachbruecke.sh` |
| `deploy_phone.sh` | 部署前备份改用 `backup_db.py deploy`；安装开机脚本；启动 tmux 会话 `sb-backup` |
| `backup.bat` | 电脑上运行：先让服务器备份当天的，再下载没有的文件 |
| `tools/backup_task.ps1` | 电脑上运行一次：登记 Windows 计划任务，每天自动跑 `backup.bat` |

### 做法

- 用 SQLite 的在线备份（`sqlite3.Connection.backup`）。以前部署时直接 `cp`，服务运行中可能拷到写了一半的数据。备份先写临时文件，完成后再改名，中途失败不会留下坏文件。
- 文件名带日期，按名字排序就是按时间排序，清理时删最旧的。
- 开机脚本只启动还没在运行的 tmux 会话（`sprachbruecke`、`sb-tunnel`、`sb-backup`），手动再跑一次也不会重复启动。启动记录写进 `boot.log`。
- 原来的 `~/.termux/boot/start.sh`（sshd 和 8080 测试页）没有改动。

### 恢复备份

在 Xshell 里依次运行：

```
tmux kill-session -t sprachbruecke
cd ~/sprachbruecke
cp vocab.db vocab.db.before-restore
gunzip -c backups/daily/vocab.日期.db.gz > vocab.db
bash boot.sh
```

### 已知限制

- 开机自启还没有真正重启过服务器来验证。
- 电脑自动拉备份要先登记一次计划任务：PowerShell 里运行 `powershell -ExecutionPolicy Bypass -File tools\backup_task.ps1`，每天 21:00 跑 `backup.bat`（电脑那时关着就开机后补跑），日志在 `backups\server\backup.log`。要在 `deploy.local.bat` 里写 `BACKUP_IP`（服务器的 Tailscale 地址，不会变），电脑到服务器的 SSH 不能要密码（定时运行时不会等输入）。电脑关机好几天时，服务器只留 7 份，中间的会丢。
- 服务器的电池和 MIUI 杀后台问题，代码管不了。

## 变更记录

- 2026-11-02：新增。已部署：每日备份已生成，解压后数据库检查正常；`backup.bat` 已成功下载。开机自启还没重启验证。
- 2026-11-02：部署备份的清理也包括以前没压缩的旧备份，一共只留最近 10 份（服务器上的备份从 238 MB 降到 38 MB）。
- 2026-11-03：电脑定时拉备份：`backup.bat` 能从 `deploy.local.bat` 读 `BACKUP_IP`，`NOPAUSE=1` 时 SSH 不等密码；新增 `tools/backup_task.ps1` 登记计划任务。修了 `deploy.local.bat` 在这台电脑上读不到的问题（改成绝对路径）。用 Tailscale 地址不等待地跑过一次，下载成功；计划任务还没登记。
