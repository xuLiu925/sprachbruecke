"""账号: 注册 / 登录 / 退出 / 当前用户 / 改密码 / 邮件找回密码 / 绑定邮箱; 管理员: 邀请码、成员列表、重置密码

管理员 = 第一个注册的用户(编号最小), 他注册时什么都不要。之后的注册方式见 register_mode():
    email   先验证邮箱(验证码)再注册, 配置了发信(email_codes.py)时的默认方式;
            带了邀请码(管理员发的邀请链接 ?invite=)就不用邮箱, 注册页平时不显示邀请码
    invite  要管理员发的邀请码, 没配置发信时的默认方式
    open    什么都不要
环境变量 REGISTER_MODE 可以指定; 旧的 ALLOW_REGISTER=1 等于 open。
登录可以用用户名或邮箱, 所以用户名里不能有 @。
"""
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import email_codes
from database import fmt_time, get_db, now_str
from email_codes import norm_email
from helpers import current_user_id, err, json_body, login_required

bp = Blueprint("auth", __name__)

# 登录失败限速(内存里, 重启清零): 同一用户名 10 分钟内最多失败 8 次
_fail = {}
FAIL_WINDOW = 600
FAIL_MAX = 8

INVITE_DAYS = 7                                   # 邀请码几天后过期
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"    # 去掉了容易看错的 I L O 0 1
LOGIN_KEY = "login_token"                         # user_settings 里存当前登录令牌的键
# 不用登录的接口: 会话过期时照常处理, 不返回“已在别的设备登录”
NO_LOGIN_PATHS = {"/api/me", "/api/login", "/api/register", "/api/register/code",
                  "/api/password/forgot", "/api/password/reset"}


def too_many_fails(name):
    t = time.time()
    lst = [x for x in _fail.get(name, []) if t - x < FAIL_WINDOW]
    _fail[name] = lst
    return len(lst) >= FAIL_MAX


def record_fail(name):
    _fail.setdefault(name, []).append(time.time())


def random_code(n):
    return "".join(secrets.choice(CODE_CHARS) for _ in range(n))


def norm_code(s):
    """用户输入的邀请码: 去掉横线空格, 转大写"""
    return re.sub(r"[^0-9A-Za-z]", "", str(s or "")).upper()


def show_code(code):
    return code[:4] + "-" + code[4:]


def register_mode():
    mode = os.environ.get("REGISTER_MODE", "")
    if mode in ("email", "invite", "open"):
        return mode
    if os.environ.get("ALLOW_REGISTER", "0") == "1":
        return "open"
    return "email" if email_codes.configured() else "invite"


def check_username(username):
    """注册时的用户名: 返回错误信息, 没问题返回 None"""
    if not (3 <= len(username) <= 32):
        return "用户名长度需要 3-32 个字符"
    if "@" in username:
        return "用户名里不能有 @"
    return None


def email_taken(email, uid=None):
    row = get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    return row is not None and row["id"] != uid


def is_admin(uid):
    return uid is not None and uid == get_db().execute("SELECT MIN(id) FROM users").fetchone()[0]


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if current_user_id() is None:
            return err("请先登录", 401)
        if not is_admin(current_user_id()):
            return err("只有管理员能做这件事", 403)
        return fn(*a, **kw)

    return wrapper


def login_ok(uid, username):
    # 一个账号同时只能一个设备登录: 每次登录换一个令牌, 存在 user_settings, 旧设备的令牌就对不上了
    tok = secrets.token_hex(16)
    db = get_db()
    db.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?) "
               "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value", (uid, LOGIN_KEY, tok))
    db.commit()
    session.clear()
    session["uid"] = uid
    session["tok"] = tok
    session.permanent = True
    return jsonify({"username": username, "admin": is_admin(uid)})


def drop_login(uid):
    """让这个账号所有设备的登录失效"""
    get_db().execute("DELETE FROM user_settings WHERE user_id = ? AND key = ?", (uid, LOGIN_KEY))


@bp.before_app_request
def check_login():
    """会话里的令牌和数据库里的不一样 = 这个账号后来在别的设备登录了(或被重置了密码), 这边下线。
    两边都没有令牌 = 这个功能上线前登的, 先放行, 下次在任何设备登录后就要对上了。"""
    uid = session.get("uid")
    if uid is None:
        return None
    row = get_db().execute("SELECT value FROM user_settings WHERE user_id = ? AND key = ?",
                           (uid, LOGIN_KEY)).fetchone()
    stored = row["value"] if row else None
    if session.get("tok") == stored:
        return None
    session.clear()
    if request.path.startswith("/api/") and request.path not in NO_LOGIN_PATHS:
        return err("这个账号已在别的设备登录, 请重新登录", 401)
    return None


