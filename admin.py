"""管理后台(文档 docs/features/admin.md)

只有管理员能用(auth.admin_required)。页面在 static/js/admin.js, 入口在「我的」页。
- 概览: 用户、活跃、会员、付款、待处理、今天的学习和 AI 用量
- 用户: 按通德 ID / 用户名 / 昵称 / 邮箱搜索, 看一个人的详情, 停用 / 恢复账号
  (重置密码、送会员仍是原来的接口: auth.py 的 reset_password、billing.py 的 membership)
- 内容: 反馈和报错(feedback.py)、待审核单词(word_add.py)、邀请码(auth.py), 接口不变, 只是页面挪到后台
活跃靠 user_settings 的 last_seen(auth.check_login 每 10 分钟最多写一次), 2026-11-08 才开始记。
"""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

import billing
from auth import BAN_KEY, SEEN_KEY, admin_required, drop_login, is_admin
from database import fmt_time, get_db, now_str
from helpers import current_user_id, err, json_body
from word_store import MISSING_MEANING

bp = Blueprint("admin", __name__)

PAGE = 50            # 用户列表一页几个
MAX_REASON = 200


def ago(**kw):
    return fmt_time(datetime.now(timezone.utc) - timedelta(**kw))


def ahead(**kw):
    return fmt_time(datetime.now(timezone.utc) + timedelta(**kw))


@bp.route("/api/admin/overview")
@admin_required
def overview():
    db, now = get_db(), now_str()
    one = lambda sql, *a: db.execute(sql, a).fetchone()[0] or 0
    seen = lambda since: one("SELECT COUNT(*) FROM user_settings WHERE key = ? AND value >= ?", SEEN_KEY, since)
    paid = db.execute("SELECT currency, COUNT(*) AS n, SUM(amount) AS total FROM payments "
                      "WHERE status = 'paid' AND paid_at >= ? GROUP BY currency", (ago(days=30),)).fetchall()
    day = billing.today_key()
    return jsonify({
        "users": {
            "total": one("SELECT COUNT(*) FROM users"),
            "new_7d": one("SELECT COUNT(*) FROM users WHERE created_at >= ?", ago(days=7)),
            "active_1d": seen(ago(days=1)),
            "active_7d": seen(ago(days=7)),
            "banned": one("SELECT COUNT(*) FROM user_settings WHERE key = ?", BAN_KEY),
        },
        "members": {
            "active": one("SELECT COUNT(*) FROM memberships WHERE until > ?", now),
            "expiring_7d": one("SELECT COUNT(*) FROM memberships WHERE until > ? AND until <= ?", now, ahead(days=7)),
        },
        "payments": {
            "today": one("SELECT COUNT(*) FROM payments WHERE status = 'paid' AND paid_at >= ?", ago(days=1)),
            "month": [dict(r) for r in paid],     # 最近 30 天, 按币种; total 以分为单位
        },
        "todo": {
            "feedback": one("SELECT COUNT(*) FROM feedback WHERE done_at IS NULL"),
            "reports": one("SELECT COUNT(*) FROM content_reports"),
            "pending": one("SELECT COUNT(*) FROM words WHERE status = 'pending' "
                           "OR (status = 'public' AND meaning = ?)", MISSING_MEANING),
        },
        "today": {
            "reviews": one("SELECT COUNT(*) FROM review_log WHERE reviewed_at >= ?", ago(days=1)),
            "learners": one("SELECT COUNT(DISTINCT user_id) FROM review_log WHERE reviewed_at >= ?", ago(days=1)),
            # 今天(管理员的本地日期)新生成的 AI 内容, 和免费用户用掉的 AI 次数
            "ai_generated": one("SELECT SUM(count) FROM usage_daily WHERE day = ? AND feature = 'aigen'", day),
            "ai_free": one("SELECT COUNT(*) FROM usage_daily WHERE day = ? AND feature LIKE 'ai:%'", day),
        },
    })


USER_COLS = (
    "SELECT u.id, u.uid, u.username, u.nickname, u.email, u.created_at, "
    "(SELECT value FROM user_settings s WHERE s.user_id = u.id AND s.key = :seen) AS last_seen, "
    "(SELECT value FROM user_settings s WHERE s.user_id = u.id AND s.key = :ban) AS banned, "
    "(SELECT until FROM memberships m WHERE m.user_id = u.id AND m.until > :now) AS member_until, "
    "(SELECT COUNT(*) FROM progress p WHERE p.user_id = u.id) AS learned FROM users u "
)


def user_row(r, me_id, admin_id):
    return {**dict(r), "me": r["id"] == me_id, "admin": r["id"] == admin_id}


