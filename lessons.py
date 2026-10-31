"""情景课的后端: 点词查词、把词加入复习、角色扮演和整句复习。课文本身是静态文件 static/lessons.json

文章里的词可能是变位 / 变格后的样子(ging, Häusern), find_word 用 word_forms 里的形式反查原形。
可分动词(hole ... ab)查不出来, 由课文的 map 字段直接给出原形。

角色扮演: 用户固定扮演 Li。课文里「别人说一句 → Li 接一句」的地方就是一道题,
听对方的话, 自己开口回答, 再和参考回答对照、自评。评过的题用 FSRS 安排复习。
"""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from database import BASE, fmt_time, get_db, now_str, parse_time
from helpers import current_user_id, err, json_body, login_required
from srs import fsrs_review
from vocab import clean_word, query

bp = Blueprint("lessons", __name__)

LESSONS_FILE = os.path.join(BASE, "static", "lessons.json")
ROLE = "Li"             # 用户扮演的角色
DUE_LIMIT = 30          # 整句复习一次最多多少句
_items = {"mtime": None, "by_key": {}, "by_lesson": {}}

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


def roleplay_items(lesson):
    """一课的角色扮演题: 对方说一句, 紧接着 Li 回答"""
    out = []
    for before, line in zip(lesson["lines"], lesson["lines"][1:]):
        if line["who"] != ROLE or before["who"] == ROLE:
            continue
        key = hashlib.sha1(f"{before['de']}|{line['de']}".encode("utf-8")).hexdigest()[:16]
        out.append({"key": key, "lesson": lesson["id"], "level": lesson["level"], "title": lesson["title"],
                    "who": before["who"], "prompt": before["de"], "prompt_zh": before["zh"],
                    "answer": line["de"], "answer_zh": line["zh"]})
    return out


def load_items():
    """课文文件变了才重新读"""
    mtime = os.path.getmtime(LESSONS_FILE)
    if _items["mtime"] != mtime:
        with open(LESSONS_FILE, encoding="utf-8") as f:
            lessons = json.load(f)["lessons"]
        by_lesson = {x["id"]: roleplay_items(x) for x in lessons}
        _items.update(mtime=mtime, by_lesson=by_lesson,
                      by_key={i["key"]: i for items in by_lesson.values() for i in items})
    return _items


def as_lesson(row):
    """custom_lessons 的一行 → 和 lessons.json 里一样的结构, 编号是 u + 数字, 不会和自带课程重复"""
    return {**json.loads(row["data"]), "id": f"u{row['id']}", "level": row["level"], "title": row["title"],
            "scene": row["scene"], "custom": True}


def my_lessons():
    rows = get_db().execute("SELECT * FROM custom_lessons WHERE user_id = ? ORDER BY id DESC",
                            (current_user_id(),)).fetchall()
    return [as_lesson(r) for r in rows]


def my_items():
    """自带课程 + 当前用户自建课程的全部题目 → (按 key, 按课程)"""
    base = load_items()
    custom = {x["id"]: roleplay_items(x) for x in my_lessons()}
    by_key = {**base["by_key"], **{i["key"]: i for items in custom.values() for i in items}}
    return by_key, {**base["by_lesson"], **custom}


@bp.route("/api/roleplay/lesson/<lesson_id>")
@login_required
def roleplay_lesson(lesson_id):
    items = my_items()[1].get(lesson_id)
    if items is None:
        return err("课程不存在", 404)
    return jsonify({"items": items})


@bp.route("/api/roleplay/due")
@login_required
def roleplay_due():
    """到期要复习的句子。count 是到期总数, items 最多 DUE_LIMIT 句; 课文改掉的旧句子跳过"""
    rows = get_db().execute(
        "SELECT item_key FROM sentence_progress WHERE user_id = ? AND next_review <= ? ORDER BY next_review",
        (current_user_id(), now_str()),
    ).fetchall()
    by_key = my_items()[0]
    due = [by_key[r["item_key"]] for r in rows if r["item_key"] in by_key]
    return jsonify({"count": len(due), "items": due[:DUE_LIMIT]})


@bp.route("/api/roleplay/answer", methods=["POST"])
@login_required
def roleplay_answer():
    """评分 {key, rating}: 1 没说出来 / 2 说得磕绊 / 3 说出来了。第一次评分时这句进入复习"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    key, rating = data.get("key"), data.get("rating")
    if not isinstance(key, str) or key not in my_items()[0]:
        return err("句子不存在", 404)
    if isinstance(rating, bool) or rating not in (1, 2, 3):
        return err("rating 只能是 1-3")
    db = get_db()
    uid = current_user_id()
    row = db.execute("SELECT * FROM sentence_progress WHERE user_id = ? AND item_key = ?", (uid, key)).fetchone()
    now = datetime.now(timezone.utc)
    if row is None:
        s, d, days = fsrs_review(None, None, None, rating, now)
        reps, lapses = 0, 0
    else:
        s, d, days = fsrs_review(row["stability"], row["difficulty"], parse_time(row["last_review"]), rating, now)
        reps, lapses = row["reps"], row["lapses"] + (rating == 1)
    nxt = fmt_time(now + timedelta(days=days))
    db.execute(
        "INSERT INTO sentence_progress (user_id, item_key, next_review, stability, difficulty, last_review, "
        "reps, lapses) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id, item_key) DO UPDATE SET "
        "next_review = excluded.next_review, stability = excluded.stability, difficulty = excluded.difficulty, "
        "last_review = excluded.last_review, reps = excluded.reps, lapses = excluded.lapses",
        (uid, key, nxt, s, d, fmt_time(now), reps + 1, lapses),
    )
    db.commit()
    return jsonify({"interval_days": days, "next_review": nxt})


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