"""会员、免费次数和付款(Stripe Checkout, 一次性付款, 不自动续费)

免费用户: 今日学习、词库、查词、语法基础不限; 其他练习每天有次数(LIMITS), 会员和管理员不限。
次数在 before_app_request 里统一查, 接口返回 200 才算用了一次, 各练习模块不用改。

付款: 前端 POST /api/billing/checkout → 跳到 Stripe 的付款页(银行卡、支付宝、微信支付, 在 Stripe 后台打开哪些就显示哪些)
→ 付完回到 /?paid=会话编号#me, 前端调 /api/billing/confirm 向 Stripe 核对; Stripe 也会调 /api/stripe/webhook。
两条路都走 grant(), 同一笔只算一次。
配置: 服务器上的 .stripe_config {"secret_key": "sk_...", "webhook_secret": "whsec_..."}(不进版本库),
也可以用环境变量 STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET。
"""
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, request

from auth import admin_required, is_admin
from database import BASE, fmt_time, get_db, now_str, parse_time
from helpers import current_user_id, err, json_body, login_required
from today import MAX_TZ, local_day

bp = Blueprint("billing", __name__)

CONFIG_FILE = os.path.join(BASE, ".stripe_config")
CURRENCY = "cny"
PLANS = {   # amount 以分为单位
    "month": {"name": "月卡", "days": 30, "amount": 1800},
    "year": {"name": "年卡", "days": 365, "amount": 12800},
}

# 路径 → (名字, 每天几组, 按哪个参数分开算)
LIMITS = {
    "/api/drill/articles": ("冠词练习", 3, None),
    "/api/drill/dictation": ("听写", 3, None),
    "/api/sentences": ("句子练习", 2, "mode"),
    "/api/grammar/nouns": ("定冠词练习", 2, None),
    "/api/grammar/articles": ("冠词变格练习", 2, "type"),
    "/api/grammar/verbs": ("动词现在时练习", 2, None),
    "/api/grammar/perfekt": ("完成时练习", 2, None),
    "/api/grammar/usage": ("动词搭配练习", 2, None),
    "/api/plural": ("复数练习", 2, None),
    "/api/forms/cases": ("变格练习", 2, None),
    "/api/forms/verbs": ("变位练习", 2, None),
    "/api/roleplay/due": ("整句复习", 1, None),
}
LESSONS_PER_DAY = 1   # 每天能开几节新的情景课; 开过的课以后随时能再看, 自建的课不算
LESSON_RE = re.compile(r"^/api/roleplay/lesson/([\w-]+)$")
SESSION_RE = re.compile(r"^cs_(test|live)_[A-Za-z0-9]+$")
TOLERANCE = 300       # webhook 签名的时间最多差 5 分钟
ENFORCE = True        # 测试里关掉, 别的模块的测试不受次数限制


# ---------- 配置和 Stripe 接口 ----------
def config():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            cfg = {}
    return {
        "secret_key": os.environ.get("STRIPE_SECRET_KEY") or cfg.get("secret_key", ""),
        "webhook_secret": os.environ.get("STRIPE_WEBHOOK_SECRET") or cfg.get("webhook_secret", ""),
    }


class StripeError(Exception):
    pass


