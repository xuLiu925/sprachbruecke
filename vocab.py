"""词汇模块: 复习、冠词练习、听写、单词(查看/添加/编辑/删除/恢复)、单词书、统计

词库分两种: 公共词(owner_id 为空, 单词书和示例词) 和 每个用户自己加的私有词(只有他能看到)。
每个用户的「编辑」和「删除」也只对他自己生效, 原文不动:
  编辑 → user_word_edits(存一份他的版本), 删除 → user_hidden_words(对他隐藏, 进度保留), 都能恢复。
所以查词时都从 my_words 取: 公共词 + 自己的私有词, 套上自己的修改, 去掉自己删掉的。SQL 用命名参数 :uid
"""
import json
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from database import fmt_time, get_db, now_str, parse_time
from helpers import current_user_id, err, json_body, login_required
from srs import fsrs_review

bp = Blueprint("vocab", __name__)

NEW_PER_REQUEST = 10      # 每次最多带入多少个新词
REVIEW_LIMIT = 50         # 每次最多返回多少个到期词
MASTERED_STABILITY = 21   # 稳定性 >= 21 天, 且拼写答对过, 才算「已掌握」
GENDERS = {"", "der", "die", "das"}

# 当前用户看到的词库。all_my_words 包括他删掉的(hidden = 1), my_words 不包括
MY_WORDS = """
WITH all_my_words AS (
    SELECT w.id,
           COALESCE(e.german, w.german) AS german, COALESCE(e.pos, w.pos) AS pos,
           COALESCE(e.gender, w.gender) AS gender, COALESCE(e.plural, w.plural) AS plural,
           COALESCE(e.meaning, w.meaning) AS meaning, COALESCE(e.example, w.example) AS example,
           CASE WHEN e.word_id IS NULL THEN f.forms ELSE e.forms END AS forms,
           e.word_id IS NOT NULL AS edited,
           h.word_id IS NOT NULL AS hidden,
           w.owner_id IS NOT NULL AS private
    FROM words w
    LEFT JOIN word_forms f ON f.word_id = w.id
    LEFT JOIN user_word_edits e ON e.word_id = w.id AND e.user_id = :uid
    LEFT JOIN user_hidden_words h ON h.word_id = w.id AND h.user_id = :uid
    WHERE w.owner_id IS NULL OR w.owner_id = :uid
),
my_words AS (SELECT * FROM all_my_words WHERE NOT hidden)
"""


def query(sql, **params):
    """在 MY_WORDS 的基础上查询, 自动带上当前用户"""
    return get_db().execute(MY_WORDS + sql, {"uid": current_user_id(), **params})


# ---------- 单词书 ----------
LEVELS = ["A1", "A2", "B1", "B2", "C1"]
THEME_BOOKS = ["dsh", "common"]   # 专题单词书(word_books 表), 名字在前端 BOOK_NAMES 里
BOOKS = LEVELS + THEME_BOOKS + ["all"]   # all = 整个词库(包括自己加的词)


def current_book(uid):
    row = get_db().execute(
        "SELECT value FROM user_settings WHERE user_id = ? AND key = 'book'", (uid,)
    ).fetchone()
    if row and row["value"] in BOOKS:
        return row["value"]
    # 没选过: 有单词书就从 A1 开始, 否则用整个词库
    has_levels = get_db().execute("SELECT 1 FROM word_levels LIMIT 1").fetchone()
    return "A1" if has_levels else "all"


def book_filter(book):
    """返回 (JOIN 子句, 命名参数, 出新词的顺序)"""
    if book == "all":
        return "LEFT JOIN word_levels l ON l.word_id = w.id", {}, "COALESCE(l.rank, 1000000000), w.id"
    if book in THEME_BOOKS:
        return "JOIN word_books l ON l.word_id = w.id AND l.book = :book", {"book": book}, "l.rank"
    return "JOIN word_levels l ON l.word_id = w.id AND l.level = :book", {"book": book}, "l.rank"


