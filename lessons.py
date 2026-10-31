"""情景课的后端: 点词查词、把词加入复习。课文本身是静态文件 static/lessons.json

文章里的词可能是变位 / 变格后的样子(ging, Häusern), find_word 用 word_forms 里的形式反查原形。
可分动词(hole ... ab)查不出来, 由课文的 map 字段直接给出原形。
"""
from flask import Blueprint, jsonify, request

from database import get_db, now_str
from helpers import current_user_id, err, json_body, login_required
from vocab import clean_word, query

bp = Blueprint("lessons", __name__)

ADJ_ENDINGS = ("en", "em", "er", "es", "e")
COLS = ("w.id, w.german, w.pos, w.gender, w.plural, w.meaning, w.example, "
        "p.word_id IS NOT NULL AS learned, q.word_id IS NOT NULL AS queued")
JOINS = ("LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid "
         "LEFT JOIN study_queue q ON q.word_id = w.id AND q.user_id = :uid "
         "LEFT JOIN word_levels l ON l.word_id = w.id")


def like_escape(s):
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def find_word(token):
    """词形 → 词库里的词。原形优先, 其次复数, 再次变格 / 变位; 同样匹配时选常用的。没有返回 None"""
    lowered = token[:1].lower() + token[1:]
    for w in dict.fromkeys((token, lowered)):   # 句首大写的 Öffnen 也要能查到 öffnen
        e = like_escape(w)
        row = query(
            f"SELECT {COLS} FROM my_words w {JOINS} "
            "WHERE w.german = :w COLLATE NOCASE OR w.plural = :w COLLATE NOCASE "
            "OR w.forms LIKE :whole ESCAPE '\\' OR w.forms LIKE :tail ESCAPE '\\' "
            "ORDER BY CASE WHEN w.german = :w THEN 0 WHEN w.german = :w COLLATE NOCASE THEN 1 "
            "WHEN w.plural = :w COLLATE NOCASE THEN 2 ELSE 3 END, COALESCE(l.rank, 1000000000) LIMIT 1",
            w=w, whole=f'%"{e}"%', tail=f'% {e}"%',   # "ging" 或 "ist gegangen" / "dem Haus"
        ).fetchone()
        if row:
            return row
    for end in ADJ_ENDINGS:                     # 形容词词尾: schweren → schwer
        if lowered.endswith(end) and len(lowered) > len(end) + 1:
            row = query(
                f"SELECT {COLS} FROM my_words w {JOINS} "
                "WHERE w.german = :w AND w.pos LIKE '形容词%' LIMIT 1",
                w=lowered[:-len(end)],
            ).fetchone()
            if row:
                return row
    return None


@bp.route("/api/lookup")
@login_required
def lookup():
    """?w=词形 → {word: 词 或 null}"""
    w = request.args.get("w", "").strip()
    if not w or len(w) > 60:
        return err("词无效")
    row = find_word(w)
    return jsonify({"word": dict(row) if row else None})


def private_word_id(row):
    """课文里的词: 词库已有就用它(删掉过的恢复), 没有就加成当前用户的私有词"""
    db = get_db()
    uid = current_user_id()
    german, _pos, gender = row[:3]
    found = query("SELECT id FROM all_my_words WHERE german = :g AND gender = :a", g=german, a=gender).fetchone()
    if found:
        db.execute("DELETE FROM user_hidden_words WHERE user_id = ? AND word_id = ?", (uid, found[0]))
        return found[0]
    return db.execute(
        "INSERT INTO words (german, pos, gender, plural, meaning, example, owner_id) VALUES (?,?,?,?,?,?,?)",
        (*row, uid),
    ).lastrowid


@bp.route("/api/review/queue", methods=["POST"])
@login_required
def queue_word():
    """加入复习 {word_id} 或一个词的内容: 下次复习时排在新词最前面。已经学过的不用加"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    if "word_id" in data:
        try:
            word_id = int(data["word_id"])
        except (TypeError, ValueError):
            return err("word_id 无效")
        if query("SELECT 1 FROM my_words WHERE id = :id", id=word_id).fetchone() is None:
            return err("单词不存在", 404)
    else:
        row, e = clean_word(data)
        if e:
            return err(e)
        word_id = private_word_id(row)
    db = get_db()
    uid = current_user_id()
    learned = db.execute("SELECT 1 FROM progress WHERE user_id = ? AND word_id = ?", (uid, word_id)).fetchone()
    if not learned:
        db.execute("INSERT OR IGNORE INTO study_queue (user_id, word_id, added_at) VALUES (?,?,?)",
                   (uid, word_id, now_str()))
    db.commit()
    return jsonify({"word_id": word_id, "learned": bool(learned), "queued": not learned})