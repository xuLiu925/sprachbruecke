"""不定冠词、否定冠词、物主冠词填空题: 从单词书或错题本出题, 不用 AI, 不影响今日学习

这三个知识点练的是词尾规律, 不是每个词的词性, 所以按“格子”(如 第四格阳性)练, 词只是载体:
每组尽量覆盖所有格子, 最近错得多的格子多出。选词优先定冠词练得稳的词, 这样错了基本就是词尾的问题。
作答记在 noun_answers.cell(如 indef:der:3)。词性答错时算进这个词的词性记忆(和定冠词共用),
其他情况不碰 noun_practice, 见 noun_quiz.memory_rating()。

句型是手写的, 任意名词都要说得通, 改动后要请人核对。ein 第一格阳性和中性都对, 判断“词性错”用 gender_picks()。
"""
import collections
import random

from flask import Blueprint, jsonify, request

import noun_quiz as nq
from gender_hint import short_meaning
from helpers import current_user_id, err, login_required
from database import get_db
from vocab import book_filter, current_book, query

bp = Blueprint("article_quiz", __name__)

POOL = 400            # 一次取多少个词来配格子
RECENT = 10           # 每个格子看最近几次作答
UNSEEN_WEIGHT = 2     # 没练过的格子的权重; 全对是 1, 全错是 4
GENDERS = ["der", "die", "das"]
KEY_ZH = {"der": "阳性", "die": "阴性", "das": "中性", "pl": "复数"}
# 词尾, 下标同 forms 里的格(一、二、三、四格)
ENDINGS = {"der": ["", "es", "em", "en"], "die": ["e", "er", "er", "e"],
           "das": ["", "es", "em", ""], "pl": ["e", "er", "en", "e"]}
# 物主冠词: (提示, 词干, 翻译)
OWNERS = [("ich", "mein", "我的"), ("du", "dein", "你的"), ("er", "sein", "他的"), ("sie（她）", "ihr", "她的"),
          ("es", "sein", "它的"), ("wir", "unser", "我们的"), ("ihr（你们）", "euer", "你们的"),
          ("sie（他们）", "ihr", "他们的"), ("Sie（您）", "Ihr", "您的")]
# 句型: {第几格: (单数句子, 复数句子, 解释, 单数翻译, 复数翻译)}, {x} = ___ + 名词, {m} = 词义, {p} = 谁的
FRAMES = {
    "indef": {
        0: ("Das ist {x}.", "", "Das ist … 后面是第一格", "这是一个{m}。", ""),
        1: ("Wir kommen wegen {x}.", "", "wegen + 第二格", "我们是因为一个{m}来的。", ""),
        2: ("Wir sprechen von {x}.", "", "von + 第三格", "我们在说一个{m}。", ""),
        3: ("Wir suchen {x}.", "", "suchen + 第四格", "我们在找一个{m}。", ""),
    },
    "kein": {
        0: ("Das ist {x}.", "Das sind {x}.", "Das ist / sind … 后面是第一格", "这不是{m}。", "这些不是{m}。"),
        2: ("Das hat mit {x} zu tun.", "Das hat mit {x} zu tun.", "mit + 第三格", "这和任何{m}都没有关系。", "这和任何{m}都没有关系。"),
        3: ("Wir haben {x}.", "Wir haben {x}.", "haben + 第四格", "我们没有{m}。", "我们没有{m}。"),
    },
    "poss": {
        0: ("Das ist {x}.", "Das sind {x}.", "Das ist / sind … 后面是第一格", "这是{p}{m}。", "这些是{p}{m}。"),
        1: ("Wir kommen wegen {x}.", "Wir kommen wegen {x}.", "wegen + 第二格", "我们是因为{p}{m}来的。", "我们是因为{p}这些{m}来的。"),
        2: ("Wir sprechen von {x}.", "Wir sprechen von {x}.", "von + 第三格", "我们在说{p}{m}。", "我们在说{p}这些{m}。"),
        3: ("Wir suchen {x}.", "Wir suchen {x}.", "suchen + 第四格", "我们在找{p}{m}。", "我们在找{p}这些{m}。"),
    },
}


def form(stem, key, case_no):
    """词干 + 词尾。euer 加词尾时去掉中间的 e: eure, euren"""
    ending = ENDINGS[key][case_no]
    return ("eur" if stem == "euer" and ending else stem) + ending


def gender_picks(stem, gender, case_no):
    """选了这些 = 词性记错了(别的词性在这个格的形式); 和正确答案一样的不算, 如第一格 ein 阳性中性都对"""
    return sorted({form(stem, g, case_no) for g in GENDERS} - {form(stem, gender, case_no)})


def answer_note(kind, stem, owner, ending):
    """单词卡上的说明: 词库按原形显示, 这里说清这个答案是怎么变来的, 如 sein 的卡片只写着“是，在”"""
    name = {"indef": "不定冠词", "kein": "否定冠词", "poss": "物主冠词"}[kind]
    rule = f"{stem} + 词尾 -{ending}" if ending else f"{stem}，没有词尾"
    if stem == "euer" and ending:
        rule += "，去掉中间的 e"
    return f"{name}：{owner}（{rule}）" if owner else f"{name}：{rule}"


def all_cells(kind):
    keys = GENDERS if kind == "indef" else GENDERS + ["pl"]      # 复数没有不定冠词
    return [f"{kind}:{key}:{i}" for key in keys for i in FRAMES[kind]]