@bp.route("/api/books")
@login_required
def books():
    """各单词书的词数和当前用户的进度"""
    rows = query(
        "SELECT l.level, COUNT(*) AS total, COUNT(p.word_id) AS learned, "
        "SUM(CASE WHEN p.stability >= :ms AND p.spell_ok > 0 THEN 1 ELSE 0 END) AS mastered "
        "FROM my_words w JOIN word_levels l ON l.word_id = w.id "
        "LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid GROUP BY l.level",
        ms=MASTERED_STABILITY,
    ).fetchall()
    by = {r["level"]: dict(r) for r in rows}
    out = [by.get(lv, {"level": lv, "total": 0, "learned": 0, "mastered": 0}) for lv in LEVELS]
    rows = query(
        "SELECT l.book AS level, COUNT(*) AS total, COUNT(p.word_id) AS learned, "
        "SUM(CASE WHEN p.stability >= :ms AND p.spell_ok > 0 THEN 1 ELSE 0 END) AS mastered "
        "FROM my_words w JOIN word_books l ON l.word_id = w.id "
        "LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid GROUP BY l.book",
        ms=MASTERED_STABILITY,
    ).fetchall()
    by = {r["level"]: dict(r) for r in rows}
    themes = [by[b] for b in THEME_BOOKS if b in by]   # 没导入的专题书不显示
    return jsonify({"current": current_book(current_user_id()), "books": out, "themes": themes})


@bp.route("/api/books/current", methods=["POST"])
@login_required
def set_book():
    data = json_body()
    if data is None or data.get("book") not in BOOKS:
        return err("单词书无效")
    get_db().execute(
        "INSERT INTO user_settings (user_id, key, value) VALUES (?, 'book', ?) "
        "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
        (current_user_id(), data["book"]),
    )
    get_db().commit()
    return jsonify({"current": data["book"]})


# ---------- 复习 ----------
WORD_COLS = "w.id, w.german, w.pos, w.gender, w.plural, w.meaning, w.example, w.forms"
# progress 里除了 user_id / word_id 的全部字段: 评分前存进 review_log.prev, 撤销时原样写回
PROGRESS_COLS = ["next_review", "level", "stability", "difficulty", "last_review", "reps", "lapses", "spell_ok"]


def card(row):
    d = dict(row)
    d["forms"] = json.loads(d["forms"]) if d["forms"] else None
    # 题型: 新词先「认词」; 之后拼写和认词轮流, 拼写没答对过的一律考拼写
    if d["is_new"]:
        d["mode"] = "recall"
    else:
        d["mode"] = "spell" if d["spell_ok"] == 0 or d["reps"] % 2 == 1 else "recall"
    return d


@bp.route("/api/review/today")
@login_required
def review_today():
    due = query(
        f"SELECT {WORD_COLS}, p.reps, p.spell_ok, 0 AS is_new "
        "FROM progress p JOIN my_words w ON w.id = p.word_id "
        "WHERE p.user_id = :uid AND p.next_review <= :now ORDER BY p.next_review LIMIT :lim",
        now=now_str(), lim=REVIEW_LIMIT,
    ).fetchall()
    # 新词: 先出用户主动加入的(情景课), 再按单词书补足
    queued = query(
        f"SELECT {WORD_COLS}, 0 AS reps, 0 AS spell_ok, 1 AS is_new "
        "FROM study_queue q JOIN my_words w ON w.id = q.word_id "
        "WHERE q.user_id = :uid AND w.id NOT IN (SELECT word_id FROM progress WHERE user_id = :uid) "
        "ORDER BY q.added_at, w.id LIMIT :lim",
        lim=NEW_PER_REQUEST,
    ).fetchall()
    book_join, book_args, order = book_filter(current_book(current_user_id()))
    new = query(
        f"SELECT {WORD_COLS}, 0 AS reps, 0 AS spell_ok, 1 AS is_new FROM my_words w {book_join} "
        "WHERE w.id NOT IN (SELECT word_id FROM progress WHERE user_id = :uid) "
        f"AND w.id NOT IN (SELECT word_id FROM study_queue WHERE user_id = :uid) ORDER BY {order} LIMIT :lim",
        lim=NEW_PER_REQUEST - len(queued), **book_args,
    ).fetchall()
    new = list(queued) + list(new)
    cards = [card(r) for r in due] + [card(r) for r in new]
    return jsonify({"cards": cards, "due": len(due), "new": len(new)})


