#!/data/data/com.termux/files/usr/bin/bash
# 守护 Cloudflare 快速隧道，在 tmux 会话 sb-tunnel 里运行（deploy_phone.sh 会启动它）：
#   - cloudflared 退出了就重新启动（链接会变）
#   - 链接变了，就告诉 Cloudflare Worker（固定入口，见 cloudflare/worker.js），用户的网址不用变
#   - 每 10 分钟再同步一次，防止上次没发出去
# 需要 ~/sprachbruecke/.worker_url（Worker 网址）和 .worker_token（和 Worker 的 SET_TOKEN 一样）；
# 没有这两个文件时只守护隧道，不同步。
cd ~/sprachbruecke
PID=""
LAST=""
N=0
trap '[ -n "$PID" ] && kill "$PID" 2>/dev/null' EXIT HUP INT TERM

while true; do
    if [ -z "$PID" ] || ! kill -0 "$PID" 2>/dev/null; then
        : > tunnel.log
        cloudflared tunnel --url http://localhost:8000 >> tunnel.log 2>&1 &
        PID=$!
        LAST=""
        echo "$(date '+%F %T') 启动隧道" >> tunnel_sync.log
    fi
    URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' tunnel.log 2>/dev/null | tail -n 1)
    N=$((N + 1))
    [ $((N % 30)) -eq 0 ] && LAST=""          # 20 秒一圈，30 圈 = 10 分钟
    if [ -n "$URL" ] && [ "$URL" != "$LAST" ] && [ -s .worker_url ] && [ -s .worker_token ]; then
        if curl -fsS -m 15 -X POST "$(cat .worker_url)/__tunnel" \
                -H "X-Tunnel-Token: $(cat .worker_token)" -H "Content-Type: application/json" \
                -d "{\"url\":\"$URL\"}" >/dev/null 2>>tunnel_sync.log; then
            [ "$URL" != "$(cat .tunnel_url 2>/dev/null)" ] && echo "$(date '+%F %T') 已同步 $URL" >> tunnel_sync.log
            echo "$URL" > .tunnel_url
            LAST=$URL
        fi
    fi
    sleep 20
done
