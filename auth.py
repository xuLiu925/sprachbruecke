"""账号: 注册 / 登录 / 退出 / 当前用户"""
import os
import sqlite3
import time

from flask import Blueprint, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db
from helpers import current_user_id, err, json_body

bp = Blueprint("auth", __name__)

# 登录失败限速(内存里, 重启清零): 同一用户名 10 分钟内最多失败 8 次
_fail = {}
FAIL_WINDOW = 600
FAIL_MAX = 8


def too_many_fails(name):
    t = time.time()
    lst = [x for x in _fail.get(name, []) if t - x < FAIL_WINDOW]
    _fail[name] = lst
    return len(lst) >= FAIL_MAX


def record_fail(name):
    _fail.setdefault(name, []).append(time.time())


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
    if count > 0 and os.environ.get("ALLOW_REGISTER", "0") != "1":
        return err("目前不开放注册", 403)
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return err("用户名已存在", 409)
    session.clear()
    session["uid"] = cur.lastrowid
    session.permanent = True
    return jsonify({"username": username})


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
    session.clear()
    session["uid"] = row["id"]
    session.permanent = True
    return jsonify({"username": username})


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
    return jsonify({"username": row["username"]})
