#!/data/data/com.termux/files/usr/bin/bash
# 开机自启：deploy_phone.sh 把它复制到 ~/.termux/boot/sprachbruecke.sh，Termux:Boot 开机时运行。
# 也可以手动运行 bash ~/sprachbruecke/boot.sh，已经在跑的会话不会重启。
cd ~/sprachbruecke
LOG=~/sprachbruecke/boot.log
echo "$(date '+%F %T') 开机启动" >> "$LOG"
termux-wake-lock 2>/dev/null || true

# Android 12 的幽灵进程限制会杀掉 Termux 的子进程，重启后可能被重置，要重新关掉（要 root）
if command -v su >/dev/null; then
    su -c "settings put global settings_enable_monitor_phantom_procs false; \
           device_config put activity_manager max_phantom_processes 2147483647" >> "$LOG" 2>&1 \
        || echo "$(date '+%F %T') !! 没能关掉幽灵进程限制" >> "$LOG"
fi

sleep 15    # 等 WiFi 连上

start() {   # start 会话名 命令：会话不存在才启动
    if tmux has-session -t "$1" 2>/dev/null; then
        echo "$(date '+%F %T') $1 已在运行" >> "$LOG"
    else
        tmux new -s "$1" -d "$2"
        echo "$(date '+%F %T') 启动 $1" >> "$LOG"
    fi
}
start sprachbruecke "cd ~/sprachbruecke && python app.py 2>&1 | tee -a server.log"
start sb-tunnel "bash ~/sprachbruecke/tunnel.sh"
# 每小时检查一次，今天还没备份就备份一份
start sb-backup "cd ~/sprachbruecke && while true; do python tools/backup_db.py daily >> boot.log 2>&1; sleep 3600; done"
