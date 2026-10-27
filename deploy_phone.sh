#!/data/data/com.termux/files/usr/bin/bash
# 在手机 Termux 里运行：装依赖、备份数据库、导入单词书、用 tmux 后台启动服务。
# 一般不用手动跑，电脑上的 deploy.bat 会自动调用它。
set -e
cd ~/sprachbruecke

# 1. 备份数据库（有的话）
if [ -f vocab.db ]; then
    mkdir -p backups
    cp vocab.db "backups/vocab.db.$(date +%Y%m%d-%H%M%S)"
    echo "== 已备份 vocab.db 到 backups/"
fi

# 2. 装依赖（已装过就跳过）
command -v python >/dev/null || pkg install -y python
command -v tmux >/dev/null || pkg install -y tmux
command -v cloudflared >/dev/null || pkg install -y cloudflared
python -c "import flask" 2>/dev/null || pip install -r requirements.txt

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

# 7. Cloudflare 快速隧道（外网访问）
# 隧道已经在跑就不重启，这样链接不变；重启隧道链接会变
if tmux has-session -t sb-tunnel 2>/dev/null; then
    echo "== 隧道已在运行，沿用原来的链接"
else
    : > tunnel.log
    tmux new -s sb-tunnel -d "cloudflared tunnel --url http://localhost:8000 2>&1 | tee -a ~/sprachbruecke/tunnel.log"
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
else
    echo "!! 没拿到隧道链接，最近的日志："
    tail -n 20 tunnel.log 2>/dev/null || true
fi
