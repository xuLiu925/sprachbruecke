#!/data/data/com.termux/files/usr/bin/bash
# 在手机 Termux 里运行：装依赖、备份数据库、导入单词书、用 tmux 后台启动服务。
# 一般不用手动跑，电脑上的 deploy.bat 会自动调用它。
set -e
cd ~/sprachbruecke

# 1. 装依赖（已装过就跳过）
command -v python >/dev/null || pkg install -y python

# 2. 备份数据库（在线备份，服务运行中也安全；只留最近 10 份）
python tools/backup_db.py deploy

command -v tmux >/dev/null || pkg install -y tmux
command -v cloudflared >/dev/null || pkg install -y cloudflared
python -c "import flask, waitress" 2>/dev/null || pip install -r requirements.txt

# 情景课课文已挪到 content/（走接口查免费次数），删掉旧位置的静态文件，免得能直接下载
rm -f static/lessons.json

# 3. 停掉旧服务
tmux kill-session -t sprachbruecke 2>/dev/null && sleep 2 || true

# 4. 单词书有变化才导入（第一次一定会导入，可能要几分钟）
if [ -f data/wordbook.json ]; then
    NEW=$(md5sum data/wordbook.json | cut -d' ' -f1)
    OLD=$(cat data/.wordbook.md5 2>/dev/null || true)
    if [ "$NEW" != "$OLD" ]; then
        echo "== 导入单词书……"
        python tools/import_wordbook.py data/wordbook.json
        echo "$NEW" > data/.wordbook.md5
    else
        echo "== 单词书没变，跳过导入"
    fi
fi

# 5. 后台启动
command -v termux-wake-lock >/dev/null && termux-wake-lock || true
tmux new -s sprachbruecke -d "cd ~/sprachbruecke && python app.py 2>&1 | tee -a server.log"
sleep 3

# 6. 检查是否启动成功
if python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/me', timeout=5)" 2>/dev/null; then
    echo "== 启动成功，端口 8000"
    echo "== 局域网访问：http://$(ip route get 1 2>/dev/null | grep -o 'src [0-9.]*' | cut -d' ' -f2):8000"
else
    echo "!! 启动失败，最近的日志："
    tail -n 30 server.log 2>/dev/null || true
    exit 1
fi

# 7. Cloudflare 快速隧道（外网访问），由 tunnel.sh 守护：断了自动重启，链接变了同步给固定入口（Worker）
# 隧道已经在跑就不重启，这样链接不变；旧版直接跑 cloudflared 的会话换成 tunnel.sh（链接会变一次）
command -v curl >/dev/null || pkg install -y curl
if [ ! -s .worker_token ]; then
    python -c "import secrets; print(secrets.token_hex(24))" > .worker_token
    chmod 600 .worker_token
fi
chmod +x tunnel.sh
if tmux has-session -t sb-tunnel 2>/dev/null && \
   ! tmux list-panes -t sb-tunnel -F '#{pane_start_command}' | grep -q tunnel.sh; then
    tmux kill-session -t sb-tunnel
    pkill -f "cloudflared tunnel --url" 2>/dev/null || true
    echo "== 隧道换成 tunnel.sh 守护，链接会变一次"
fi
if tmux has-session -t sb-tunnel 2>/dev/null; then
    echo "== 隧道已在运行，沿用原来的链接"
else
    : > tunnel.log
    tmux new -s sb-tunnel -d "bash ~/sprachbruecke/tunnel.sh"
    echo "== 正在启动隧道……"
fi
URL=""
for i in $(seq 1 30); do
    URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' tunnel.log 2>/dev/null | tail -n 1)
    [ -n "$URL" ] && break
    sleep 1
done
if [ -n "$URL" ]; then
    echo "== 外网访问：$URL"
    if [ -s .worker_url ]; then
        echo "== 固定入口：$(cat .worker_url)（链接变了会自动同步，记录在 tunnel_sync.log）"
    else
        echo "== 还没配置固定入口（.worker_url），见 docs/features/fixed-url.md"
    fi
else
    echo "!! 没拿到隧道链接，最近的日志："
    tail -n 20 tunnel.log 2>/dev/null || true
fi

# 8. 开机自启（Termux:Boot）和每天自动备份
mkdir -p ~/.termux/boot
cp boot.sh ~/.termux/boot/sprachbruecke.sh
chmod 700 ~/.termux/boot/sprachbruecke.sh
if ! tmux has-session -t sb-backup 2>/dev/null; then
    tmux new -s sb-backup -d "cd ~/sprachbruecke && while true; do python tools/backup_db.py daily >> boot.log 2>&1; sleep 3600; done"
fi
echo "== 开机自启已安装；每日备份在 backups/daily/（保留 7 份）"

# 9. 守护（每次部署都重启，用上新代码）：服务挂了自动重启、外网打不开重启隧道，发邮件；清理日志和发音缓存
tmux kill-session -t sb-watch 2>/dev/null || true
tmux new -s sb-watch -d "cd ~/sprachbruecke && python tools/watchdog.py >> watchdog.log 2>&1"
echo "== 守护已启动，记录在 watchdog.log"
