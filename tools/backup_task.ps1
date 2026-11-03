# 在电脑上登记 Windows 计划任务: 每天 21:00 跑 backup.bat, 把服务器的每日备份拉到 backups\server\
# 电脑那时关着就在下次开机后补跑; 日志在 backups\server\backup.log。
# 用法(PowerShell): powershell -ExecutionPolicy Bypass -File tools\backup_task.ps1
# 删除任务: Unregister-ScheduledTask -TaskName "Sprachbruecke Backup" -Confirm:$false
# 要先在 deploy.local.bat 里写好 PHONE_USER 和 BACKUP_IP, 并且电脑到服务器的 SSH 不用密码
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root "backups\server\backup.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
$cmd = "/c set NOPAUSE=1&& call `"$root\backup.bat`" >> `"$log`" 2>&1"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $cmd -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At 21:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "Sprachbruecke Backup" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Sprachbruecke: download the server's daily database backups" -Force | Out-Null
Write-Output "已登记: 每天 21:00 下载服务器备份到 $root\backups\server"
