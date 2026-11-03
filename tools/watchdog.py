"""服务器上的守护, 在 tmux 会话 sb-watch 里一直跑(boot.sh、deploy_phone.sh 启动), 每分钟一圈:

- 本机 http://127.0.0.1:8000/api/me 连续 3 次打不开 → 重启 tmux 会话 sprachbruecke, 发邮件
- 固定网址(.worker_url)每 5 分钟查一次, 连续 3 次打不开而本机正常 → 杀掉 cloudflared
  (tunnel.sh 会重启它, 新链接自动同步给 Worker), 发邮件
- 每小时清理: 日志超过 LOG_MAX 只留最后 LOG_KEEP; tts_cache 超过 CACHE_MAX 删最久没用的;
  顺便发会员到期提醒邮件(member_mail.py)

手机整个关机、断网时它也停了, 发不出提醒。用法: python tools/watchdog.py
"""
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import alerts  # noqa: E402
import member_mail  # noqa: E402

LOCAL_URL = "http://127.0.0.1:8000/api/me"
LOGS = ("server.log", "boot.log", "tunnel_sync.log", "watchdog.log")
LOG_MAX = 5 * 1024 * 1024
LOG_KEEP = 1024 * 1024
CACHE_DIR = os.path.join(ROOT, "tts_cache")
CACHE_MAX = 300 * 1024 * 1024
FAILS = 3          # 连续几次失败才处理
STEP = 60          # 一圈几秒
REMOTE_EVERY = 5   # 几圈查一次固定网址
CLEAN_EVERY = 60   # 几圈清理一次
SERVER_CMD = "cd ~/sprachbruecke && python app.py 2>&1 | tee -a server.log"   # 和 boot.sh 一样


def log(msg):
    print(time.strftime("%F %T"), msg, flush=True)


def reachable(url, timeout=15):
    # Cloudflare 会把 Python 默认的 User-Agent(Python-urllib)当成机器人, 返回 403
    req = urllib.request.Request(url, headers={"User-Agent": "sprachbruecke-watchdog/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def tail(path, n=30):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return ""


def trim_log(path, max_size=LOG_MAX, keep=LOG_KEEP):
    """文件超过 max_size 就只留最后 keep 字节(从完整的一行开始), 返回是否动过"""
    try:
        if os.path.getsize(path) <= max_size:
            return False
        with open(path, "rb") as f:
            f.seek(-keep, os.SEEK_END)
            data = f.read()
    except OSError:
        return False
    data = data[data.find(b"\n") + 1:]
    with open(path, "r+b") as f:     # 原地改写: tee 还开着这个文件, 不能换成新文件
        f.write(data)
        f.truncate()
    return True


def prune_cache(folder=CACHE_DIR, max_size=CACHE_MAX):
    """缓存超过 max_size 就删最久没用的, 删到 max_size 的八成; 返回删了几个"""
    try:
        files = [os.path.join(folder, x) for x in os.listdir(folder)]
    except OSError:
        return 0
    stats = []
    for p in files:
        try:
            st = os.stat(p)
        except OSError:
            continue
        stats.append((max(st.st_atime, st.st_mtime), st.st_size, p))
    total = sum(s for _, s, _ in stats)
    if total <= max_size:
        return 0
    n = 0
    for _, size, p in sorted(stats):
        if total <= max_size * 0.8:
            break
        try:
            os.remove(p)
        except OSError:
            continue
        total -= size
        n += 1
    return n


def restart_server():
    subprocess.run(["tmux", "kill-session", "-t", "sprachbruecke"], stderr=subprocess.DEVNULL)
    time.sleep(2)
    subprocess.run(["tmux", "new", "-s", "sprachbruecke", "-d", SERVER_CMD])


def restart_tunnel():
    subprocess.run(["pkill", "-f", "cloudflared tunnel --url"], stderr=subprocess.DEVNULL)


def worker_url():
    try:
        with open(os.path.join(ROOT, ".worker_url"), encoding="utf-8") as f:
            return f.read().strip().rstrip("/")
    except OSError:
        return ""


def clean():
    for name in LOGS:
        if trim_log(os.path.join(ROOT, name)):
            log(f"{name} 太大, 只留最后一部分")
    n = prune_cache()
    if n:
        log(f"发音缓存删了 {n} 个最久没用的文件")
    try:
        n = member_mail.run()
        if n:
            log(f"发了 {n} 封会员到期提醒")
    except Exception as e:   # 数据库忙之类, 下个小时再试
        log(f"会员到期提醒出错: {e}")


def main():
    os.chdir(ROOT)
    local_fail = remote_fail = 0
    i = 0
    log("守护启动")
    while True:
        if reachable(LOCAL_URL):
            local_fail = 0
        else:
            local_fail += 1
            log(f"本机服务打不开（第 {local_fail} 次）")
            if local_fail >= FAILS:
                last = tail(os.path.join(ROOT, "server.log"))
                restart_server()
                log("已重启服务")
                alerts.notify("down:local", "服务挂了，已自动重启",
                              f"本机 {LOCAL_URL} 连续 {FAILS} 次打不开，已重启 tmux 会话 sprachbruecke。\n\n"
                              f"重启前 server.log 最后几行：\n{last}")
                local_fail = 0
                time.sleep(STEP)   # 给它时间启动
        url = worker_url()
        if url and i % REMOTE_EVERY == 0 and local_fail == 0:
            if reachable(url + "/api/me", timeout=30):
                remote_fail = 0
            else:
                remote_fail += 1
                log(f"固定网址打不开（第 {remote_fail} 次）")
                if remote_fail >= FAILS:
                    restart_tunnel()
                    log("已重启隧道")
                    alerts.notify("down:remote", "外网打不开，已重启隧道",
                                  f"{url} 连续 {FAILS} 次打不开（本机服务正常），已重启 cloudflared，"
                                  f"新链接会自动同步给 Worker。\n\n隧道同步日志：\n"
                                  f"{tail(os.path.join(ROOT, 'tunnel_sync.log'), 10)}")
                    remote_fail = 0
        if i % CLEAN_EVERY == 0:
            clean()
        i += 1
        time.sleep(STEP)


if __name__ == "__main__":
    main()