@bp.route("/api/register/code", methods=["POST"])
def register_code():
    """邮箱注册第一步 {username, email}: 先检查用户名和邮箱能不能用, 再发验证码"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    if register_mode() != "email":
        return err("现在不用邮箱注册")
    username = str(data.get("username", "")).strip()
    email = norm_email(data.get("email"))
    bad = check_username(username)
    if bad:
        return err(bad)
    if not email:
        return err("邮箱格式不对")
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        return err("用户名已存在", 409)
    if email_taken(email):
        return err("这个邮箱已经注册过了，可以直接登录或找回密码", 409)
    bad = email_codes.send_code(email, "register")
    return err(bad, 429) if bad else jsonify({"ok": True})


@bp.route("/api/register", methods=["POST"])
def register():
    data = json_body()
    if data is None:
        return err("请求格式错误")
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    bad = check_username(username)
    if bad:
        return err(bad)
    if len(password) < 8:
        return err("密码至少 8 位")
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    mode = register_mode() if count > 0 else "open"
    code = norm_code(data.get("invite"))
    need_invite = mode == "invite" or (mode == "email" and bool(code))   # 邀请链接注册不用邮箱
    email = None
    if need_invite:
        if not code:
            return err("需要邀请码才能注册", 403)
        ok = db.execute("SELECT 1 FROM invites WHERE code = ? AND used_at IS NULL AND expires_at > ?",
                        (code, now_str())).fetchone()
        if ok is None:
            return err("邀请码无效、已用过或已过期")
    elif mode == "email":
        email = norm_email(data.get("email"))
        if not email:
            return err("邮箱格式不对")
        if email_taken(email):
            return err("这个邮箱已经注册过了，可以直接登录或找回密码", 409)
        bad = email_codes.check_code(email, "register", data.get("code"))
        if bad:
            return err(bad)
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), email),
        )
    except sqlite3.IntegrityError:
        db.rollback()
        return err("用户名已存在", 409)
    uid = cur.lastrowid
    if need_invite:
        # 同时有两个人用同一个码时, 只有一个能成功
        used = db.execute("UPDATE invites SET used_by = ?, used_at = ? WHERE code = ? AND used_at IS NULL",
                          (uid, now_str(), code)).rowcount
        if not used:
            db.rollback()
            return err("邀请码无效、已用过或已过期")
    db.commit()
    return login_ok(uid, username)


@bp.route("/api/login", methods=["POST"])
def login():
    data = json_body()
    if data is None:
        return err("请求格式错误")
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    key = username.lower()
    if too_many_fails(key):
        return err("尝试次数过多, 请 10 分钟后再试", 429)
    if "@" in username:     # 用邮箱登录
        row = get_db().execute("SELECT id, username, password_hash FROM users WHERE email = ?",
                               (norm_email(username),)).fetchone()
    else:
        row = get_db().execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        record_fail(key)
        return err("用户名或密码错误", 401)
    return login_ok(row["id"], row["username"])


@bp.route("/api/logout", methods=["POST"])
def logout():
    if session.get("uid") is not None:
        drop_login(session["uid"])
        get_db().commit()
    session.clear()
    return jsonify({"ok": True})


@bp.route("/api/me")
def me():
    uid = current_user_id()
    if uid is None:
        return jsonify({"username": None, "register": register_mode()})
    row = get_db().execute("SELECT username, email FROM users WHERE id = ?", (uid,)).fetchone()
    if row is None:
        session.clear()
        return jsonify({"username": None, "register": register_mode()})
    # register 登录后也要给: 页面是登录状态打开的, 退出后去注册时要用
    return jsonify({"username": row["username"], "admin": is_admin(uid), "email": row["email"],
                    "register": register_mode()})


@bp.route("/api/password", methods=["POST"])
@login_required
def change_password():
    """改自己的密码 {old, new}: 要先输对旧密码"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    uid = current_user_id()
    key = f"#uid{uid}"
    if too_many_fails(key):
        return err("尝试次数过多, 请 10 分钟后再试", 429)
    db = get_db()
    row = db.execute("SELECT password_hash FROM users WHERE id = ?", (uid,)).fetchone()
    if not check_password_hash(row["password_hash"], str(data.get("old", ""))):
        record_fail(key)
        return err("旧密码不对", 401)
    new = str(data.get("new", ""))
    if len(new) < 8:
        return err("新密码至少 8 位")
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), uid))
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/password/forgot", methods=["POST"])
def forgot_password():
    """{email}: 有这个邮箱的账号就发验证码。没有也返回成功, 不让人试出谁注册过"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    email = norm_email(data.get("email"))
    if not email:
        return err("邮箱格式不对")
    if not email_taken(email):
        return jsonify({"ok": True})
    bad = email_codes.send_code(email, "reset")
    return err(bad, 429) if bad else jsonify({"ok": True})


@bp.route("/api/password/reset", methods=["POST"])
def reset_by_email():
    """{email, code, new}: 设置新密码并登录; 其他设备下线(login_ok 换了令牌)"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    email = norm_email(data.get("email"))
    new = str(data.get("new", ""))
    if len(new) < 8:
        return err("新密码至少 8 位")
    db = get_db()
    row = db.execute("SELECT id, username FROM users WHERE email = ?", (email,)).fetchone() if email else None
    if row is None:
        return err("验证码无效或已过期，请重新发送")
    bad = email_codes.check_code(email, "reset", data.get("code"))
    if bad:
        return err(bad)
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), row["id"]))
    db.commit()
    _fail.pop(row["username"].lower(), None)
    return login_ok(row["id"], row["username"])