@bp.route("/api/review/answer", methods=["POST"])
@login_required
def review_answer():
    data = json_body()
    if data is None:
        return err("请求格式错误")
    try:
        word_id = int(data.get("word_id"))
    except (TypeError, ValueError):
        return err("word_id 无效")
    rating = data.get("rating")
    if rating is None and "correct" in data:  # 兼容旧版前端
        rating = 3 if data.get("correct") else 1
    if isinstance(rating, bool) or rating not in (1, 2, 3, 4):
        return err("rating 只能是 1-4")
    mode = data.get("mode", "recall")
    if mode not in ("recall", "spell"):
        return err("mode 无效")
    uid = current_user_id()
    db = get_db()
    if word_row(word_id) is None:
        return err("单词不存在", 404)
    row = db.execute(
        f"SELECT {', '.join(PROGRESS_COLS)} FROM progress WHERE user_id = ? AND word_id = ?", (uid, word_id)
    ).fetchone()
    now = datetime.now(timezone.utc)
    if row is None or row["stability"] is None:
        s, d, days = fsrs_review(None, None, None, rating, now)
        reps = lapses = spell_ok = 0
    else:
        s, d, days = fsrs_review(row["stability"], row["difficulty"],
                                 parse_time(row["last_review"]), rating, now)
        reps, lapses, spell_ok = row["reps"], row["lapses"], row["spell_ok"]
        lapses += rating == 1
    reps += 1
    spell_ok += mode == "spell" and rating > 1
    nxt = fmt_time(now + timedelta(days=days))
    db.execute(
        "INSERT INTO progress (user_id, word_id, next_review, stability, difficulty, "
        "last_review, reps, lapses, spell_ok) VALUES (?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(user_id, word_id) DO UPDATE SET next_review = excluded.next_review, "
        "stability = excluded.stability, difficulty = excluded.difficulty, "
        "last_review = excluded.last_review, reps = excluded.reps, "
        "lapses = excluded.lapses, spell_ok = excluded.spell_ok",
        (uid, word_id, nxt, s, d, fmt_time(now), reps, lapses, spell_ok),
    )
    log_id = db.execute(
        "INSERT INTO review_log (user_id, word_id, rating, mode, reviewed_at, prev) VALUES (?,?,?,?,?,?)",
        (uid, word_id, rating, mode, fmt_time(now), json.dumps(dict(row)) if row else None),
    ).lastrowid
    db.commit()
    return jsonify({
        "next_review": nxt, "interval_days": days,
        "stability": round(s, 2), "difficulty": round(d, 2),
        "mastered": s >= MASTERED_STABILITY and spell_ok > 0,
        "log_id": log_id,
    })


