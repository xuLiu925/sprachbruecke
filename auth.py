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
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import email_codes
from content_filter import blocked
from database import DB_PATH, fmt_time, get_db, new_uid, now_str
from email_codes import norm_email
from helpers import client_ip, current_user_id, err, json_body, login_required
from user_profile import display_name, nickname_wait

bp = Blueprint("auth", __name__)

# 登录失败限速(内存里, 重启清零), 10 分钟内:
#   同一用户名 + 同一 IP 最多失败 FAIL_MAX 次  —— 别人在他那边输错, 不会锁住你
#   同一 IP 最多失败 FAIL_IP_MAX 次              —— 挡住换着用户名撞密码
#   同一用户名(所有 IP 加起来)最多 FAIL_NAME_MAX 次 —— 挡住换着 IP 猜一个人的密码
_fail = {}
_fail_lock = threading.Lock()
FAIL_WINDOW = 600
FAIL_MAX = 8
FAIL_IP_MAX = 30
FAIL_NAME_MAX = 100
FAIL_KEYS_MAX = 5000      # 记录的键超过这么多时清掉过期的, 免得被随机用户名撑大内存

INVITE_DAYS = 7                                   # 邀请码几天后过期
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"    # 去掉了容易看错的 I L O 0 1
LOGIN_KEY = "login_token"                         # user_settings 里存当前登录令牌的键
BAN_KEY = "banned"                                # user_settings: 管理员停用了这个账号, 值 = 原因(admin.py)
SEEN_KEY = "last_seen"                            # user_settings: 最近一次用的时间(UTC), 管理后台看活跃
SEEN_EVERY = 600                                  # 同一个人最多每 10 分钟写一次 last_seen, 少写数据库
BAN_MSG = "这个账号已被停用，有疑问请联系管理员"
_seen = {}                                        # uid → 上次写 last_seen 的时间(内存里, 重启清零)
# 不用登录的接口: 会话过期时照常处理, 不返回“已在别的设备登录”
NO_LOGIN_PATHS = {"/api/me", "/api/login", "/api/register", "/api/register/code",
                  "/api/password/forgot", "/api/password/reset"}


def _recent(key, t):
    lst = [x for x in _fail.get(key, []) if t - x < FAIL_WINDOW]
    if lst:
        _fail[key] = lst
    else:
        _fail.pop(key, None)
    return len(lst)


def too_many_fails(name, ip=None, limit=FAIL_MAX):
    """name 是用户名(小写)或 #uid编号 这类键; 带 ip 时另外按 IP、按用户名总数查"""
    t = time.time()
    with _fail_lock:
        if ip is None:
            return _recent(name, t) >= limit
        return (_recent(f"{name}|{ip}", t) >= FAIL_MAX or _recent(f"@ip|{ip}", t) >= FAIL_IP_MAX
                or _recent(name, t) >= FAIL_NAME_MAX)


def record_fail(name, ip=None):
    t = time.time()
    with _fail_lock:
        if len(_fail) > FAIL_KEYS_MAX:
            for k in list(_fail):
                _recent(k, t)
        keys = [name] if ip is None else [name, f"{name}|{ip}", f"@ip|{ip}"]
        for k in keys:
            _fail.setdefault(k, []).append(t)


def clear_fails(name):
    """密码被重置后, 解开这个用户名的限速(各 IP 的也一起)"""
    with _fail_lock:
        for k in [k for k in _fail if k == name or k.startswith(name + "|")]:
            del _fail[k]


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


# 新注册的用户名只能用英文字母、数字、汉字和 _ . -: 不让用空格、零宽字符、长得像英文的外文字母冒充别人。
# 以前注册的用户名不受影响(登录不查这个)
USERNAME_RE = re.compile(r"[A-Za-z0-9_.\-一-鿿]+")


def check_username(username):
    """注册时的用户名: 返回错误信息, 没问题返回 None"""
    if not (3 <= len(username) <= 32):
        return "用户名长度需要 3-32 个字符"
    if "@" in username:
        return "用户名里不能有 @"
    if not USERNAME_RE.fullmatch(username):
        return "用户名只能用英文字母、数字、汉字和 _ . -"
    if blocked(username):
        return "用户名里有不适合的词，换一个吧"
    return None


def username_taken(username):
    """大小写不同也算同一个(Liuxu 和 liuxu), 免得冒充"""
    return get_db().execute("SELECT 1 FROM users WHERE lower(username) = lower(?)", (username,)).fetchone() is not None


def email_taken(email, uid=None):
    row = get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    return row is not None and row["id"] != uid


# 有过管理员的标记文件, 放在数据库文件旁边(vocab.db.admin_lock)。数据库丢了、重新建的空库里,
# 第一个注册的人会成为管理员 —— 有这个文件时空库不让注册, 要先从备份恢复(或者确认后手动删掉这个文件)
ADMIN_LOCK = DB_PATH + ".admin_lock"


def is_admin(uid):
    ok = uid is not None and uid == get_db().execute("SELECT MIN(id) FROM users").fetchone()[0]
    if ok and not os.path.exists(ADMIN_LOCK):
        try:
            with open(ADMIN_LOCK, "w") as f:
                f.write("这个服务器已经有过管理员。数据库是空的时候, 先从备份恢复 vocab.db; 确实要重新开始再删掉这个文件\n")
        except OSError:
            pass
    return ok


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if current_user_id() is None:
            return err("请先登录", 401)
        if not is_admin(current_user_id()):
            return err("只有管理员能做这件事", 403)
        return fn(*a, **kw)

    return wrapper