@bp.route("/api/email/code", methods=["POST"])
@login_required
def bind_email_code():
    """绑定或更换邮箱第一步 {email}: 发验证码到新邮箱"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    email = norm_email(data.get("email"))
    if not email:
        return err("邮箱格式不对")
    if email_taken(email, current_user_id()):
        return err("这个邮箱已经被别的账号用了", 409)
    bad = email_codes.send_code(email, "bind")
    return err(bad, 429) if bad else jsonify({"ok": True})


@bp.route("/api/email", methods=["POST"])
@login_required
def bind_email():
    """{email, code}: 验证码对了就绑定"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    email = norm_email(data.get("email"))
    if not email:
        return err("邮箱格式不对")
    if email_taken(email, current_user_id()):
        return err("这个邮箱已经被别的账号用了", 409)
    bad = email_codes.check_code(email, "bind", data.get("code"))
    if bad:
        return err(bad)
    db = get_db()
    db.execute("UPDATE users SET email = ? WHERE id = ?", (email, current_user_id()))
    db.commit()
    return jsonify({"email": email})


# ---------- 管理员 ----------
@bp.route("/api/invites")
@admin_required
def list_invites():
    """最近 20 个邀请码, status: unused / used / expired"""
    rows = get_db().execute(
        "SELECT i.code, i.created_at, i.expires_at, i.used_at, u.username AS used_by FROM invites i "
        "LEFT JOIN users u ON u.id = i.used_by ORDER BY i.created_at DESC, i.rowid DESC LIMIT 20"
    ).fetchall()
    now = now_str()
    out = []
    for r in rows:
        d = dict(r)
        d["code"] = show_code(r["code"])
        d["status"] = "used" if r["used_at"] else ("unused" if r["expires_at"] > now else "expired")
        out.append(d)
    return jsonify({"invites": out, "days": INVITE_DAYS})


@bp.route("/api/invites", methods=["POST"])
@admin_required
def create_invite():
    db = get_db()
    now = datetime.now(timezone.utc)
    code = random_code(8)
    db.execute("INSERT INTO invites (code, created_by, created_at, expires_at) VALUES (?,?,?,?)",
               (code, current_user_id(), fmt_time(now), fmt_time(now + timedelta(days=INVITE_DAYS))))
    db.commit()
    return jsonify({"code": show_code(code), "expires_at": fmt_time(now + timedelta(days=INVITE_DAYS))})


@bp.route("/api/invites/<code>", methods=["DELETE"])
@admin_required
def delete_invite(code):
    """作废一个还没用过的邀请码(用过的留着记录)"""
    db = get_db()
    n = db.execute("DELETE FROM invites WHERE code = ? AND used_at IS NULL", (norm_code(code),)).rowcount
    db.commit()
    return jsonify({"deleted": n})


@bp.route("/api/admin/users")
@admin_required
def list_users():
    rows = get_db().execute(
        "SELECT u.id, u.username, u.email, (SELECT COUNT(*) FROM progress p WHERE p.user_id = u.id) AS learned, "
        "(SELECT until FROM memberships m WHERE m.user_id = u.id AND m.until > ?) AS member_until "
        "FROM users u ORDER BY u.id", (now_str(),)
    ).fetchall()
    me_id = current_user_id()
    return jsonify({"users": [{**dict(r), "me": r["id"] == me_id} for r in rows]})


@bp.route("/api/admin/users/<int:uid>/reset_password", methods=["POST"])
@admin_required
def reset_password(uid):
    """把别人的密码重置成一个临时密码, 返回给管理员转告; 他登录后自己再改"""
    if uid == current_user_id():
        return err("改自己的密码请用“修改密码”")
    db = get_db()
    row = db.execute("SELECT username FROM users WHERE id = ?", (uid,)).fetchone()
    if row is None:
        return err("用户不存在", 404)
    temp = random_code(10)
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(temp), uid))
    drop_login(uid)   # 他已登录的设备下线
    db.commit()
    _fail.pop(row["username"].lower(), None)   # 他之前输错被限速的话, 一起解开
    return jsonify({"username": row["username"], "password": temp})
