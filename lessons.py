"""情景课的后端: 课文、点词查词、把词加入复习、角色扮演和整句复习。
课文在 content/lessons.json, 不放 static/: 列表只给标题和词表, 课文要走 /api/lessons/<id>, 免费次数在 billing.py 里查

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
from vocab import clean_word, enqueue, query
from word_store import word_id_for
import lexicon

bp = Blueprint("lessons", __name__)

LESSONS_FILE = os.path.join(BASE, "content", "lessons.json")
ROLE = "Li"             # 用户扮演的角色
DUE_LIMIT = 30          # 整句复习一次最多多少句
LIST_FIELDS = ("id", "level", "title", "scene", "glossary")   # 课程列表给的字段(词表单词卡要用)
_items = {"mtime": None, "lessons": {}, "by_key": {}, "by_lesson": {}, "glossary": []}

ADJ_ENDINGS = ("en", "em", "er", "es", "e")
COLS = ("w.id, w.german, w.pos, w.gender, w.plural, w.meaning, w.example, "
        "p.word_id IS NOT NULL AS learned, q.word_id IS NOT NULL AS queued")
JOINS = ("LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid "
         "LEFT JOIN study_queue q ON q.word_id = w.id AND q.user_id = :uid "
         "LEFT JOIN word_levels l ON l.word_id = w.id")


def like_escape(s):
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def find_word(token):
    """词形 → 词库里的词。原形优先, 其次复数, 再次变格 / 变位, 再查词典的变化形式; 同样匹配时选常用的。没有返回 None"""
    row = find_in_words(token)
    if row:
        return row
    rows = lexicon_rows(lexicon.lemmas_of(token))
    return rows[0] if rows else None


def exact_match(row, w):
    """区分大小写地对得上: 文中的 gefahren 是 fahren 的分词, 不是 Gefahr 的复数 Gefahren"""
    f = row["forms"] or ""
    return w in (row["german"], row["plural"]) or f'"{w}"' in f or f' {w}"' in f


def find_in_words(token, strict=False):
    """只按词库自己的数据(原形、复数、变格 / 变位表、形容词词尾)找。
    strict = 区分大小写(点词: 文中的大小写是准的); 查词搜索框里用户可能写 haus, 不区分"""
    lowered = token[:1].lower() + token[1:]
    for w in dict.fromkeys((token, lowered)):   # 句首大写的 Öffnen 也要能查到 öffnen
        e = like_escape(w)
        rows = query(
            f"SELECT {COLS}, w.forms FROM my_words w {JOINS} "
            "WHERE w.german = :w COLLATE NOCASE OR w.plural = :w COLLATE NOCASE "
            "OR w.forms LIKE :whole ESCAPE '\\' OR w.forms LIKE :tail ESCAPE '\\' "
            "ORDER BY CASE WHEN w.german = :w THEN 0 WHEN w.german = :w COLLATE NOCASE THEN 1 "
            "WHEN w.plural = :w COLLATE NOCASE THEN 2 ELSE 3 END, COALESCE(l.rank, 1000000000) LIMIT 30",
            w=w, whole=f'%"{e}"%', tail=f'% {e}"%',   # "ging" 或 "ist gegangen" / "dem Haus"
        ).fetchall()
        row = next((r for r in rows if exact_match(r, w)), None) if strict else (rows[0] if rows else None)
        if row:
            return {k: row[k] for k in row.keys() if k != "forms"}
    for end in ADJ_ENDINGS:                     # 形容词词尾: schweren → schwer
        if lowered.endswith(end) and len(lowered) > len(end) + 1:
            row = query(
                f"SELECT {COLS} FROM my_words w {JOINS} "
                "WHERE w.german = :w AND w.pos LIKE '形容词%' LIMIT 1",
                w=lowered[:-len(end)],
            ).fetchone()
            if row:
                return dict(row)
    return None


def lexicon_rows(lemmas):
    """词典给的原形候选里, 词库有的那些, 常用的在前(regnet → regnen 比 regen 常用)"""
    found = []
    for g in lemmas:
        row = query(f"SELECT {COLS}, COALESCE(l.rank, 1000000000) AS rk FROM my_words w {JOINS} "
                    "WHERE w.german = :g ORDER BY rk LIMIT 1", g=g).fetchone()
        if row:
            found.append(row)
    found.sort(key=lambda r: r["rk"])
    return [{k: r[k] for k in r.keys() if k != "rk"} for r in found]


def resolve(token):
    """点词: (词, 其他可能的原形)。词 = 词库里的词; 词库没有、词典有时是词典词条(id 为 null, lexicon = true);
    都没有是 None。其他原形给“不是这个词？”用, 最多 3 个"""
    row = find_in_words(token, strict=True)
    if row:                                     # 词库自己的数据对得上, 不用问
        return row, []
    lemmas = lexicon.lemmas_of(token)
    rows = lexicon_rows(lemmas)
    if rows:
        return rows[0], [g for g in lemmas if g.lower() != rows[0]["german"].lower()][:3]
    for g in lemmas:
        hit = lexicon.find(g)[0]
        if hit:
            from dictionary import NO_MEANING_HINT, glossary_row   # dictionary 依赖 lessons, 放这里免得循环导入
            word = {**glossary_row({**hit, "meaning": hit["meaning"] or NO_MEANING_HINT}),
                    "lexicon": True, "needs_meaning": not hit["meaning"], "learned": False, "queued": False}
            return word, [x for x in lemmas if x != g][:3]
    return None, []


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
        glossary = {}       # 同一个词在几课里都有时, 用最先出现的
        for x in lessons:
            for g in x["glossary"]:
                glossary.setdefault((g["german"].lower(), g["gender"]), g)
        _items.update(mtime=mtime, lessons={x["id"]: x for x in lessons},
                      by_lesson=by_lesson, glossary=list(glossary.values()),
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


def drill_items(de, level, drills):
    """替换练习的题, 字段和角色扮演一样, 多了 drill / hint。prompt 是原句, prompt_zh 是新情况"""
    out = []
    for d in drills:
        key = hashlib.sha1(f"drill|{de}|{d['answer']}".encode("utf-8")).hexdigest()[:16]
        out.append({"key": key, "drill": True, "lesson": "", "level": level, "title": "替换练习", "who": "",
                    "prompt": de, "prompt_zh": d["cue"], "hint": d.get("hint", ""),
                    "answer": d["answer"], "answer_zh": d["answer_zh"]})
    return out


def my_items():
    """自带课程 + 当前用户自建课程 + 替换练习的全部题目 → (按 key, 按课程)"""
    base = load_items()
    custom = {x["id"]: roleplay_items(x) for x in my_lessons()}
    by_key = {**base["by_key"], **{i["key"]: i for items in custom.values() for i in items}}
    for r in get_db().execute("SELECT de, level, data FROM sentence_drills"):
        by_key.update({i["key"]: i for i in drill_items(r["de"], r["level"], json.loads(r["data"]))})
    return by_key, {**base["by_lesson"], **custom}


MAX_DONE = 500   # 学完的课最多记多少个


def lesson_state(uid):
    """(最近打开的课, 学完的课的列表), 存在 user_settings 的 lesson_last / lesson_done(JSON)"""
    rows = get_db().execute("SELECT key, value FROM user_settings WHERE user_id = ? AND key IN ('lesson_last', 'lesson_done')",
                            (uid,)).fetchall()
    s = {r["key"]: r["value"] for r in rows}
    try:
        done = json.loads(s.get("lesson_done") or "[]")
    except ValueError:
        done = []
    return s.get("lesson_last"), done if isinstance(done, list) else []


def valid_lesson_id(lid):
    """自带课程的编号, 或者自己的自建课程(u数字)"""
    if not isinstance(lid, str) or len(lid) > 40:
        return False
    if lid in load_items()["lessons"]:
        return True
    return lid[:1] == "u" and lid[1:].isdigit() and get_db().execute(
        "SELECT 1 FROM custom_lessons WHERE id = ? AND user_id = ?", (int(lid[1:]), current_user_id())).fetchone() is not None


@bp.route("/api/lessons")
@login_required
def lesson_list():
    """自带课程的列表(没有课文), 加上这个用户最近打开的课 last 和学完的课 done"""
    last, done = lesson_state(current_user_id())
    return jsonify({"lessons": [{k: x[k] for k in LIST_FIELDS} for x in load_items()["lessons"].values()],
                    "last": last, "done": done})


@bp.route("/api/lessons/progress", methods=["POST"])
@login_required
def lesson_progress():
    """{last: 课程编号} 记下最近打开的课; {done: [课程编号, …]} 加进学完的课(以前存在浏览器里的也用这个搬过来)"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    uid, db = current_user_id(), get_db()
    last, done = lesson_state(uid)
    upsert = "INSERT INTO user_settings (user_id, key, value) VALUES (?,?,?) " \
             "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value"
    if "last" in data:
        if not valid_lesson_id(data["last"]):
            return err("课程不存在", 404)
        last = data["last"]
        db.execute(upsert, (uid, "lesson_last", last))
    if "done" in data:
        new = data["done"]
        if not isinstance(new, list) or len(new) > MAX_DONE:
            return err("格式错误")
        for lid in new:
            if lid not in done and valid_lesson_id(lid):
                done.append(lid)
        done = done[-MAX_DONE:]
        db.execute(upsert, (uid, "lesson_done", json.dumps(done)))
    db.commit()
    return jsonify({"last": last, "done": done})