def stripe(method, path, data=None):
    """调 Stripe 接口, 返回 JSON; 测试里会替换成假的"""
    key = config()["secret_key"]
    if not key:
        raise StripeError("还没有配置收款")
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request("https://api.stripe.com/v1/" + path, data=body, method=method,
                                 headers={"Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("error", {}).get("message", "")
        except ValueError:
            msg = ""
        print("Stripe 出错:", e.code, msg, flush=True)
        raise StripeError(msg or "收款服务出错")
    except (urllib.error.URLError, TimeoutError) as e:
        print("Stripe 连不上:", e, flush=True)
        raise StripeError("连不上收款服务, 请稍后再试")


def check_signature(payload, header, secret):
    """Stripe-Signature: t=时间,v1=签名[,v1=...]; 签名 = HMAC-SHA256(secret, "时间.请求体")"""
    parts = [p.split("=", 1) for p in (header or "").split(",") if "=" in p]
    stamp = next((v for k, v in parts if k == "t"), "")
    sigs = [v for k, v in parts if k == "v1"]
    if not stamp.isdigit() or not sigs or abs(time.time() - int(stamp)) > TOLERANCE:
        return False
    want = hmac.new(secret.encode(), stamp.encode() + b"." + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(want, s) for s in sigs)


# ---------- 会员 ----------
def member_until(uid):
    row = get_db().execute("SELECT until FROM memberships WHERE user_id = ?", (uid,)).fetchone()
    return row["until"] if row and row["until"] > now_str() else None


def unlimited(uid):
    if "unlimited" not in g:
        g.unlimited = is_admin(uid) or member_until(uid) is not None
    return g.unlimited


def extend(db, uid, days):
    """会员加 days 天: 没过期就从到期时间往后加, 过期了从现在算"""
    row = db.execute("SELECT until FROM memberships WHERE user_id = ?", (uid,)).fetchone()
    now = datetime.now(timezone.utc)
    start = max(now, parse_time(row["until"])) if row else now
    until = fmt_time(start + timedelta(days=days))
    db.execute("INSERT INTO memberships (user_id, until, updated_at) VALUES (?,?,?) "
               "ON CONFLICT(user_id) DO UPDATE SET until = excluded.until, updated_at = excluded.updated_at",
               (uid, until, now_str()))
    return until


def grant(s):
    """Stripe 的 Checkout 会话已付款 → 开会员。同一笔只算一次; 金额对不上不开"""
    if s.get("payment_status") != "paid":
        return False
    db = get_db()
    row = db.execute("SELECT * FROM payments WHERE session_id = ?", (s.get("id"),)).fetchone()
    if row is None:
        return False
    if row["status"] == "paid":
        return True
    if s.get("amount_total") != row["amount"] or s.get("currency") != row["currency"]:
        print("付款金额对不上:", row["session_id"], s.get("amount_total"), s.get("currency"), flush=True)
        return False
    if db.execute("UPDATE payments SET status = 'paid', paid_at = ? WHERE session_id = ? AND status != 'paid'",
                  (now_str(), row["session_id"])).rowcount == 1 and row["user_id"] is not None:
        extend(db, row["user_id"], PLANS[row["plan"]]["days"])
    db.commit()
    return True


# ---------- 免费次数 ----------
def today_key():
    try:
        tz = min(max(int(request.headers.get("X-TZ") or request.args.get("tz") or 0), -MAX_TZ), MAX_TZ)
    except ValueError:
        tz = 0
    return local_day(tz)[0]


def used(uid, day, feature):
    row = get_db().execute("SELECT count FROM usage_daily WHERE user_id = ? AND day = ? AND feature = ?",
                           (uid, day, feature)).fetchone()
    return row["count"] if row else 0


def lesson_check(uid, day, lesson_id):
    """开过的课随时能再看("seen"); 没开过的, 今天开的新课没到上限才行("new"), 否则返回提示文字。
    每节课只在第一次打开那天记一行, 所以按今天的行数就是今天开的新课数"""
    db = get_db()
    if db.execute("SELECT 1 FROM usage_daily WHERE user_id = ? AND feature = ?",
                  (uid, "lesson:" + lesson_id)).fetchone():
        return "seen"
    n = db.execute("SELECT COUNT(*) FROM usage_daily WHERE user_id = ? AND day = ? AND feature LIKE 'lesson:%'",
                   (uid, day)).fetchone()[0]
    if n < LESSONS_PER_DAY:
        return "new"
    return f"免费版每天能学 {LESSONS_PER_DAY} 节新的情景课（学过的课随时能再看），今天的已经用完了。开通会员不限次数。"


def check_lesson(uid, lesson_id):
    """情景课: 不行返回 402, 第一次打开就记下来(返回 200 时才记)"""
    if lesson_id.startswith("u"):   # 自建的课
        return None
    day = today_key()
    r = lesson_check(uid, day, lesson_id)
    if r == "new":
        g.quota = (uid, day, "lesson:" + lesson_id)
    elif r != "seen":
        return paywall(r)
    return None


def paywall(msg):
    return jsonify({"error": msg, "paywall": True}), 402


@bp.before_app_request
def check_quota():
    uid = current_user_id()
    if uid is None or request.method != "GET" or not ENFORCE:
        return None
    path = request.path
    lesson = LESSON_RE.match(path)
    rule = LIMITS.get(path)
    if not lesson and not rule:
        return None
    if path == "/api/roleplay/due" and request.args.get("count"):   # 首页只看数量, 不算
        return None
    if unlimited(uid):
        return None
    if lesson:
        return check_lesson(uid, lesson.group(1))
    day = today_key()
    name, limit, arg = rule
    feature = path + (":" + request.args.get(arg, "") if arg else "")
    if used(uid, day, feature) >= limit:
        return paywall(f"免费版每天能做 {limit} 组{name}，今天的已经用完了。开通会员不限次数。")
    g.quota = (uid, day, feature)
    return None


@bp.after_app_request
def count_quota(resp):
    q = g.pop("quota", None)
    if q and resp.status_code == 200:
        db = get_db()
        db.execute("INSERT INTO usage_daily (user_id, day, feature, count) VALUES (?,?,?,1) "
                   "ON CONFLICT(user_id, day, feature) DO UPDATE SET count = count + 1", q)
        db.commit()
    return resp


@bp.route("/api/usage/lesson", methods=["POST"])
@login_required
def open_lesson():
    """打开一节情景课(课文是静态文件, 前端打开前先来这里登记)"""
    data = json_body() or {}
    lesson_id = str(data.get("id", ""))
    if not re.fullmatch(r"[\w-]{1,40}", lesson_id):
        return err("课程编号不对")
    uid = current_user_id()
    if ENFORCE and not unlimited(uid):
        blocked = check_lesson(uid, lesson_id)
        if blocked:
            return blocked
    return jsonify({"ok": True})


# ---------- 接口 ----------
@bp.route("/api/billing")
@login_required
def status():
    uid = current_user_id()
    day = today_key()
    usage = []
    if not unlimited(uid):
        rows = get_db().execute("SELECT feature, count FROM usage_daily WHERE user_id = ? AND day = ?",
                                (uid, day)).fetchall()
        counts = {r["feature"]: r["count"] for r in rows}
        for path, (name, limit, arg) in LIMITS.items():
            n = sum(c for f, c in counts.items() if f == path or f.startswith(path + ":"))
            if n:
                usage.append({"name": name, "used": n, "limit": limit, "split": bool(arg)})
    return jsonify({
        "admin": is_admin(uid),
        "until": member_until(uid),
        "enabled": bool(config()["secret_key"]),
        "plans": [{"id": k, "name": p["name"], "days": p["days"], "price": p["amount"] / 100} for k, p in PLANS.items()],
        "usage": usage,
    })


@bp.route("/api/billing/checkout", methods=["POST"])
@login_required
def checkout():
    data = json_body()
    plan = PLANS.get((data or {}).get("plan"))
    if plan is None:
        return err("请选择月卡或年卡")
    origin = request.headers.get("Origin") or request.host_url.rstrip("/")
    if not re.fullmatch(r"https?://[\w.:-]+", origin):
        return err("网址不对")
    uid = current_user_id()
    email = get_db().execute("SELECT email FROM users WHERE id = ?", (uid,)).fetchone()["email"]
    params = {
        "mode": "payment",
        "locale": "zh",
        "line_items[0][quantity]": 1,
        "line_items[0][price_data][currency]": CURRENCY,
        "line_items[0][price_data][unit_amount]": plan["amount"],
        "line_items[0][price_data][product_data][name]": f"通德会员 · {plan['name']}（{plan['days']} 天）",
        "client_reference_id": uid,
        "metadata[user_id]": uid,
        "metadata[plan]": data["plan"],
        "success_url": origin + "/?paid={CHECKOUT_SESSION_ID}#me",
        "cancel_url": origin + "/#me",
    }
    if email:
        params["customer_email"] = email
    try:
        s = stripe("POST", "checkout/sessions", params)
    except StripeError as e:
        return err(str(e), 502)
    db = get_db()
    db.execute("INSERT INTO payments (session_id, user_id, plan, amount, currency, status, created_at) "
               "VALUES (?,?,?,?,?,'open',?)", (s["id"], uid, data["plan"], plan["amount"], CURRENCY, now_str()))
    db.commit()
    return jsonify({"url": s["url"]})


@bp.route("/api/billing/confirm")
@login_required
def confirm():
    """付完款回来时核对一次(webhook 没到也能开会员)"""
    sid = request.args.get("session_id", "")
    if not SESSION_RE.match(sid):
        return err("付款编号不对")
    row = get_db().execute("SELECT user_id FROM payments WHERE session_id = ?", (sid,)).fetchone()
    if row is None or row["user_id"] != current_user_id():
        return err("找不到这笔付款", 404)
    try:
        s = stripe("GET", "checkout/sessions/" + sid)
    except StripeError as e:
        return err(str(e), 502)
    paid = grant(s)
    return jsonify({"paid": paid, "until": member_until(current_user_id())})


@bp.route("/api/stripe/webhook", methods=["POST"])
def webhook():
    secret = config()["webhook_secret"]
    payload = request.get_data()
    if not secret or not check_signature(payload, request.headers.get("Stripe-Signature"), secret):
        return err("签名不对", 400)
    try:
        event = json.loads(payload)
    except ValueError:
        return err("格式不对", 400)
    if event.get("type") in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        grant(event.get("data", {}).get("object", {}))
    return jsonify({"ok": True})


@bp.route("/api/admin/users/<int:uid>/membership", methods=["POST"])
@admin_required
def set_membership(uid):
    """管理员送会员 {days}: 大于 0 = 加这么多天; 0 = 取消"""
    data = json_body()
    try:
        days = int((data or {}).get("days"))
    except (TypeError, ValueError):
        return err("天数不对")
    if not 0 <= days <= 3660:
        return err("天数不对")
    db = get_db()
    if not db.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone():
        return err("没有这个用户", 404)
    if days:
        extend(db, uid, days)
    else:
        db.execute("DELETE FROM memberships WHERE user_id = ?", (uid,))
    db.commit()
    return jsonify({"until": member_until(uid)})
