"""邮箱验证码和发信(只用标准库)

发信用 SMTP, 默认 Gmail(smtp.gmail.com:465 + 应用专用密码)。配置放服务器上的 .mail_config(JSON, 不进版本库):
    {"user": "xxx@gmail.com", "password": "应用专用密码"}       可选 "host" / "port"
也可以用环境变量 MAIL_USER / MAIL_PASSWORD。没有配置时不能发验证码, 注册方式默认退回邀请码(auth.register_mode)。

验证码 6 位数字, 10 分钟有效, 输错 5 次作废, 只存哈希。为了不被刷:
同一个邮箱 60 秒内只能发一次、一小时最多 5 次; 全站每天最多 DAILY_MAX 封(Gmail 免费每天约 500 封)。
"""
import hashlib
import json
import os
import re
import secrets
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from database import BASE, fmt_time, get_db, now_str

CONFIG_FILE = os.path.join(BASE, ".mail_config")
CODE_MINUTES = 10
MAX_TRIES = 5
RESEND_SECONDS = 60
HOURLY_MAX = 5
DAILY_MAX = 200
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PURPOSES = {"register": "注册", "reset": "找回密码", "bind": "绑定邮箱"}

sender = None   # 测试时换成 fn(to, subject, body), 不真的发信


def norm_email(s):
    """去空格、转小写; 格式不对返回空字符串"""
    s = str(s or "").strip().lower()
    return s if len(s) <= 254 and EMAIL_RE.match(s) else ""


def config():
    if os.environ.get("MAIL_USER") and os.environ.get("MAIL_PASSWORD"):
        return {"user": os.environ["MAIL_USER"], "password": os.environ["MAIL_PASSWORD"]}
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return None
    return cfg if cfg.get("user") and cfg.get("password") else None


def configured():
    return config() is not None


def send_mail(to, subject, body):
    if sender is not None:
        return sender(to, subject, body)
    cfg = config()
    msg = EmailMessage()
    msg["From"] = f"通德 Sprachbrücke <{cfg['user']}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP_SSL(cfg.get("host", "smtp.gmail.com"), int(cfg.get("port", 465)),
                          context=ssl.create_default_context(), timeout=20) as s:
        s.login(cfg["user"], cfg["password"])
        s.send_message(msg)


def _hash(email, purpose, code):
    return hashlib.sha256(f"{purpose}:{email}:{code}".encode()).hexdigest()


def send_code(email, purpose):
    """给 email 发验证码。成功返回 None, 否则返回给用户看的错误信息"""
    if sender is None and not configured():
        return "邮件服务还没配置，请联系管理员"
    db = get_db()
    now = datetime.now(timezone.utc)
    last = db.execute("SELECT MAX(sent_at) FROM mail_log WHERE email = ?", (email,)).fetchone()[0]
    if last and last > fmt_time(now - timedelta(seconds=RESEND_SECONDS)):
        return "发得太快了，请 1 分钟后再试"
    hour = db.execute("SELECT COUNT(*) FROM mail_log WHERE email = ? AND sent_at > ?",
                      (email, fmt_time(now - timedelta(hours=1)))).fetchone()[0]
    if hour >= HOURLY_MAX:
        return "这个邮箱一小时内收了太多验证码，请稍后再试"
    day = db.execute("SELECT COUNT(*) FROM mail_log WHERE sent_at >= ?", (now_str()[:10],)).fetchone()[0]
    if day >= DAILY_MAX:
        return "今天发的邮件太多了，请明天再试"
    code = f"{secrets.randbelow(10 ** 6):06d}"
    what = PURPOSES[purpose]
    body = (f"你的通德{what}验证码是：{code}\n\n"
            f"{CODE_MINUTES} 分钟内有效。如果不是你本人操作，请忽略这封邮件。\n\n通德 Sprachbrücke")
    try:
        send_mail(email, f"通德{what}验证码：{code}", body)
    except Exception as e:      # 发信失败不能让接口 500, 原因写进服务器日志
        print(f"!! 发信失败 {purpose}: {type(e).__name__}: {e}", file=sys.stderr)
        return "邮件没发出去，请检查邮箱地址，或稍后再试"
    db.execute("INSERT INTO email_codes (email, purpose, code_hash, expires_at, tries) VALUES (?,?,?,?,0) "
               "ON CONFLICT(email, purpose) DO UPDATE SET code_hash = excluded.code_hash, "
               "expires_at = excluded.expires_at, tries = 0",
               (email, purpose, _hash(email, purpose, code), fmt_time(now + timedelta(minutes=CODE_MINUTES))))
    db.execute("INSERT INTO mail_log (email, purpose, sent_at) VALUES (?,?,?)", (email, purpose, now_str()))
    db.commit()
    return None


def check_code(email, purpose, code):
    """验证码对: 删掉它(不提交, 由调用的人和后面的修改一起提交)并返回 None; 不对: 记一次错误并返回错误信息"""
    db = get_db()
    row = db.execute("SELECT code_hash, expires_at, tries FROM email_codes WHERE email = ? AND purpose = ?",
                     (email, purpose)).fetchone()
    if row is None or row["expires_at"] < now_str() or row["tries"] >= MAX_TRIES:
        return "验证码无效或已过期，请重新发送"
    if not secrets.compare_digest(row["code_hash"], _hash(email, purpose, re.sub(r"\D", "", str(code or "")))):
        db.execute("UPDATE email_codes SET tries = tries + 1 WHERE email = ? AND purpose = ?", (email, purpose))
        db.commit()
        return "验证码不对"
    db.execute("DELETE FROM email_codes WHERE email = ? AND purpose = ?", (email, purpose))
    return None
