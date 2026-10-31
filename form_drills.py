"""词形练习: 复数、变格、动词变位。题目来自词库已有的数据, 不用 AI, 不影响复习计划

题目格式和句子填空一样(sentences.py), 前端共用 sentence.js 的答题页; 多一个 accept = 都算对的写法。
优先用学过的词, 不够时用当前单词书最常用的词补。
"""
import json
import random
import re

from flask import Blueprint, jsonify

from helpers import current_user_id, err, login_required
from vocab import book_filter, current_book, query

bp = Blueprint("form_drills", __name__)

ROUND_SIZE = 10
POOL_SIZE = 300       # 最多看多少个词
MIN_LEARNED = 5       # 学过的词凑出的题少于这个数时, 用单词书的词补
PLURAL_OK = re.compile(r"[A-Za-zÄÖÜäöüß-]+$")     # 挡掉 Poulets(CH) 这类带注释的数据
ARTICLE_OK = re.compile(r"(der|die|das|des|dem|den) ")
CASE_NAMES = ["第一格", "第二格", "第三格", "第四格"]
PERSONS = ["ich", "du", "er/sie/es", "wir", "ihr", "sie/Sie"]


def question(row, zh, before, answer, de, accept=None):
    return {"word_id": row["id"], "german": row["german"], "gender": row["gender"], "meaning": row["meaning"],
            "zh": zh, "de": de, "tokens": [], "accept": accept or [answer],
            "blank": {"before": before, "answer": answer, "after": ""}}


def forms_of(row):
    return json.loads(row["forms"]) if row["forms"] else {}


def plural_question(row):
    plural = row["plural"].strip()
    if not row["gender"] or not PLURAL_OK.match(plural):
        return None
    return question(row, "写出复数", "die ", plural, f"die {plural}")


def case_slots(row):
    """这个词可以出题的 [(单复数, 第几格, 写法列表)]; 单数第一格是给出的, 不考。数据对不上时返回空"""
    cases = forms_of(row).get("cases") or {}
    sg, pl = cases.get("sg") or [], cases.get("pl") or []
    if len(sg) != 4 or not all(sg) or sg[0].split()[0] != row["gender"]:
        return []
    groups = [("单数", i, sg[i]) for i in range(1, 4)]
    if len(pl) == 4 and all(pl):
        groups += [("复数", i, pl[i]) for i in range(4)]
    slots = []
    for number, i, form in groups:
        ways = [x.strip() for x in form.split(" / ")]       # des Mannes / des Manns 两种都对
        if all(ARTICLE_OK.match(x) and "," not in x and "(" not in x for x in ways):
            slots.append((number, i, ways))
    return slots


def case_question(row):
    slots = case_slots(row)
    if not slots:
        return None
    number, i, ways = random.choice(slots)
    return question(row, f"{CASE_NAMES[i]} · {number}", "", ways[0], " / ".join(ways), ways)


def verb_slots(row):
    """这个动词可以出题的 [(第几人称, 变位)]; 和原形相同的 wir / sie 太简单, 只有不规则动词才考"""
    praesens = forms_of(row).get("praesens") or []
    if len(praesens) != 6 or not all(praesens):
        return []
    german = row["german"].lower()
    slots = []
    for i, form in enumerate(praesens):
        if form.lower() == german:
            continue
        if german.endswith(("ern", "eln")) and form.lower() == german[:-1]:   # 数据里 ich zerschmetter 少了 e, 不出题
            continue
        slots.append((i, form))
    return slots


def verb_question(row):
    slots = verb_slots(row)
    if not slots:
        return None
    i, form = random.choice(slots)
    person = PERSONS[i]
    return question(row, f"{row['german']} 的现在时", person + " ", form, f"{person.split('/')[0]} {form}")


KINDS = {
    "plural": (plural_question, "w.gender != '' AND w.plural != ''"),
    "cases": (case_question, "w.gender != '' AND w.forms LIKE '%\"cases\"%'"),
    "verbs": (verb_question, "w.forms LIKE '%\"praesens\"%'"),
}


def make_questions(rows, maker, seen, n):
    out = []
    for r in rows:
        if len(out) >= n:
            break
        q = maker(r) if r["id"] not in seen else None
        if q:
            seen.add(r["id"])
            out.append(q)
    return out


@bp.route("/api/forms/<kind>")
@login_required
def form_questions(kind):
    if kind not in KINDS:
        return err("题型无效", 404)
    maker, where = KINDS[kind]
    cols = "w.id, w.german, w.gender, w.plural, w.meaning, w.forms"
    rows = query(
        f"SELECT {cols} FROM my_words w JOIN progress p ON p.word_id = w.id AND p.user_id = :uid "
        f"WHERE {where} ORDER BY RANDOM() LIMIT :n", n=POOL_SIZE,
    ).fetchall()
    seen = set()
    questions = make_questions(rows, maker, seen, ROUND_SIZE)
    if len(questions) < MIN_LEARNED:
        book_join, book_args, order = book_filter(current_book(current_user_id()))
        rows = query(f"SELECT {cols} FROM my_words w {book_join} WHERE {where} ORDER BY {order} LIMIT :n",
                     n=POOL_SIZE, **book_args).fetchall()
        random.shuffle(rows)
        questions += make_questions(rows, maker, seen, ROUND_SIZE - len(questions))
    return jsonify({"questions": questions})
