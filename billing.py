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
EXPIRED_SHOW = 7     # 到期后几天内页面上还提示“会员已到期”(首页提醒的天数在 home.js 的 MEMBER_WARN)
LESSONS_PER_DAY = 1  # 每天能开几节新的情景课; 开过的课以后随时能再看, 自建的课不算
LESSON_RE = re.compile(r"^/api/(?:lessons|roleplay/lesson)/([\w-]+)$")
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
TZ_KEY = "quota_tz"      # user_settings: 免费次数按哪个时区算, 值 = "时区分钟,改的时间戳"
TZ_CHANGE_SECONDS = 86400
ARG_DEFAULTS = {"mode": "cloze"}   # 不带参数时接口用的默认值, 计数要和带上默认值时算同一样


def today_key():
    """免费次数算在哪一天(用户本地日期, 凌晨 4 点换日)"""
    if "quota_day" in g:
        return g.quota_day
    try:
        tz = min(max(int(request.headers.get("X-TZ") or request.args.get("tz") or 0), -MAX_TZ), MAX_TZ)
    except ValueError:
        tz = 0
    uid = current_user_id()
    if uid is not None:
        tz = pinned_tz(uid, tz)
    g.quota_day = local_day(tz)[0]
    return g.quota_day


def pinned_tz(uid, tz):
    """用这个用户记下的时区; 时区变了(出国、夏令时)最多 24 小时改一次。
    不然来回改时区, 同一时刻能凑出两三个不同的“今天”, 多拿几天的次数"""
    db = get_db()
    row = db.execute("SELECT value FROM user_settings WHERE user_id = ? AND key = ?", (uid, TZ_KEY)).fetchone()
    now = int(time.time())
    if row:
        try:
            old, at = (int(x) for x in row["value"].split(","))
        except ValueError:
            old, at = None, 0
        if old is not None and (old == tz or now - at < TZ_CHANGE_SECONDS):
            return old
    db.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?) "
               "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value", (uid, TZ_KEY, f"{tz},{now}"))
    db.commit()
    return tz


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
    """情景课: 不行返回 402。新课先记下来再数今天开了几节(同时开两节新课时不会都放过去),
    接口最后没返回 200 就删掉这条(count_quota)"""
    if lesson_id.startswith("u"):   # 自建的课
        return None
    day = today_key()
    r = lesson_check(uid, day, lesson_id)
    if r == "seen":
        return None
    if r != "new":
        return paywall(r)
    db, feature = get_db(), "lesson:" + lesson_id
    db.execute("INSERT OR IGNORE INTO usage_daily (user_id, day, feature, count) VALUES (?,?,?,1)", (uid, day, feature))
    db.commit()
    n = db.execute("SELECT COUNT(*) FROM usage_daily WHERE user_id = ? AND day = ? AND feature LIKE 'lesson:%'",
                   (uid, day)).fetchone()[0]
    if n > LESSONS_PER_DAY:
        db.execute("DELETE FROM usage_daily WHERE user_id = ? AND day = ? AND feature = ?", (uid, day, feature))
        db.commit()
        return paywall(lesson_check(uid, day, lesson_id))
    g.quota_refund = ("lesson", uid, day, feature)
    return None


def paywall(msg, title=None, stay=False):
    """stay = 关掉弹窗后留在当前页面(AI、会员功能: 页面本身还能用); 否则前端退回上一页(练习页没题了)"""
    body = {"error": msg, "paywall": True}
    if title:
        body["title"] = title
    if stay:
        body["stay"] = True
    return jsonify(body), 402


# ---------- AI 次数(文档 docs/features/ai-quota.md) ----------
# 免费用户: 讲解、AI 查词、构词、联想记忆共用每天 AI_FREE 次, 每样东西当天第一次用才算(usage_daily 的 ai:键 一样一行);
# 讲解打开就算, 查词 / 构词 / 联想记忆只有新生成才算(已有的随便看, 由各模块决定调不调 ai_block)。
# 会员不限次数, 但和免费用户一样每天最多新生成 AI_GEN_CAP 条(aigen), 防刷费用。管理员都不限
AI_FREE = 5
AI_GEN_CAP = 200
CUSTOM_PER_DAY = 3     # 会员每天能用 AI 生成几次自建对话
AI_MSG = (f"免费版每天能用 {AI_FREE} 次 AI（句子讲解、AI 查词、构词解释、联想记忆），今天的已经用完了。"
          "开通会员不限次数。")


def ai_used(uid, day):
    return get_db().execute("SELECT COUNT(*) FROM usage_daily WHERE user_id = ? AND day = ? AND feature LIKE 'ai:%'",
                            (uid, day)).fetchone()[0]