@bp.route("/api/review/undo", methods=["POST"])
@login_required
def review_undo():
    """撤销一次评分 {log_id}: 进度恢复成评分前的样子。只能撤销这个词最近的一次评分"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    uid = current_user_id()
    db = get_db()
    log = db.execute("SELECT * FROM review_log WHERE id = ? AND user_id = ?",
                     (data.get("log_id"), uid)).fetchone()
    if log is None:
        return err("找不到这次评分", 404)
    latest = db.execute("SELECT MAX(id) FROM review_log WHERE user_id = ? AND word_id = ?",
                        (uid, log["word_id"])).fetchone()[0]
    if latest != log["id"]:
        return err("这个词后来又复习过，不能撤销这一次")
    if log["prev"] is None:
        db.execute("DELETE FROM progress WHERE user_id = ? AND word_id = ?", (uid, log["word_id"]))
    else:
        prev = json.loads(log["prev"])
        db.execute(
            f"UPDATE progress SET {', '.join(c + ' = ?' for c in PROGRESS_COLS)} WHERE user_id = ? AND word_id = ?",
            [prev[c] for c in PROGRESS_COLS] + [uid, log["word_id"]],
        )
    db.execute("DELETE FROM review_log WHERE id = ?", (log["id"],))
    db.commit()
    return jsonify({"word_id": log["word_id"]})


@bp.route("/api/drill/articles")
@login_required
def drill_articles():
    """冠词练习题: 优先用学过的名词, 太少时从整个词库里随机抽。只是练习, 不影响复习计划"""
    q = ("SELECT w.id, w.german, w.gender, w.plural, w.meaning, w.example FROM my_words w {} "
         "WHERE w.gender != '' ORDER BY RANDOM() LIMIT 20")
    rows = query(q.format("JOIN progress p ON p.word_id = w.id AND p.user_id = :uid")).fetchall()
    if len(rows) < 5:
        rows = query(q.format("")).fetchall()
    return jsonify({"words": [dict(r) for r in rows]})


@bp.route("/api/drill/dictation")
@login_required
def drill_dictation():
    """听写题: 学过的词里随机 20 个; 学过的不到 5 个时, 用当前单词书里最常用的 20 个。只是练习, 不影响复习计划"""
    cols = "w.id, w.german, w.gender, w.pos, w.meaning, w.example"
    rows = query(
        f"SELECT {cols} FROM my_words w JOIN progress p ON p.word_id = w.id AND p.user_id = :uid "
        "ORDER BY RANDOM() LIMIT 20",
    ).fetchall()
    if len(rows) < 5:
        book_join, book_args, order = book_filter(current_book(current_user_id()))
        rows = query(f"SELECT {cols} FROM my_words w {book_join} ORDER BY {order} LIMIT 20", **book_args).fetchall()
    return jsonify({"words": [dict(r) for r in rows]})


# ---------- 单词 ----------
def clean_word(d):
    if not isinstance(d, dict):
        return None, "格式错误"
    german = str(d.get("german", "")).strip()
    meaning = str(d.get("meaning", "")).strip()
    gender = str(d.get("gender", "")).strip().lower()
    if not german or not meaning:
        return None, "德语词和释义不能为空"
    if gender not in GENDERS:
        return None, "性别只能是 der / die / das 或留空"
    if len(german) > 100 or len(meaning) > 300:
        return None, "内容太长"
    return (
        german,
        str(d.get("pos", "")).strip()[:20],
        gender,
        str(d.get("plural", "")).strip()[:100],
        meaning,
        str(d.get("example", "")).strip()[:300],
    ), None


def str_list(v, n):
    """n 个字符串组成的列表, 每个最长 60 字符; 不合格返回 None"""
    if not isinstance(v, list) or len(v) != n:
        return None
    out = [str(x).strip() if isinstance(x, (str, int, float)) else None for x in v]
    if any(x is None or len(x) > 60 for x in out):
        return None
    return out


def clean_forms(f):
    """返回 (JSON 字符串或 None, 错误信息或 None)"""
    if f is None or f == {}:
        return None, None
    if not isinstance(f, dict) or not set(f) <= {"cases", "praesens", "past"}:
        return None, "变化形式格式错误"
    out = {}
    if "cases" in f:
        c = f["cases"]
        if not isinstance(c, dict):
            return None, "变格格式错误"
        sg = str_list(c.get("sg"), 4)
        pl = str_list(c.get("pl", [""] * 4), 4)
        if sg is None or pl is None:
            return None, "变格格式错误"
        if not all(sg):
            return None, "单数的四个格要填全"
        if any(pl) and not all(pl):
            return None, "复数的四个格要么填全, 要么全空"
        out["cases"] = {"sg": sg, "pl": pl}
    if "praesens" in f:
        p = str_list(f["praesens"], 6)
        if p is None:
            return None, "变位格式错误"
        if not all(p):
            return None, "六个人称的变位要填全"
        out["praesens"] = p
    if "past" in f:   # [过去式, 完成时], 如 ["fuhr", "ist gefahren"]
        p = str_list(f["past"], 2)
        if p is None or not all(p):
            return None, "过去式 / 完成时格式错误"
        out["past"] = p
    if not out:
        return None, None
    return json.dumps(out, ensure_ascii=False), None


def word_status(d):
    """new 未学 / learning 学习中 / mastered 已掌握"""
    if d["reps"] is None:
        return "new"
    if d["stability"] >= MASTERED_STABILITY and d["spell_ok"] > 0:
        return "mastered"
    return "learning"


@bp.route("/api/words")
@login_required
def list_words():
    """词库列表(带当前用户的学习状态), ?q= 按德语或释义搜索, ?level= A1..C1 / mine(自己加的) / hidden(删掉的), 最多 200 条"""
    q = request.args.get("q", "").strip()[:50]
    level = request.args.get("level", "")
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    source = "my_words"
    where = "(w.german LIKE :like ESCAPE '\\' OR w.meaning LIKE :like ESCAPE '\\')"
    args = {"like": like}
    theme_join = ""
    order = "w.german COLLATE NOCASE"
    if level in LEVELS:
        where += " AND l.level = :level"
        args["level"] = level
        order = "l.rank"
    elif level in THEME_BOOKS:
        theme_join = "JOIN word_books b ON b.word_id = w.id AND b.book = :level"
        args["level"] = level
        order = "b.rank"
    elif level == "mine":     # 自己加的私有词
        where += " AND w.private"
    elif level == "hidden":   # 自己删掉的词(可以恢复)
        source = "all_my_words"
        where += " AND w.hidden"
    rows = query(
        "SELECT w.id, w.german, w.gender, w.pos, w.plural, w.meaning, w.edited, w.hidden, w.private, l.level, "
        "p.next_review, p.stability, p.spell_ok, p.reps "
        f"FROM {source} w {theme_join} LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid "
        f"LEFT JOIN word_levels l ON l.word_id = w.id WHERE {where} ORDER BY {order} LIMIT 200",
        **args,
    ).fetchall()
    words = []
    for r in rows:
        d = dict(r)
        d["status"] = word_status(d)
        d["edited"], d["hidden"], d["private"] = bool(d["edited"]), bool(d["hidden"]), bool(d["private"])
        for k in ("stability", "spell_ok", "reps"):
            del d[k]
        words.append(d)
    return jsonify({"words": words})


def word_row(word_id):
    """当前用户看到的一个词(包括他删掉的), 没有返回 None"""
    return query("SELECT * FROM all_my_words WHERE id = :id", id=word_id).fetchone()


@bp.route("/api/words/<int:word_id>")
@login_required
def get_word(word_id):
    """一个词的全部内容(当前用户的版本), 加上他的学习情况; 改过的话附上原文 original"""
    row = query(
        "SELECT w.*, l.level, p.next_review, p.stability, p.spell_ok, p.reps, p.lapses "
        "FROM all_my_words w LEFT JOIN word_levels l ON l.word_id = w.id "
        "LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid WHERE w.id = :id",
        id=word_id,
    ).fetchone()
    if row is None:
        return err("单词不存在", 404)
    d = dict(row)
    d["forms"] = json.loads(d["forms"]) if d["forms"] else None
    db = get_db()
    details = db.execute("SELECT details FROM word_details WHERE word_id = ?", (word_id,)).fetchone()
    d["details"] = json.loads(details[0]) if details else None
    d["books"] = [r[0] for r in db.execute("SELECT book FROM word_books WHERE word_id = ?", (word_id,))]
    d["status"] = word_status(d)
    d["stability"] = round(d["stability"], 1) if d["stability"] is not None else None
    d["edited"], d["hidden"], d["private"] = bool(d["edited"]), bool(d["hidden"]), bool(d["private"])
    d["original"] = None
    if d["edited"]:
        o = get_db().execute(
            "SELECT w.german, w.pos, w.gender, w.plural, w.meaning, w.example, f.forms "
            "FROM words w LEFT JOIN word_forms f ON f.word_id = w.id WHERE w.id = ?", (word_id,),
        ).fetchone()
        d["original"] = {**dict(o), "forms": json.loads(o["forms"]) if o["forms"] else None}
    return jsonify(d)


@bp.route("/api/words/<int:word_id>", methods=["PUT"])
@login_required
def edit_word(word_id):
    """改一个词 —— 只改当前用户自己的版本, 词库原文不动。
    带 forms 字段就一起改变格/变位(null 或 {} 表示删掉), 不带就保留现在的。改得和原文一样就等于恢复。"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    row, e = clean_word(data)
    if e:
        return err(e)
    cur = word_row(word_id)
    if cur is None:
        return err("单词不存在", 404)
    if "forms" in data:
        forms, e = clean_forms(data["forms"])
        if e:
            return err(e)
    else:
        forms = cur["forms"]
    db = get_db()
    uid = current_user_id()
    orig = db.execute(
        "SELECT w.german, w.pos, w.gender, w.plural, w.meaning, w.example, f.forms "
        "FROM words w LEFT JOIN word_forms f ON f.word_id = w.id WHERE w.id = ?", (word_id,),
    ).fetchone()
    load = lambda f: json.loads(f) if f else None   # noqa: E731
    if tuple(orig)[:6] == row and load(orig["forms"]) == load(forms):
        db.execute("DELETE FROM user_word_edits WHERE user_id = ? AND word_id = ?", (uid, word_id))
    else:
        db.execute(
            "INSERT INTO user_word_edits (user_id, word_id, german, pos, gender, plural, meaning, example, "
            "forms, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id, word_id) DO UPDATE SET "
            "german = excluded.german, pos = excluded.pos, gender = excluded.gender, plural = excluded.plural, "
            "meaning = excluded.meaning, example = excluded.example, forms = excluded.forms, "
            "updated_at = excluded.updated_at",
            (uid, word_id, *row, forms, now_str()),
        )
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/words/<int:word_id>/revert", methods=["POST"])
@login_required
def revert_word(word_id):
    """恢复原来的内容(去掉当前用户的修改)"""
    db = get_db()
    db.execute("DELETE FROM user_word_edits WHERE user_id = ? AND word_id = ?", (current_user_id(), word_id))
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/words/<int:word_id>", methods=["DELETE"])
@login_required
def delete_word(word_id):
    """「删除」一个词 —— 只对当前用户隐藏, 复习进度保留, 可以恢复。别的用户不受影响"""
    db = get_db()
    if word_row(word_id) is None:
        return err("单词不存在", 404)
    db.execute("INSERT OR IGNORE INTO user_hidden_words (user_id, word_id, hidden_at) VALUES (?, ?, ?)",
               (current_user_id(), word_id, now_str()))
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/words/<int:word_id>/unhide", methods=["POST"])
@login_required
def unhide_word(word_id):
    """恢复删掉的词(复习进度还在)"""
    db = get_db()
    db.execute("DELETE FROM user_hidden_words WHERE user_id = ? AND word_id = ?", (current_user_id(), word_id))
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/words", methods=["POST"])
@login_required
def add_words():
    """添加单词 —— 加成当前用户的私有词, 别人看不到。
    公共词库里已经有(德语 + 冠词相同)就不重复加; 如果是他删掉过的, 这次添加 = 恢复"""
    data = request.get_json(silent=True)
    items = data if isinstance(data, list) else ([data] if isinstance(data, dict) else None)
    if items is None or len(items) == 0:
        return err("请求格式错误")
    if len(items) > 2000:
        return err("一次最多导入 2000 个")
    db = get_db()
    uid = current_user_id()
    added = skipped = 0
    for d in items:
        row, e = clean_word(d)
        if e:
            return err(e)
        forms, e = clean_forms(d.get("forms"))
        if e:
            return err(f"{row[0]}: {e}")
        public = db.execute("SELECT id FROM words WHERE german = ? AND gender = ? AND owner_id IS NULL",
                            (row[0], row[2])).fetchone()
        if public:
            cur = db.execute("DELETE FROM user_hidden_words WHERE user_id = ? AND word_id = ?", (uid, public[0]))
            added += cur.rowcount     # 删掉过的 → 恢复, 算加上了
            skipped += 1 - cur.rowcount
            continue
        cur = db.execute(
            "INSERT OR IGNORE INTO words (german, pos, gender, plural, meaning, example, owner_id) "
            "VALUES (?,?,?,?,?,?,?)",
            (*row, uid),
        )
        if cur.rowcount:
            added += 1
            if forms:
                db.execute("INSERT INTO word_forms (word_id, forms) VALUES (?, ?)",
                           (cur.lastrowid, forms))
        else:   # 自己已经加过: 删掉过的就恢复
            own = db.execute("SELECT id FROM words WHERE german = ? AND gender = ? AND owner_id = ?",
                             (row[0], row[2], uid)).fetchone()
            cur = db.execute("DELETE FROM user_hidden_words WHERE user_id = ? AND word_id = ?", (uid, own[0]))
            added += cur.rowcount
            skipped += 1 - cur.rowcount
    db.commit()
    return jsonify({"added": added, "skipped": skipped})


