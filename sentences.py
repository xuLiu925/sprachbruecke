"""句子模块: 用词库里的例句出题(填空 / 排序 / 中译德)。只是练习, 不影响复习计划

例句来自 words.example 和 word_details.examples, 格式是「德语\\n中文」, 没有中文翻译的不用。
都从 MY_WORDS 取词(vocab.query), 所以用户改过的例句算数, 删掉的词不出现。

2026-11-07 起结构照听写(dictation.py): 练习范围(单词书 / 错题本)、按词 + 题型用 FSRS 排期(sent_practice)、
错题本(答错过的 + 手动加的 sent_list), 每种题型分开记。每次从这个词的例句里随机挑一句, 不固定同一句。
填空系统判对错; 连词成句、中译德和例句不同时由用户自评, 自评结果照样记。不影响今日学习。
"""
import json
import random
import re

from flask import Blueprint, jsonify, request

from custom_lessons import text
from database import get_db, now_str
from helpers import current_user_id, err, json_body, login_required
from lessons import find_word
from noun_quiz import MASTER_S, PAGE_SIZE, pick_round, update_practice
from today import local_day, read_tz
from vocab import BOOKS, book_filter, current_book, query

bp = Blueprint("sentences", __name__)

MODES = {"cloze", "order", "translate"}
SCOPES = BOOKS + ["wrong"]
ROUND_SIZE = 10       # 一组几题
POOL_SIZE = 300       # 一次看多少个词(不是每个词都有能用的例句)
MAX_SCAN = 1500       # 没练过的词最多往后看多少个, 凑不满就算了
MIN_TOKENS, MAX_TOKENS = 3, 14

# 带引号、括号、斜线(如 ihr/ihm)等的句子不适合出题
BAD_CHARS = re.compile(r'[/()\[\]{}"„“”«»‹›…:;=+*_|<>]')
CHINESE = re.compile(r"[一-鿿]")
WORD = re.compile(r"[^\W\d_]+")
ADJ_ENDINGS = ("e", "en", "em", "er", "es", "n", "m", "r", "s")


def parse_sentence(text):
    """「德语\\n中文」→ (德语, 中文, 词列表); 不适合出题返回 None"""
    lines = [x.strip() for x in (text or "").split("\n") if x.strip()]
    if len(lines) != 2:
        return None
    de, zh = lines
    if BAD_CHARS.search(de) or CHINESE.search(de) or not CHINESE.search(zh):
        return None
    if de[-1] not in ".!?" or re.search(r"[.!?]", de[:-1]):   # 只要一句话; 也挡掉 z.B. 这类缩写
        return None
    tokens = [t.strip(",") for t in de[:-1].split()]
    if not MIN_TOKENS <= len(tokens) <= MAX_TOKENS or not all(re.search(r"\w", t) for t in tokens):
        return None
    return de, zh, tokens


def word_shapes(german, pos, plural, forms):
    """这个词在句子里可能的样子(小写): 原形、复数、变格、变位。形容词加上常见词尾"""
    def last(s):
        parts = (s or "").split()
        return parts[-1] if parts else ""

    def first(s):
        parts = (s or "").split()
        return parts[0] if parts else ""

    shapes = {last(german), last(plural)}
    f = json.loads(forms) if forms else {}
    cases = f.get("cases") or {}
    shapes.update(last(x) for x in (cases.get("sg") or []) + (cases.get("pl") or []))
    shapes.update(first(x) for x in f.get("praesens") or [])   # 可分动词写成 stehe auf, 取前面的词
    past = f.get("past") or []
    if past:
        shapes.add(first(past[0]))        # fuhr
    if len(past) > 1:
        shapes.add(last(past[1]))         # ist gefahren → gefahren
    if (pos or "").startswith("形容词"):
        shapes.update(german + e for e in ADJ_ENDINGS)
    return {s.lower() for s in shapes if s}


def find_blank(de, shapes):
    """在句子里找目标词, 只出现一次才能出填空题; 返回 {before, answer, after} 或 None"""
    hits = [m for m in WORD.finditer(de) if m.group().lower() in shapes]
    if len(hits) != 1:
        return None
    m = hits[0]
    return {"before": de[:m.start()], "answer": m.group(), "after": de[m.end():]}


def make_questions(rows, mode, seen):
    """每个词最多出一题; seen 是已经用过的德语句子, 防止重复"""
    out = []
    for r in rows:
        details = json.loads(r["details"]) if r["details"] else {}
        texts = [r["example"]] + list(details.get("examples") or [])
        random.shuffle(texts)
        for text in texts:
            parsed = parse_sentence(text)
            if parsed is None or parsed[0] in seen:
                continue
            de, zh, tokens = parsed
            blank = find_blank(de, word_shapes(r["german"], r["pos"], r["plural"], r["forms"]))
            if mode == "cloze" and blank is None:
                continue
            seen.add(de)
            out.append({"word_id": r["id"], "german": r["german"], "gender": r["gender"], "meaning": r["meaning"],
                        "de": de, "zh": zh, "tokens": tokens, "blank": blank})
            break
    return out


