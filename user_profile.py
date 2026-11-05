"""个人资料: 昵称和通德 ID(文档 docs/features/profile.md)

- 通德 ID(users.uid): 注册时随机生成的 8 位数字, 不变, 联系客服、管理员找人时用(database.new_uid)
- 昵称(users.nickname): 显示用的名字, 空 = 用用户名。可以重名(有 ID 区分); NICK_DAYS 天能改一次。
  登录还是用用户名或邮箱, 用户名不能改
- POST /api/profile/nickname {nickname}
"""
import re
from datetime import timedelta

from flask import Blueprint, jsonify

from content_filter import blocked
from database import fmt_time, get_db, now_str, parse_time
from helpers import current_user_id, err, json_body, login_required

bp = Blueprint("profile", __name__)

NICK_DAYS = 30
NICK_MIN, NICK_MAX = 2, 16
NICK_RE = re.compile(r"[A-Za-z0-9_.\-一-鿿]+")     # 和新用户名一样: 不让用空格、零宽字符冒充别人
# 防止冒充管理员、官方(小写比较)
RESERVED = ("管理员", "管理", "官方", "客服", "通德", "系统", "admin", "tongde", "sprachbr", "system", "support")


def display_name(row):
    return row["nickname"] or row["username"]


def nickname_wait(nickname_at):
    """还要等几天才能再改昵称; 0 = 现在就能改"""
    if not nickname_at:
        return 0
    left = parse_time(nickname_at) + timedelta(days=NICK_DAYS) - parse_time(now_str())
    return max(0, -(-int(left.total_seconds()) // 86400))    # 不满一天按一天


def check_nickname(nick):
    if not (NICK_MIN <= len(nick) <= NICK_MAX):
        return f"昵称需要 {NICK_MIN}-{NICK_MAX} 个字"
    if not NICK_RE.fullmatch(nick):
        return "昵称只能用汉字、英文字母、数字和 _ . -"
    low = nick.lower()
    if any(w in low for w in RESERVED):
        return "昵称里不能有“管理员、官方、客服、通德”这类词"
    if blocked(nick):
        return "昵称里有不适合的词，换一个吧"
    return None


@bp.route("/api/profile/nickname", methods=["POST"])
@login_required
def set_nickname():
    data = json_body()
    if data is None:
        return err("请求格式错误")
    nick = str(data.get("nickname", "")).strip()
    bad = check_nickname(nick)
    if bad:
        return err(bad)
    db = get_db()
    uid = current_user_id()
    row = db.execute("SELECT username, nickname, nickname_at FROM users WHERE id = ?", (uid,)).fetchone()
    if nick == display_name(row):
        return err("和现在的昵称一样")
    wait = nickname_wait(row["nickname_at"])
    if wait:
        return err(f"昵称 {NICK_DAYS} 天只能改一次，还要等 {wait} 天", 429)
    now = now_str()
    db.execute("UPDATE users SET nickname = ?, nickname_at = ? WHERE id = ?", (nick, now, uid))
    db.commit()
    return jsonify({"nickname": nick, "nickname_wait": NICK_DAYS,
                    "next": fmt_time(parse_time(now) + timedelta(days=NICK_DAYS))})
