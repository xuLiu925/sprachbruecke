"""句子模块: 用词库里的例句出题(填空 / 排序 / 中译德)。只是练习, 不影响复习计划

例句来自 words.example 和 word_details.examples, 格式是「德语\\n中文」, 没有中文翻译的不用。
都从 MY_WORDS 取词(vocab.query), 所以用户改过的例句算数, 删掉的词不出现。
"""
import json
import random
import re

from flask import Blueprint, jsonify, request

from helpers import current_user_id, err, login_required
from vocab import book_filter, current_book, query

bp = Blueprint("sentences", __name__)

MODES = {"cloze", "order", "translate"}
ROUND_SIZE = 10       # 一组几题
POOL_SIZE = 300       # 最多看多少个词(不是每个词都有能用的例句)
MIN_LEARNED = 5       # 学过的词凑出的题少于这个数时, 用当前单词书最常用的词补
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


@bp.route("/api/sentences")
@login_required
def sentences():
    """一组句子题 ?mode=cloze|order|translate: 优先用学过的词, 不够时用当前单词书最常用的词补"""
    mode = request.args.get("mode", "cloze")
    if mode not in MODES:
        return err("题型无效")
    cols = "w.id, w.german, w.pos, w.gender, w.plural, w.meaning, w.example, w.forms, d.details"
    details = "LEFT JOIN word_details d ON d.word_id = w.id"
    rows = query(
        f"SELECT {cols} FROM my_words w JOIN progress p ON p.word_id = w.id AND p.user_id = :uid {details} "
        "ORDER BY RANDOM() LIMIT :n", n=POOL_SIZE,
    ).fetchall()
    seen = set()
    questions = make_questions(rows, mode, seen)[:ROUND_SIZE]
    if len(questions) < MIN_LEARNED:
        book_join, book_args, order = book_filter(current_book(current_user_id()))
        rows = query(f"SELECT {cols} FROM my_words w {book_join} {details} ORDER BY {order} LIMIT :n",
                     n=POOL_SIZE, **book_args).fetchall()
        random.shuffle(rows)
        questions += make_questions(rows, mode, seen)[:ROUND_SIZE - len(questions)]
    return jsonify({"questions": questions})