@bp.route("/api/admin/users")
@admin_required
def users():
    """?q= 搜索(通德 ID、用户名、昵称、邮箱, 不分大小写) &filter= member / banned &offset=; 新注册的在前"""
    q = (request.args.get("q") or "").strip().lower()
    flt = request.args.get("filter") or ""
    try:
        offset = max(int(request.args.get("offset") or 0), 0)
    except ValueError:
        offset = 0
    db = get_db()
    args = {"seen": SEEN_KEY, "ban": BAN_KEY, "now": now_str(), "like": f"%{q}%", "lim": PAGE + 1, "off": offset}
    where = []
    if q:
        where.append("(u.uid LIKE :like OR lower(u.username) LIKE :like OR lower(coalesce(u.nickname, '')) LIKE :like "
                     "OR coalesce(u.email, '') LIKE :like)")
    if flt == "member":
        where.append("member_until IS NOT NULL")
    elif flt == "banned":
        where.append("banned IS NOT NULL")
    # 用子查询包一层, 才能按 member_until / banned 这些算出来的列筛选
    sql = (f"SELECT * FROM ({USER_COLS}) u" + (" WHERE " + " AND ".join(where) if where else "")
           + " ORDER BY u.id DESC LIMIT :lim OFFSET :off")
    rows = db.execute(sql, args).fetchall()
    total = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    admin_id = db.execute("SELECT MIN(id) FROM users").fetchone()[0]
    me_id = current_user_id()
    return jsonify({"users": [user_row(r, me_id, admin_id) for r in rows[:PAGE]],
                    "more": len(rows) > PAGE, "total": total})


@bp.route("/api/admin/users/<int:uid>")
@admin_required
def user_detail(uid):
    db, now = get_db(), now_str()
    r = db.execute(f"{USER_COLS} WHERE u.id = :id", {"seen": SEEN_KEY, "ban": BAN_KEY, "now": now, "id": uid}).fetchone()
    if r is None:
        return err("用户不存在", 404)
    one = lambda sql, *a: db.execute(sql, a).fetchone()[0] or 0
    admin_id = db.execute("SELECT MIN(id) FROM users").fetchone()[0]
    pays = db.execute("SELECT plan, amount, currency, status, created_at, paid_at FROM payments WHERE user_id = ? "
                      "ORDER BY created_at DESC LIMIT 20", (uid,)).fetchall()
    last_day = db.execute("SELECT MAX(day) FROM usage_daily WHERE user_id = ?", (uid,)).fetchone()[0]
    usage = db.execute("SELECT feature, count FROM usage_daily WHERE user_id = ? AND day = ? ORDER BY feature",
                       (uid, last_day)).fetchall() if last_day else []
    m = db.execute("SELECT until FROM memberships WHERE user_id = ?", (uid,)).fetchone()
    return jsonify({
        **user_row(r, current_user_id(), admin_id),
        "member_last": m["until"] if m else None,          # 过期的也给, 看得出以前是不是会员
        "mastered": one("SELECT COUNT(*) FROM progress WHERE user_id = ? AND stability >= 21 AND spell_ok > 0", uid),
        "reviews_7d": one("SELECT COUNT(*) FROM review_log WHERE user_id = ? AND reviewed_at >= ?", uid, ago(days=7)),
        "last_review": db.execute("SELECT MAX(reviewed_at) FROM review_log WHERE user_id = ?", (uid,)).fetchone()[0],
        "added_words": one("SELECT COUNT(*) FROM user_added_words WHERE user_id = ?", uid),
        "lessons": one("SELECT COUNT(*) FROM custom_lessons WHERE user_id = ?", uid),
        "feedback": one("SELECT COUNT(*) FROM feedback WHERE user_id = ?", uid),
        "payments": [dict(p) for p in pays],
        "usage_day": last_day,
        "usage": [dict(u) for u in usage],
    })


@bp.route("/api/admin/users/<int:uid>/ban", methods=["POST"])
@admin_required
def ban(uid):
    """{banned: true, reason} 停用账号(马上下线, 不能再登录, 数据都留着) / {banned: false} 恢复"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    if uid == current_user_id() or is_admin(uid):
        return err("不能停用管理员账号")
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE id = ?", (uid,)).fetchone() is None:
        return err("用户不存在", 404)
    if data.get("banned"):
        reason = str(data.get("reason") or "").strip()[:MAX_REASON] or "（没写原因）"
        db.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?) "
                   "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value", (uid, BAN_KEY, reason))
        drop_login(uid)
    else:
        db.execute("DELETE FROM user_settings WHERE user_id = ? AND key = ?", (uid, BAN_KEY))
    db.commit()
    return jsonify({"ok": True, "banned": bool(data.get("banned"))})