def ai_block(uid, key, generate=False):
    """用一次 AI 之前查: 能用返回 None, 否则返回 402(免费次数用完) / 429(今天生成太多) 响应。
    key = 用的是哪样东西, 如 note:句子编号、parts:词"""
    if not ENFORCE or is_admin(uid):
        return None
    day = today_key()
    if generate and used(uid, day, "aigen") >= AI_GEN_CAP:
        return err(f"今天新生成的 AI 内容太多了（每天最多 {AI_GEN_CAP} 条），明天再来吧", 429)
    if unlimited(uid) or used(uid, day, "ai:" + key):
        return None
    if ai_used(uid, day) >= AI_FREE:
        return paywall(AI_MSG, stay=True)
    return None


def ai_can_generate(uid):
    """现在能不能新生成(前端决定显示“生成”还是“还没有”); 免费用户次数用完时也返回 True, 点了再弹会员"""
    return not unlimited(uid) or ai_block(uid, "?", generate=True) is None


def ai_done(uid, key, generated=False):
    """用成功了再记: 免费用户记 ai:key, 新生成的记 aigen。管理员不记"""
    if not ENFORCE or is_admin(uid):
        return
    day, db = today_key(), get_db()
    for feature in ([] if unlimited(uid) else ["ai:" + key]) + (["aigen"] if generated else []):
        db.execute("INSERT INTO usage_daily (user_id, day, feature, count) VALUES (?,?,?,1) "
                   "ON CONFLICT(user_id, day, feature) DO UPDATE SET count = count + 1", (uid, day, feature))
    db.commit()


def member_only(uid, name):
    """会员功能: 会员和管理员返回 None, 免费用户返回 402"""
    if not ENFORCE or unlimited(uid):
        return None
    return paywall(f"{name}是会员功能。开通会员就能用，AI 讲解和各种练习也都不限次数。", title="这是会员功能", stay=True)


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
    feature = path + (":" + (request.args.get(arg) or ARG_DEFAULTS.get(arg, "")) if arg else "")
    # 先占一次(没到上限才加 1, 一条语句做完, 同时发几个请求也不会超), 接口最后没返回 200 再退回去
    db = get_db()
    cur = db.execute("INSERT INTO usage_daily (user_id, day, feature, count) VALUES (?,?,?,1) "
                     "ON CONFLICT(user_id, day, feature) DO UPDATE SET count = count + 1 WHERE count < ?",
                     (uid, day, feature, limit))
    db.commit()
    if cur.rowcount == 0:
        return paywall(f"免费版每天能做 {limit} 组{name}，今天的已经用完了。开通会员不限次数。")
    g.quota_refund = ("count", uid, day, feature)
    return None


@bp.after_app_request
def count_quota(resp):
    """先占的次数: 接口返回 200 就算用了, 否则退回(报错、参数不对的请求不算)"""
    q = g.pop("quota_refund", None)
    if q and resp.status_code != 200:
        kind, uid, day, feature = q
        db = get_db()
        if kind == "lesson":
            db.execute("DELETE FROM usage_daily WHERE user_id = ? AND day = ? AND feature = ?", (uid, day, feature))
        else:
            db.execute("UPDATE usage_daily SET count = count - 1 WHERE user_id = ? AND day = ? AND feature = ? "
                       "AND count > 0", (uid, day, feature))
        db.commit()
    return resp


@bp.route("/api/usage/lesson", methods=["POST"])
@login_required
def open_lesson():
    """旧版前端打开情景课前来这里登记; 新版直接 GET /api/lessons/<id>, 留着兼容还没刷新的页面"""
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
        n = sum(1 for f in counts if f.startswith("ai:"))
        if n:
            usage.append({"name": "AI（讲解、查词、构词、联想记忆）", "used": n, "limit": AI_FREE, "split": False})
    row = get_db().execute("SELECT until FROM memberships WHERE user_id = ?", (uid,)).fetchone()
    until = member_until(uid)
    # 最近 EXPIRED_SHOW 天内到期的, 页面上提示“会员已到期”
    expired = (row["until"] if row and not until
               and row["until"] > fmt_time(datetime.now(timezone.utc) - timedelta(days=EXPIRED_SHOW)) else None)
    return jsonify({
        "admin": is_admin(uid),
        "until": until,
        "expired": expired,
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
    # 手机上不给微信支付: Stripe 在手机网页上的微信支付只显示二维码, 同一台手机扫不了(微信也不让扫相册里的付款码)。
    # 付款方式由 Stripe 后台统一管理(payment_method_types 已不能用, 2026-11-06 线上报 400), 手机上只排除微信支付;
    # Stripe 不认排除参数时去掉它再建一次, 保证至少能付款
    ua = request.headers.get("User-Agent", "")
    mobile = data.get("mobile") is True or bool(re.search(r"Android|iPhone|iPad|iPod|Mobile|TongdeApp/", ua))
    if mobile:
        params["excluded_payment_method_types[0]"] = "wechat_pay"
    try:
        try:
            s = stripe("POST", "checkout/sessions", params)
        except StripeError as e:
            if not mobile or "excluded_payment_method_types" not in str(e):
                raise
            print("Stripe 不接受排除微信支付, 改成不排除:", e, flush=True)
            del params["excluded_payment_method_types[0]"]
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