# 有例句的词(粗筛, 能不能出题还要看 parse_sentence); 和练习记录、手动加的词
HAS_EXAMPLE = "AND (instr(w.example, char(10)) > 0 OR d.details LIKE '%\"examples\"%')"
DETAILS = "LEFT JOIN word_details d ON d.word_id = w.id"
MARKS = ("LEFT JOIN sent_practice sp ON sp.word_id = w.id AND sp.user_id = :uid AND sp.mode = :mode "
         "LEFT JOIN sent_list sl ON sl.word_id = w.id AND sl.user_id = :uid AND sl.mode = :mode")
IN_WRONG = "AND (sp.weak = 1 OR sl.word_id IS NOT NULL)"
RISK = "COALESCE((julianday(:now) - julianday(sp.last_review)) / sp.stability, 1e9) DESC, sp.last_at"
COLS = "w.id, w.german, w.pos, w.gender, w.plural, w.meaning, w.example, w.forms, d.details"


@bp.route("/api/sentences")
@login_required
def sentences():
    """一组句子题 ?mode=cloze|order|translate&scope=单词书或 wrong: 每个词一题。
    到期的(最容易忘的优先) > 没练过的(今日学习学过的优先, 再按词频) > 未到期里最容易忘的。不带 scope 用当前单词书"""
    mode = request.args.get("mode", "cloze")
    if mode not in MODES:
        return err("题型无效")
    scope = request.args.get("scope") or current_book(current_user_id())
    if scope not in SCOPES:
        return err("范围无效")
    base = (f"SELECT {COLS} FROM my_words w {{join}} {DETAILS} {MARKS} "
            f"LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid WHERE 1 {HAS_EXAMPLE} {{where}}")
    now, seen = now_str(), set()
    if scope == "wrong":
        rows = query(base.format(join="", where=IN_WRONG) + f" ORDER BY {RISK} LIMIT :pool",
                     pool=POOL_SIZE, now=now, mode=mode).fetchall()
        return jsonify({"questions": pick_round(make_questions(rows, mode, seen)[:ROUND_SIZE], [], [], ROUND_SIZE)})
    join, args, order = book_filter(scope)
    end = local_day(read_tz())[2]

    def pick(where, tail, scan=POOL_SIZE):
        out = []
        for off in range(0, scan, POOL_SIZE):          # 前面的词没有能用的例句时, 再往后看
            rows = query(base.format(join=join, where=where) + f" ORDER BY {tail} LIMIT :pool OFFSET :off",
                         pool=POOL_SIZE, off=off, now=now, end=end, mode=mode, **args).fetchall()
            out += make_questions(rows, mode, seen)
            if len(out) >= ROUND_SIZE or len(rows) < POOL_SIZE:
                break
        return out[:ROUND_SIZE]
    due = pick("AND sp.word_id IS NOT NULL AND (sp.next_review IS NULL OR sp.next_review < :end)", RISK)
    new = pick("AND sp.word_id IS NULL", f"p.word_id IS NULL, {order}", MAX_SCAN)
    spare = pick("AND sp.next_review >= :end", RISK)
    return jsonify({"questions": pick_round(due, new, spare, ROUND_SIZE)})


def read_mode(mode):
    return mode if mode in MODES else None


@bp.route("/api/sentences/<mode>/books")
@login_required
def sent_books(mode):
    """练习范围: 各单词书有例句的词数和这种题型的进度、错题本词数。字段名同定冠词练习(nouns = 词数), 前端共用"""
    if not read_mode(mode):
        return err("题型无效", 404)
    counts = ("COUNT(*) AS nouns, COUNT(sp.word_id) AS practiced, "
              f"COALESCE(SUM(CASE WHEN 1 {IN_WRONG} THEN 1 ELSE 0 END), 0) AS weak, "
              "COALESCE(SUM(sp.stability >= :master), 0) AS mastered")
    by = {}
    for table_name, key in (("word_levels", "level"), ("word_books", "book")):
        for r in query(f"SELECT l.{key} AS book, {counts} FROM my_words w JOIN {table_name} l ON l.word_id = w.id "
                       f"{DETAILS} {MARKS} WHERE 1 {HAS_EXAMPLE} GROUP BY l.{key}", master=MASTER_S, mode=mode).fetchall():
            by[r["book"]] = dict(r)
    whole = query(f"SELECT {counts} FROM my_words w {DETAILS} {MARKS} WHERE 1 {HAS_EXAMPLE}",
                  master=MASTER_S, mode=mode).fetchone()
    # 错题本里也可能有手动加的、没有例句的词: 错题数按错题本本身算
    wrong = query(f"SELECT COUNT(*) FROM my_words w {DETAILS} {MARKS} WHERE 1 {IN_WRONG}", mode=mode).fetchone()[0]
    by["all"] = {**dict(whole), "book": "all"}
    return jsonify({"current": current_book(current_user_id()), "wrong": wrong,
                    "books": [by[b] for b in BOOKS if b in by]})


