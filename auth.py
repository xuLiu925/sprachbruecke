"""账号: 注册(凭邀请码) / 登录 / 退出 / 当前用户 / 改密码; 管理员: 邀请码、成员列表、重置密码

管理员 = 第一个注册的用户(编号最小)。第一个用户注册不需要邀请码, 之后要管理员发的邀请码;
环境变量 ALLOW_REGISTER=1 时不要邀请码(所有人都能注册)。
"""
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

from database import fmt_time, get_db, now_str
from helpers import current_user_id, err, json_body, login_required

bp = Blueprint("auth", __name__)

# 登录失败限速(内存里, 重启清零): 同一用户名 10 分钟内最多失败 8 次
_fail = {}
FAIL_WINDOW = 600
FAIL_MAX = 8

INVITE_DAYS = 7                                   # 邀请码几天后过期
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"    # 去掉了容易看错的 I L O 0 1


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
    session.clear()
    session["uid"] = uid
    session.permanent = True
    return jsonify({"username": username, "admin": is_admin(uid)})


@bp.route("/api/register", methods=["POST"])
def register():
    data = json_body()
    if data is None:
        return err("请求格式错误")
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not (3 <= len(username) <= 32):
        return err("用户名长度需要 3-32 个字符")
    if len(password) < 8:
        return err("密码至少 8 位")
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    need_invite = count > 0 and os.environ.get("ALLOW_REGISTER", "0") != "1"
    code = norm_code(data.get("invite"))
    if need_invite:
        if not code:
            return err("需要邀请码才能注册", 403)
        ok = db.execute("SELECT 1 FROM invites WHERE code = ? AND used_at IS NULL AND expires_at > ?",
                        (code, now_str())).fetchone()
        if ok is None:
            return err("邀请码无效、已用过或已过期")
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
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
    row = get_db().execute(
        "SELECT id, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        record_fail(key)
        return err("用户名或密码错误", 401)
    return login_ok(row["id"], username)


@bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.route("/api/me")
def me():
    uid = current_user_id()
    if uid is None:
        return jsonify({"username": None})
    row = get_db().execute("SELECT username FROM users WHERE id = ?", (uid,)).fetchone()
    if row is None:
        session.clear()
        return jsonify({"username": None})
    return jsonify({"username": row["username"], "admin": is_admin(uid)})


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
        "SELECT u.id, u.username, (SELECT COUNT(*) FROM progress p WHERE p.user_id = u.id) AS learned "
        "FROM users u ORDER BY u.id"
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
    db.commit()
    _fail.pop(row["username"].lower(), None)   # 他之前输错被限速的话, 一起解开
    return jsonify({"username": row["username"], "password": temp})
