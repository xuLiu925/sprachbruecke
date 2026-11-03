"""给管理员发提醒邮件: 网站报错(app.py)、服务挂了 / 外网打不开(tools/watchdog.py)

收件人 = 管理员(第一个用户)绑定的邮箱, 没绑定就发给发信邮箱自己。没配置发信时只打印。
同一种提醒 QUIET 秒内只发一封, 记录在 .alert_state(网站和守护进程共用)。
"""
import json
import os
import sqlite3
import sys
import threading
import time
import traceback

import email_codes
from database import BASE, DB_PATH

STATE_FILE = os.path.join(BASE, ".alert_state")
QUIET = 3600
_lock = threading.Lock()


def recipient():
    try:
        con = sqlite3.connect(DB_PATH, timeout=5)
        try:
            row = con.execute("SELECT email FROM users ORDER BY id LIMIT 1").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        row = None
    if row and row[0]:
        return row[0]
    cfg = email_codes.config()
    return cfg["user"] if cfg else None


def _due(kind):
    """这种提醒现在能不能发; 能就记下时间"""
    with _lock:
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, ValueError):
            state = {}
        now = time.time()
        if now - state.get(kind, 0) < QUIET:
            return False
        state[kind] = now
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f)
        except OSError:
            pass
        return True


def notify(kind, subject, body):
    """发提醒, 返回是否发出。发信失败只打印, 不抛异常"""
    print(f"!! 提醒 {kind}: {subject}", file=sys.stderr, flush=True)
    if email_codes.sender is None and not email_codes.configured():
        return False
    to = recipient()
    if not to or not _due(kind):
        return False
    try:
        email_codes.send_mail(to, "[通德] " + subject, body + "\n\n同一种提醒一小时内只发一封。")
    except Exception as e:
        print(f"!! 提醒邮件没发出去: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return False
    return True


def report_error(method, path, exc):
    """网站接口出了没处理的异常(500): 后台线程发信, 不拖慢这次请求"""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    threading.Thread(target=notify, daemon=True, args=(
        f"error:{path}:{type(exc).__name__}", f"网站出错 {path}", f"{method} {path}\n\n{tb}")).start()
