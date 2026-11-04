"""功能引导(Blueprint, 文档 docs/features/guide.md): 记下每个用户看过哪些引导, 换设备也不重复弹

- GET  /api/guide          {seen: [...], showcase}: 看过的引导(tour = 第一次登录的导览, 其他是用到时的小提示);
                           showcase = 导览里打开的示范词 {id, german, de}(de = 它的例句, 打开讲解不算 AI 次数)
- POST /api/guide {key}    记一个看过的
存在 user_settings 的 guide_seen(JSON 列表)。引导的内容和出现的时机都在前端 static/js/guide.js
"""
import json
import re

from flask import Blueprint, jsonify

from database import get_db
from helpers import current_user_id, err, json_body, login_required

bp = Blueprint("guide", __name__)

KEY = "guide_seen"
# 导览里展示的示范词: 没有词性规律(才会显示 AI 联想记忆)、构词清楚、例句讲解内容多。
# 它的构词、联想记忆、例句讲解要提前在服务器上生成好并人工检查过; 换词时这几样也要一起准备
SHOWCASE = ("Anruf", "der")
KEY_RE = re.compile(r"[a-z_]{1,30}")
MAX_KEYS = 50


def seen(uid):
    row = get_db().execute("SELECT value FROM user_settings WHERE user_id = ? AND key = ?", (uid, KEY)).fetchone()
    try:
        out = json.loads(row["value"]) if row else []
    except ValueError:
        out = []
    return [k for k in out if isinstance(k, str)] if isinstance(out, list) else []


def showcase():
    row = get_db().execute("SELECT id, german, example FROM words WHERE german = ? AND gender = ? AND status = 'public' "
                           "ORDER BY id LIMIT 1", SHOWCASE).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "german": row["german"], "de": (row["example"] or "").split(chr(10))[0].strip()}


def is_showcase_sentence(de):
    s = showcase()
    return bool(s and s["de"] and s["de"] == de)


@bp.route("/api/guide")
@login_required
def get_guide():
    return jsonify({"seen": seen(current_user_id()), "showcase": showcase()})


@bp.route("/api/guide", methods=["POST"])
@login_required
def mark_seen():
    data = json_body()
    key = str((data or {}).get("key", ""))
    if not KEY_RE.fullmatch(key):
        return err("参数无效")
    uid = current_user_id()
    keys = seen(uid)
    if key not in keys and len(keys) < MAX_KEYS:
        keys.append(key)
        db = get_db()
        db.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?) "
                   "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value", (uid, KEY, json.dumps(keys)))
        db.commit()
    return jsonify({"seen": keys})
