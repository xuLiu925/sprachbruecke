"""查词: 德语(原形、复数、变位、变格、形容词词尾)和中文都能查, 按相关程度排序

和 /api/words 的区别: 那边是词库列表, 这边查得更广, 最相关的词排在最前面。不用 AI。
返回的字段和词库列表一样, 多一个 form: 查的是变化形式时, 记下用户输入的那个词。

情景课的仓储词(glossary)也能查到。它们不在 words 表里, 所以 id 是 null, glossary = true;
用户加入复习后就变成他的私有词, 那时词库里有了, 这里不再重复显示。
"""
import re

from flask import Blueprint, jsonify, request

from helpers import err, login_required
from lessons import find_word, like_escape, load_items
from vocab import query, word_status

bp = Blueprint("dictionary", __name__)

LIMIT = 50
CHINESE_POOL = 1000       # 中文先取这么多, 再排序
CHINESE = re.compile(r"[一-鿿]")
SEGMENT = re.compile(r"[，,；;、/（）()【】\s]+")
COLS = ("w.id, w.german, w.gender, w.pos, w.plural, w.meaning, w.edited, w.hidden, w.private, l.level, "
        "p.next_review, p.stability, p.spell_ok, p.reps")
JOINS = ("LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid "
         "LEFT JOIN word_levels l ON l.word_id = w.id")
LEVEL_RANK = "COALESCE(l.rank, 1000000000)"


def out_row(row, form=None):
    d = dict(row)
    d["status"] = word_status(d)
    d["edited"], d["hidden"], d["private"] = bool(d["edited"]), bool(d["hidden"]), bool(d["private"])
    for k in ("stability", "spell_ok", "reps", "rk"):
        d.pop(k, None)
    if form:
        d["form"] = form
    return d


def glossary_row(g, form=None):
    d = {"id": None, "glossary": True, "german": g["german"], "gender": g["gender"], "pos": g["pos"],
         "plural": g["plural"], "meaning": g["meaning"], "level": None, "next_review": None, "status": "new",
         "edited": False, "hidden": False, "private": False}
    if form:
        d["form"] = form
    return d


def not_in_words(g):
    return query("SELECT 1 FROM all_my_words WHERE german = :g AND gender = :a LIMIT 1",
                 g=g["german"], a=g["gender"]).fetchone() is None


def glossary_german(q):
    """(档次, 词) 列表, 档次的含义和 search_german 一样"""
    low, out = q.lower(), []
    for g in load_items()["glossary"]:
        german, plural = g["german"].lower(), g["plural"].lower()
        if german == low:
            rk = 0
        elif plural == low:
            rk = 1
        elif german.startswith(low):
            rk = 3
        elif low in german:
            rk = 4
        elif low in g["meaning"].lower():
            rk = 5
        else:
            continue
        if not_in_words(g):
            out.append((rk, glossary_row(g, q if rk == 1 else None)))
    return out


def chinese_rank(meaning, q):
    """释义完全相同 0 > 某个义项完全相同 1 > 某个义项开头 2 > 其他包含 3"""
    parts = [p for p in SEGMENT.split(meaning) if p]
    if meaning == q:
        return 0
    if q in parts:
        return 1
    if any(p.startswith(q) for p in parts):
        return 2
    return 3


def merge(ranked_words, ranked_glossary):
    """按档次合并; 同一档里仓储词排前面(用户查它们多半是为了工作)"""
    merged = ranked_glossary + ranked_words
    return [w for _rk, w in sorted(merged, key=lambda x: x[0])[:LIMIT]]   # sorted 是稳定排序


def search_german(q):
    """原形 > 复数 > 变化形式 > 开头相同 > 词里包含 > 释义里有"""
    lowered = q[:1].lower() + q[1:]
    e, el = like_escape(q), like_escape(lowered)
    hit = find_word(q)
    rows = query(
        f"SELECT {COLS}, CASE WHEN w.german = :q COLLATE NOCASE OR w.german = :low THEN 0 "
        "WHEN w.plural = :q COLLATE NOCASE OR w.plural = :low THEN 1 "
        "WHEN w.id = :hit THEN 2 "
        "WHEN w.german LIKE :start ESCAPE '\\' THEN 3 "
        "WHEN w.german LIKE :part ESCAPE '\\' THEN 4 ELSE 5 END AS rk "
        f"FROM my_words w {JOINS} "
        "WHERE w.german = :q COLLATE NOCASE OR w.german = :low OR w.plural = :q COLLATE NOCASE OR w.plural = :low "
        "OR w.id = :hit OR w.german LIKE :part ESCAPE '\\' OR w.meaning LIKE :part ESCAPE '\\' "
        f"ORDER BY rk, {LEVEL_RANK}, length(w.german) LIMIT :lim",
        q=q, low=lowered, hit=hit["id"] if hit else -1, start=e + "%", part=f"%{e}%", lim=LIMIT,
    ).fetchall()
    # el 只在首字母是变音时和 e 不同, 这时 LIKE 不分大小写的规则管不到, 再查一次开头
    if el != e:
        seen = {r["id"] for r in rows}
        extra = query(
            f"SELECT {COLS}, 3 AS rk FROM my_words w {JOINS} WHERE w.german LIKE :start ESCAPE '\\' "
            f"ORDER BY {LEVEL_RANK}, length(w.german) LIMIT :lim",
            start=el + "%", lim=LIMIT,
        ).fetchall()
        rows = sorted(list(rows) + [r for r in extra if r["id"] not in seen], key=lambda r: r["rk"])[:LIMIT]
    return merge([(r["rk"], out_row(r, q if r["rk"] in (1, 2) else None)) for r in rows], glossary_german(q))


def search_chinese(q):
    rows = query(
        f"SELECT {COLS} FROM my_words w {JOINS} WHERE w.meaning LIKE :part ESCAPE '\\' "
        f"ORDER BY {LEVEL_RANK}, length(w.german) LIMIT :lim",
        part=f"%{like_escape(q)}%", lim=CHINESE_POOL,
    ).fetchall()
    words = [(chinese_rank(r["meaning"], q), out_row(r)) for r in rows]   # 查询已按常用程度排好, 同一档里常用词在前
    glossary = [(chinese_rank(g["meaning"], q), glossary_row(g)) for g in load_items()["glossary"]
                if q in g["meaning"] and not_in_words(g)]
    return merge(words, glossary)


@bp.route("/api/dict")
@login_required
def lookup():
    q = request.args.get("q", "").strip()
    if not q or len(q) > 50:
        return err("请输入要查的词")
    words = search_chinese(q) if CHINESE.search(q) else search_german(q)
    return jsonify({"words": words})