def weights_from(rows, cells):
    """rows = 最新的在前的 (格子, 对错): 最近错得多的格子权重大"""
    recent = collections.defaultdict(list)
    for cell, ok in rows:
        if len(recent[cell]) < RECENT:
            recent[cell].append(ok)
    return {c: 1 + 3 * (1 - sum(recent[c]) / len(recent[c])) if recent[c] else UNSEEN_WEIGHT for c in cells}


def deal_cells(cells, weights, n):
    """先每个格子一题(格子比题多时按权重抽), 剩下的题按权重多出"""
    picked = sorted(cells, key=lambda c: random.random() ** (1 / weights[c]), reverse=True)[:n]
    picked += random.choices(cells, [weights[c] for c in cells], k=n - len(picked))
    random.shuffle(picked)
    return picked


def noun_table(kind, row):
    """这个词能用的名词形式 {(单复数, 第几格): 名词}。没有复数的词大多不可数, 不说 ein Wasser"""
    tab = {(num, i): noun for num, i, _a, noun in nq.table(row)}
    if kind == "indef" and len(tab) > 1 and not any(num == "复数" for num, _i in tab):
        return {}
    return tab


def noun_for(tab, row, key, i):
    if key != "pl" and key != row["gender"]:
        return None
    return tab.get(("复数" if key == "pl" else "单数", i))


def make_question(row, cell, noun):
    kind, key, i = cell.split(":")
    i = int(i)
    label, stem, owner = random.choice(OWNERS) if kind == "poss" else ("", "ein" if kind == "indef" else "kein", "")
    answer = form(stem, key, i)
    plural = key == "pl"
    sg, pl, why, zh_sg, zh_pl = FRAMES[kind][i]
    name = nq.CASE_NAMES[i] + KEY_ZH[key]
    zh = (zh_pl if plural else zh_sg).format(m=short_meaning(row["meaning"]) or row["meaning"], p=owner)
    explain = (f"{label} → {stem}；" if label else "") + f"{why}；{name} → {answer}"
    q = nq.base_question(row, (pl if plural else sg).format(x="___ " + noun), answer, "复数" if plural else "单数",
                         explain, zh, "template", [i])
    return {**q, "options": [stem + e for e in ("", "e", "en", "em", "er", "es")] if stem != "euer"
                 else ["euer", "eure", "euren", "eurem", "eurer", "eures"],
            "gender_picks": [] if plural else gender_picks(stem, row["gender"], i),
            "article": kind, "cell": cell, "cell_name": name,
            "answer_lemma": stem, "answer_note": answer_note(kind, stem, owner, ENDINGS[key][i])}


def fill_round(kind, rows, cells, n):
    """给每个格子配一个词, 每个词最多一题; 配完还有词而题不够时(错题本里词少), 让剩下的词随便选个能用的格子"""
    tables, used, out = {}, set(), []
    def tab(r):
        return tables.setdefault(r["id"], noun_table(kind, r))
    for cell in cells:
        _kind, key, i = cell.split(":")
        for r in rows:
            noun = None if r["id"] in used else noun_for(tab(r), r, key, int(i))
            if noun:
                used.add(r["id"])
                out.append(make_question(r, cell, noun))
                break
    every = all_cells(kind)
    for r in rows:
        if len(out) >= n:
            break
        if r["id"] in used:
            continue
        fits = [(c, noun_for(tab(r), r, c.split(":")[1], int(c.split(":")[2]))) for c in every]
        fits = [x for x in fits if x[1]]
        if fits:
            used.add(r["id"])
            out.append(make_question(r, *random.choice(fits)))
    return out[:n]


def shuffled_tiers(rows):
    """同一档内打乱, 每组的词不一样; rows 已按档排好"""
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r["tier"]].append(r)
    out = []
    for tier in sorted(groups):
        random.shuffle(groups[tier])
        out += groups[tier]
    return out


@bp.route("/api/grammar/articles")
@login_required
def articles():
    """?type=indef|kein|poss&scope=单词书或 wrong&n=14: 一组题, 每个词最多一题。不带 scope 时用当前单词书"""
    kind = request.args.get("type", "")
    if kind not in FRAMES:
        return err("类型无效")
    uid = current_user_id()
    scope = request.args.get("scope") or current_book(uid)
    if scope not in nq.SCOPES:
        return err("范围无效")
    try:
        n = min(max(int(request.args.get("n", "14")), 1), nq.MAX_ROUND)
    except ValueError:
        return err("题数无效")
    if scope == "wrong":
        join, where, args, order = "", nq.IN_WRONG, {}, "w.id"
    else:
        join, args, order = book_filter(scope)
        where = ""
    # 定冠词练得稳的 > 今日学习学过的 > 其他(同档内词频靠前的) > 错题本里的
    rows = query(
        "SELECT w.id, w.german, w.gender, w.meaning, w.forms, CASE WHEN np.weak = 1 THEN 3 WHEN np.stability >= 3 THEN 0 "
        f"WHEN p.word_id IS NOT NULL THEN 1 ELSE 2 END AS tier FROM my_words w {join} {nq.MARKS} "
        f"LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid WHERE w.gender != '' {where} "
        f"ORDER BY tier, {order} LIMIT :pool", pool=POOL, **args,
    ).fetchall()
    cells = all_cells(kind)
    recent = get_db().execute("SELECT cell, ok FROM noun_answers WHERE user_id = ? AND cell LIKE ? ORDER BY id DESC LIMIT 500",
                              (uid, kind + ":%")).fetchall()
    weights = weights_from([tuple(r) for r in recent], cells)
    return jsonify({"questions": fill_round(kind, shuffled_tiers(rows), deal_cells(cells, weights, n), n)})