@bp.route("/api/lessons/<lesson_id>")
@login_required
def lesson_text(lesson_id):
    """一节自带课程的全文; 免费用户每天能开的新课有限(billing.py 的 check_quota)"""
    lesson = load_items()["lessons"].get(lesson_id)
    if lesson is None:
        return err("课程不存在", 404)
    return jsonify({"lesson": lesson})


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
    """到期要复习的句子。count 是到期总数, items 最多 DUE_LIMIT 句; 课文改掉的旧句子跳过
    ?count=1 只要数量(首页用, 不算免费次数, 见 billing.py)"""
    rows = get_db().execute(
        "SELECT item_key FROM sentence_progress WHERE user_id = ? AND next_review <= ? ORDER BY next_review",
        (current_user_id(), now_str()),
    ).fetchall()
    by_key = my_items()[0]
    due = [by_key[r["item_key"]] for r in rows if r["item_key"] in by_key]
    if request.args.get("count"):
        return jsonify({"count": len(due)})
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
def lookup():
    """?w=词形 → {word: 词 或 null, alts: 其他可能的原形}。词库没有、词典有时 word 是词典词条(id 为 null)。
    没登录时只查得到试学的词(试学例句里点到它们)"""
    w = request.args.get("w", "").strip()
    if not w or len(w) > 60:
        return err("词无效")
    row, alts = resolve(w)
    if current_user_id() is None:
        from trial import is_trial_id   # trial 依赖 vocab, 放这里免得循环导入
        if not row or not row["id"] or not is_trial_id(row["id"]):
            return err("请先登录", 401)
        alts = []
    return jsonify({"word": row, "alts": alts})


@bp.route("/api/review/queue", methods=["POST"])
@login_required
def queue_word():
    """加入学习 {word_id} 或一个词的内容: 今天的学习量 +1, 排在新词最前面。已经学过的不用加"""
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
        word_id = word_id_for(get_db(), current_user_id(), row)
    db = get_db()
    queued = enqueue(db, current_user_id(), word_id, 1)
    db.commit()
    return jsonify({"word_id": word_id, "learned": not queued, "queued": queued})