# ---------- 统计 ----------
@bp.route("/api/stats")
@login_required
def stats():
    uid = current_user_id()
    total = query("SELECT COUNT(*) FROM my_words").fetchone()[0]
    learned, due, mastered = query(
        "SELECT COUNT(*), "
        "COALESCE(SUM(p.next_review <= :now), 0), "
        "COALESCE(SUM(p.stability >= :ms AND p.spell_ok > 0), 0) "
        "FROM progress p JOIN my_words w ON w.id = p.word_id WHERE p.user_id = :uid",
        now=now_str(), ms=MASTERED_STABILITY,
    ).fetchone()
    book = current_book(uid)
    book_join, book_args, _ = book_filter(book)
    book_total, book_learned, book_mastered = query(
        f"SELECT COUNT(*), COUNT(p.word_id), COALESCE(SUM(p.stability >= :ms AND p.spell_ok > 0), 0) "
        f"FROM my_words w {book_join} "
        "LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid", ms=MASTERED_STABILITY, **book_args,
    ).fetchone()
    queued = query(
        "SELECT COUNT(*) FROM study_queue q JOIN my_words w ON w.id = q.word_id WHERE q.user_id = :uid "
        "AND w.id NOT IN (SELECT word_id FROM progress WHERE user_id = :uid)",
    ).fetchone()[0]
    return jsonify({"total": total, "learned": learned, "due": due, "mastered": mastered,
                    "book": book, "book_total": book_total, "book_learned": book_learned,
                    "book_mastered": book_mastered, "queued": queued})