@bp.route("/api/sentences/<mode>/words")
@login_required
def sent_words(mode):
    """查看一个范围里的词 ?scope=&page=: 带 wrong / streak / manual"""
    if not read_mode(mode):
        return err("题型无效", 404)
    scope = request.args.get("scope", "")
    if scope not in SCOPES:
        return err("范围无效")
    try:
        page = max(int(request.args.get("page", "1")), 1)
    except ValueError:
        return err("页码无效")
    if scope == "wrong":
        join, where, args, order = "", IN_WRONG, {}, "sp.last_at DESC, w.german"
    else:
        join, args, order = book_filter(scope)
        where = HAS_EXAMPLE
    source = f"FROM my_words w {join} {DETAILS} {MARKS} WHERE 1 {where}"
    total = query(f"SELECT COUNT(*) {source}", mode=mode, **args).fetchone()[0]
    rows = query(
        "SELECT w.id, w.german, w.gender, w.plural, w.meaning, COALESCE(sp.wrong, 0) AS wrong, "
        f"COALESCE(sp.streak, 0) AS streak, sl.word_id IS NOT NULL AS manual {source} ORDER BY {order} LIMIT :lim OFFSET :off",
        lim=PAGE_SIZE, off=(page - 1) * PAGE_SIZE, mode=mode, **args,
    ).fetchall()
    words = [{**dict(r), "manual": bool(r["manual"])} for r in rows]
    return jsonify({"words": words, "total": total, "page": page, "pages": max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)})


@bp.route("/api/sentences/<mode>/result", methods=["POST"])
@login_required
def sent_result(mode):
    """记一次作答 {word_id, ok}: 只记每组第一次作答(前端负责); 自评的题等用户选了才记"""
    if not read_mode(mode):
        return err("题型无效", 404)
    data = json_body()
    word_id, ok = (data.get("word_id"), data.get("ok")) if data else (None, None)
    if isinstance(word_id, bool) or not isinstance(word_id, int) or not isinstance(ok, bool):
        return err("参数无效")
    if query("SELECT 1 FROM all_my_words WHERE id = :id", id=word_id).fetchone() is None:
        return err("单词不存在", 404)
    db = get_db()
    update_practice(db, current_user_id(), word_id, 3 if ok else 1, table="sent_practice", keys={"mode": mode})
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/sentences/<mode>/list", methods=["POST"])
@login_required
def sent_add(mode):
    """加入这种题型的错题本 {word_id} 或 {text}: 返回 added / skipped / missing"""
    if not read_mode(mode):
        return err("题型无效", 404)
    data = json_body()
    if data is None:
        return err("请求格式错误")
    if "word_id" in data:
        word_id = data["word_id"]
        if isinstance(word_id, bool) or not isinstance(word_id, int):
            return err("单词无效")
        if query("SELECT 1 FROM my_words WHERE id = :id", id=word_id).fetchone() is None:
            return err("单词不存在", 404)
        ids, missing = [word_id], []
    else:
        names = [x for x in re.split(r"[,，;；、\s]+", text(data.get("text"), 3000))
                 if x and x.lower() not in ("der", "die", "das")]
        if not names:
            return err("请输入要加入的词")
        ids, missing = [], []
        for name in names[:100]:
            hit = find_word(name)
            if hit and hit["id"]:
                ids.append(hit["id"])
            else:
                missing.append(name)
    db = get_db()
    uid = current_user_id()
    added = 0
    for word_id in dict.fromkeys(ids):
        added += db.execute("INSERT OR IGNORE INTO sent_list (user_id, word_id, mode, added_at) VALUES (?,?,?,?)",
                            (uid, word_id, mode, now_str())).rowcount
    db.commit()
    return jsonify({"added": added, "skipped": len(set(ids)) - added, "missing": missing})


@bp.route("/api/sentences/<mode>/list/<int:word_id>", methods=["DELETE"])
@login_required
def sent_remove(mode, word_id):
    """移出错题本: 手动加的删掉, 错过的记录清零"""
    if not read_mode(mode):
        return err("题型无效", 404)
    db = get_db()
    uid = current_user_id()
    db.execute("DELETE FROM sent_list WHERE user_id = ? AND word_id = ? AND mode = ?", (uid, word_id, mode))
    db.execute("UPDATE sent_practice SET wrong = 0, streak = 0, weak = 0 WHERE user_id = ? AND word_id = ? AND mode = ?",
               (uid, word_id, mode))
    db.commit()
    return jsonify({"ok": True})
