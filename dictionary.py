"""查词: 德语(原形、复数、变位、变格、形容词词尾)和中文都能查, 按相关程度排序

和 /api/words 的区别: 那边是词库列表, 这边查得更广, 最相关的词排在最前面。不用 AI。
返回的字段和词库列表一样, 多一个 form: 查的是变化形式时, 记下用户输入的那个词。

情景课的仓储词(glossary)也能查到。它们不在 words 表里, 所以 id 是 null, glossary = true;
用户加入复习后就变成他的私有词, 那时词库里有了, 这里不再重复显示。

查不到时可以用 AI 查询(/api/dict/ai): 用户点了才调用, 只有管理员能用, 结果存 ai_words,
同样的查询不再调用 AI。AI 的结果也是 id 为 null, ai_word = true, 同样要加入复习才进词库。
"""
import json
import re

from flask import Blueprint, jsonify, request

from auth import admin_required, is_admin
from custom_lessons import TOKEN, AiError, api_key, call_gemini, extract_json, text
from database import get_db, now_str
from helpers import current_user_id, err, json_body, login_required
from lessons import find_word, like_escape, load_items, my_lessons
from vocab import GENDERS, query, word_status

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


def all_glossary():
    """自带 15 课和当前用户自建课程的词表; 同一个词只留一份, 自带的优先"""
    seen = {}
    for g in load_items()["glossary"] + [g for lesson in my_lessons() for g in lesson["glossary"]]:
        seen.setdefault((g["german"].lower(), g["gender"]), g)
    return list(seen.values())


def not_in_words(g):
    return query("SELECT 1 FROM all_my_words WHERE german = :g AND gender = :a LIMIT 1",
                 g=g["german"], a=g["gender"]).fetchone() is None


def glossary_german(q):
    """(档次, 词) 列表, 档次的含义和 search_german 一样"""
    low, out = q.lower(), []
    for g in all_glossary():
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
    glossary = [(chinese_rank(g["meaning"], q), glossary_row(g)) for g in all_glossary()
                if q in g["meaning"] and not_in_words(g)]
    return merge(words, glossary)


# ---------- AI 查词 ----------
def lookup_key(q):
    return "".join(q.split()).lower()


def build_prompt(q, context=""):
    where = f"\n这个词出现在这句话里，请按句中的意思解释：{context}\n" if context else ""
    return f"""你是德汉词典编辑，读者是在德国海外仓工作的中文学习者。请查这个词：{q}
{where}
规则：
- 输入可能是德语（可能是变化形式）或中文。给出对应德语词的原形。中文输入时选仓库工作中最常用的德语词。
- 如果不是真实存在的词，或你不确定，只输出 {{"found": false}}，不要编造。
- gender 只能是 der、die、das 或空字符串，名词必须填写。pos 用中文，如 名词、动词、形容词。
- plural 是名词复数，其他词性留空。meaning 是简短的中文释义。
- example 是一句简单、正确的例句，格式：德语 + 换行 + 中文翻译。
- 只输出一个 JSON 对象，不要 Markdown 代码块，不要其他文字。

JSON 格式：
{{"found": true, "german": "Lieferschein", "gender": "der", "pos": "名词", "plural": "Lieferscheine", "meaning": "送货单", "example": "Hier ist der Lieferschein.\\n这是送货单。"}}"""


def clean_example(raw):
    lines = [x.strip() for x in raw.split("\n") if x.strip()] if isinstance(raw, str) else []
    if len(lines) != 2 or CHINESE.search(lines[0]) or not CHINESE.search(lines[1]) or len(raw) > 300:
        return ""
    return "\n".join(lines)


def clean_ai_word(data):
    """返回 (词, 错误)。只留下认识的字段"""
    if not isinstance(data, dict):
        return None, "内容不是 JSON 对象"
    german, pos = text(data.get("german"), 100), text(data.get("pos"), 20)
    meaning, gender = text(data.get("meaning"), 300), data.get("gender", "")
    if not TOKEN.search(german) or CHINESE.search(german):
        return None, "德语词无效"
    if not CHINESE.search(meaning):
        return None, "缺少中文释义"
    if gender not in GENDERS or (pos.startswith("名词") and not gender):
        return None, "冠词无效"
    return {"german": german, "gender": gender, "pos": pos, "plural": text(data.get("plural"), 100),
            "meaning": meaning, "example": clean_example(data.get("example"))}, None


def load_ai_word(q):
    row = get_db().execute("SELECT data FROM ai_words WHERE lookup_key = ?", (lookup_key(q),)).fetchone()
    return json.loads(row["data"]) if row else None


def ai_row(word):
    return {**glossary_row(word), "glossary": False, "ai_word": True, "example": word["example"]}


@bp.route("/api/dict/ai", methods=["POST"])
@admin_required
def ai_lookup():
    """用 AI 查一个词 {q, context}: context 是可选的原句, 让释义贴合语境。
    已保存就直接返回。AI 说没有这个词时 word 是 null, 不保存, 以后可以再试"""
    data = json_body()
    q = text(data.get("q"), 51) if data else ""
    if not q or len(q) > 50:
        return err("请输入要查的词")
    saved = load_ai_word(q)
    if saved:
        return jsonify({"word": ai_row(saved)})
    try:
        raw = call_gemini(build_prompt(q, text(data.get("context"), 300)))
    except AiError as ex:
        return err(ex.msg, ex.code)
    parsed = extract_json(raw)
    if parsed is not None and parsed.get("found") is False:
        return jsonify({"word": None})
    word, e = clean_ai_word(parsed)
    if e:
        return err("AI 查询结果不完整（" + e + "），请再试一次", 502)
    db = get_db()
    db.execute("INSERT OR REPLACE INTO ai_words (lookup_key, query, data, created_at) VALUES (?,?,?,?)",
               (lookup_key(q), q, json.dumps(word, ensure_ascii=False), now_str()))
    db.commit()
    return jsonify({"word": ai_row(word)})


@bp.route("/api/dict")
@login_required
def lookup():
    q = request.args.get("q", "").strip()
    if not q or len(q) > 50:
        return err("请输入要查的词")
    words = search_chinese(q) if CHINESE.search(q) else search_german(q)
    saved = load_ai_word(q)
    if saved and not_in_words(saved):
        words = [ai_row(saved)] + words[:LIMIT - 1]
    return jsonify({"words": words, "can": is_admin(current_user_id()), "ai": bool(api_key())})
