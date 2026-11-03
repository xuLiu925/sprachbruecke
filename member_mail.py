"""会员到期提醒邮件: 由 tools/watchdog.py 每小时调一次 run()。

会员还剩不到 DAYS 天、账号绑定了邮箱的, 发一封“快到期了”。发过的记在 user_settings 的 expiry_mail
(值 = 当时的到期时间), 同一个到期时间只发一次; 续费后到期时间变了, 下次快到期再发。
直接用 sqlite3, 不依赖 Flask(守护进程里没有应用上下文)。没配置发信时什么都不做。
"""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import email_codes
from database import DB_PATH, fmt_time, parse_time

DAYS = 3
KEY = "expiry_mail"
SITE = "https://tongde.pages.dev"
BEIJING = timezone(timedelta(hours=8))   # 用户大多在国内, 邮件里的日期按北京时间写


def due(con, now):
    """该发提醒的人: [(user_id, username, email, until)]"""
    return con.execute(
        "SELECT u.id, u.username, u.email, m.until FROM memberships m JOIN users u ON u.id = m.user_id "
        "LEFT JOIN user_settings s ON s.user_id = u.id AND s.key = ? "
        "WHERE u.email IS NOT NULL AND m.until > ? AND m.until <= ? AND (s.value IS NULL OR s.value != m.until)",
        (KEY, fmt_time(now), fmt_time(now + timedelta(days=DAYS)))).fetchall()


def body(username, until, now):
    left = max(1, -(-(parse_time(until) - now).total_seconds() // 86400))
    day = parse_time(until).astimezone(BEIJING)
    return (f"{username}，你好：\n\n你的通德会员还剩 {int(left)} 天，{day.month}月{day.day}日到期。"
            f"到期后回到免费版，大部分练习每天有次数限制，学习记录不受影响。\n\n"
            f"想继续不限次数地练，可以在「我的」页续费；现在续费会接着往后加，不会浪费剩下的天数：\n{SITE}/#me\n\n"
            f"通德 Sprachbrücke")


def run(now=None):
    """发该发的提醒, 返回发出了几封"""
    if email_codes.sender is None and not email_codes.configured():
        return 0
    now = now or datetime.now(timezone.utc)
    con = sqlite3.connect(DB_PATH, timeout=10)
    sent = 0
    try:
        for uid, username, email, until in due(con, now):
            try:
                email_codes.send_mail(email, "[通德] 会员快到期了", body(username, until, now))
            except Exception as e:   # 一个人发失败不影响别人, 下个小时再试
                print(f"会员提醒发给 {uid} 失败: {e}", file=sys.stderr, flush=True)
                continue
            con.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?,?,?) "
                        "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value", (uid, KEY, until))
            con.commit()
            sent += 1
    finally:
        con.close()
    return sent
