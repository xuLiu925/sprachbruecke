"""查词: 德语(原形、复数、变位、变格、形容词词尾)和中文都能查, 按相关程度排序

和 /api/words 的区别: 那边是词库列表, 这边查得更广, 最相关的词排在最前面。不用 AI。
返回的字段和词库列表一样, 多一个 form: 查的是变化形式时, 记下用户输入的那个词。
"""
import re

from flask import Blueprint, jsonify, request

from helpers import err, login_required
from lessons import find_word, like_escape
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
    return [out_row(r, q if r["rk"] in (1, 2) else None) for r in rows]


def search_chinese(q):
    """释义完全相同 > 某个义项完全相同 > 某个义项开头 > 其他包含"""
    rows = query(
        f"SELECT {COLS} FROM my_words w {JOINS} WHERE w.meaning LIKE :part ESCAPE '\\' "
        f"ORDER BY {LEVEL_RANK}, length(w.german) LIMIT :lim",
        part=f"%{like_escape(q)}%", lim=CHINESE_POOL,
    ).fetchall()

    def rank(row):
        meaning = row["meaning"]
        parts = [p for p in SEGMENT.split(meaning) if p]
        if meaning == q:
            return 0
        if q in parts:
            return 1
        if any(p.startswith(q) for p in parts):
            return 2
        return 3

    return [out_row(r) for r in sorted(rows, key=rank)[:LIMIT]]   # sorted 是稳定排序, 同一档里常用词在前


@bp.route("/api/dict")
@login_required
def lookup():
    q = request.args.get("q", "").strip()
    if not q or len(q) > 50:
        return err("请输入要查的词")
    words = search_chinese(q) if CHINESE.search(q) else search_german(q)
    return jsonify({"words": words})