def banned(uid):
    return get_db().execute("SELECT 1 FROM user_settings WHERE user_id = ? AND key = ?",
                            (uid, BAN_KEY)).fetchone() is not None


def login_ok(uid, username):
    # 被停用的账号: 密码对了也不让登录(先核对密码再说, 不让别人试出哪个账号被停用)
    if banned(uid):
        return err(BAN_MSG, 403)
    start_session(uid)
    return jsonify({"username": username, "admin": is_admin(uid)})


def start_session(uid):
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
    db = get_db()
    vals = dict(db.execute("SELECT key, value FROM user_settings WHERE user_id = ? AND key IN (?, ?)",
                           (uid, LOGIN_KEY, BAN_KEY)).fetchall())
    if BAN_KEY in vals:     # 登录中被停用: 马上下线
        session.clear()
        if request.path.startswith("/api/") and request.path not in NO_LOGIN_PATHS:
            return err(BAN_MSG, 403)
        return None
    if session.get("tok") == vals.get(LOGIN_KEY):
        t = time.time()
        if t - _seen.get(uid, 0) > SEEN_EVERY:
            _seen[uid] = t
            db.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?) "
                       "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value", (uid, SEEN_KEY, now_str()))
            db.commit()
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
    if username_taken(username):
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
    if username_taken(username):
        return err("用户名已存在", 409)
    db = get_db()
    count =db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0 and os.path.exists(ADMIN_LOCK):
        print("!! 数据库里没有用户, 但有过管理员: 拒绝注册, 请先从备份恢复 vocab.db", flush=True)
        return err("服务器正在维护，暂时不能注册", 503)
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
            "INSERT INTO users (username, password_hash, email, uid, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, generate_password_hash(password), email, new_uid(db), now_str()),
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
    key, ip = username.lower(), client_ip()
    if too_many_fails(key, ip):
        return err("尝试次数过多, 请 10 分钟后再试", 429)
    if "@" in username:     # 用邮箱登录
        row = get_db().execute("SELECT id, username, password_hash FROM users WHERE email = ?",
                               (norm_email(username),)).fetchone()
    else:
        row = get_db().execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        record_fail(key, ip)
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
    row = get_db().execute("SELECT username, email, uid, nickname, nickname_at FROM users WHERE id = ?",
                           (uid,)).fetchone()
    if row is None:
        session.clear()
        return jsonify({"username": None, "register": register_mode()})
    # register 登录后也要给: 页面是登录状态打开的, 退出后去注册时要用
    # username = 登录账号(不能改); nickname = 显示的名字; uid = 通德 ID
    return jsonify({"username": row["username"], "admin": is_admin(uid), "email": row["email"],
                    "uid": row["uid"], "nickname": display_name(row),
                    "nickname_wait": nickname_wait(row["nickname_at"]), "register": register_mode()})


@bp.route("/api/password", methods=["POST"])
@login_required
def change_password():
    """改自己的密码 {old, new}: 要先输对旧密码"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    uid = current_user_id()
    key = f"@uid{uid}"   # 用户名里不能有 @, 不会和用户名撞
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
    start_session(uid)   # 换登录令牌: 以前的会话(比如被偷的 cookie)作废, 当前设备换上新令牌继续用
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
    clear_fails(row["username"].lower())
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
    """{email, code, password}: 密码和验证码都对了就绑定。要密码: 别人拿到已登录的手机,
    不能把邮箱换成自己的、再用“忘记密码”把账号拿走。换了邮箱给旧邮箱发一封通知"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    uid = current_user_id()
    email = norm_email(data.get("email"))
    if not email:
        return err("邮箱格式不对")
    key = f"@uid{uid}"   # 和改密码共用限速
    if too_many_fails(key):
        return err("尝试次数过多, 请 10 分钟后再试", 429)
    db = get_db()
    row = db.execute("SELECT password_hash, email FROM users WHERE id = ?", (uid,)).fetchone()
    if not check_password_hash(row["password_hash"], str(data.get("password", ""))):
        record_fail(key)
        return err("登录密码不对", 401)
    if email == row["email"]:
        return err("和现在的邮箱一样")
    if email_taken(email, uid):
        return err("这个邮箱已经被别的账号用了", 409)
    bad = email_codes.check_code(email, "bind", data.get("code"))
    if bad:
        return err(bad)
    db.execute("UPDATE users SET email = ? WHERE id = ?", (email, uid))
    db.commit()
    if row["email"]:
        notify_email_changed(row["email"], email)
    return jsonify({"email": email})


def mask_email(email):
    name, _, domain = email.partition("@")
    return name[:2] + "***@" + domain


def notify_email_changed(old, new):
    """发不出去不影响换邮箱(原因写进日志)"""
    if email_codes.sender is None and not email_codes.configured():
        return
    body = (f"你的通德账号绑定的邮箱已经改成 {mask_email(new)}，以后登录和找回密码都用新邮箱。\n\n"
            "如果不是你本人操作，请尽快在「我的」页意见反馈里联系管理员，或直接回复这封邮件。\n\n通德 Sprachbrücke")
    try:
        email_codes.send_mail(old, "通德账号的邮箱已更换", body)
    except Exception as e:
        print(f"!! 换邮箱通知没发出去: {type(e).__name__}: {e}", flush=True)


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
    clear_fails(row["username"].lower())   # 他之前输错被限速的话, 一起解开
    return jsonify({"username": row["username"], "password": temp})
