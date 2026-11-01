"""动词现在时填空题: 从单词书或错题本的动词出题, 不用 AI, 不影响今日学习

每个动词的句子: 手写句子(verb_sentences.py) + 真实例句(只用能确定人称的句子)。都没有时出短题 `du ___`, 不硬套句型:
动词要的宾语和介词各不相同, 通用句型会造出错句。
词形的记忆用 FSRS 排期(verb_practice), 和词义的 progress 分开, 选词规则同定冠词(noun_quiz.pick_round)。
答对 = 良好; 词形答错 = 忘了; 人称用错、开着提示不改记忆状态, 这个词明天再出。
词干要变的动词, 选了没变的形式(du fahrst)才算词形错; 不规则动词选错都算词形错; 其他都是人称错。
人称按最近的对错加权(article_quiz.weights_from), 词干要变的动词多出 du 和 er。
"""
import json
import random
import re

from flask import Blueprint, jsonify, request

import article_quiz as aq
import noun_quiz as nq
from custom_lessons import CHINESE, text
from database import get_db, now_str
from gender_hint import short_meaning
from helpers import current_user_id, err, json_body, login_required
from lessons import find_word
from today import local_day, read_tz
from verb_sentences import WRITTEN
from vocab import book_filter, current_book, query

bp = Blueprint("verb_quiz", __name__)

ROUTE = "<any(verbs, perfekt):which>"
IS_VERB = "w.gender = '' AND w.forms LIKE '%\"praesens\"%' AND w.german NOT LIKE '% %'"
PERSONS = ["ich", "du", "er / sie / es", "wir", "ihr", "sie / Sie"]
SHORT_SUBJECT = ["ich", "du", "er", "wir", "ihr", "Sie"]     # 短题的主语; 第三人称单数一律用 er
ENDINGS = ["-e", "-st", "-t", "-en", "-t", "-en"]
IRREGULAR = ("sein", "haben", "werden", "wissen")           # 词尾看得出来的情态动词不用写在这里
FOCUS = 3             # 词干要变的动词, du 和 er 的权重放大几倍
RECENT_ANSWERS = 500
LETTERS = nq.LETTERS
FORM = re.compile(rf"[{LETTERS}]+( [{LETTERS}]+)?")
TOKEN = re.compile(rf"[{LETTERS}]+")
NOT_SIMPLE = re.compile(r"[\"„“”()/:–-]")
PARTICLES = {"ab", "an", "auf", "aus", "bei", "ein", "fest", "her", "hin", "los", "mit", "nach", "um", "vor", "vorbei",
             "weg", "zu", "zurück", "zusammen"}


def full_ich(ich, wir):
    """词库(维基词典)不少 ich 形式是口语省略 e 的写法: mein → meine, feier → feiere, sammel → sammle"""
    if wir.endswith("eln") and ich == wir[:-1]:
        return wir[:-3] + "le"
    if ich == (wir[:-1] if wir.endswith("ern") else wir[:-2]):
        return ich + "e"
    return ich


def verb_info(row):
    """词库的现在时变位整理好; 数据不完整时返回 None"""
    forms = (json.loads(row["forms"]) if row["forms"] else {}).get("praesens") or []
    if len(forms) != 6 or not all(isinstance(f, str) and FORM.fullmatch(f) for f in forms):
        return None
    german = row["german"].lower()
    heads = [f.split()[0] for f in forms]
    modal = heads[0] == heads[2]         # ich 和 er 一样: 情态动词, ich soll 不缺 e
    if not modal:
        heads[0] = full_ich(heads[0], heads[3])
    irregular = german.endswith(IRREGULAR) or modal
    return {"heads": heads, "particle": forms[0].split()[1] if " " in forms[0] else "", "irregular": irregular,
            "changes": not irregular and heads[2] != heads[4]}


def regular_du(ihr):
    """词干不变时 du 的形式: fahrt → fahrst, lest → lest, haltet → haltest"""
    stem = ihr[:-1]
    return stem + ("t" if stem.endswith(("s", "ß", "z", "x")) else "st")


def stem_picks(v, person):
    """选了这些 = 词形没记住; 选别的是人称用错了"""
    if v["irregular"]:
        return [h for h in dict.fromkeys(v["heads"]) if h != v["heads"][person]]
    if not v["changes"]:
        return []
    return {1: [regular_du(v["heads"][4])], 2: [v["heads"][4]]}.get(person, [])


def explain(row, v, person):
    german, heads, form = row["german"], v["heads"], v["heads"][person]
    if v["irregular"]:
        why = f"{german} 不规则，要单独记：ich {heads[0]}, du {heads[1]}, er {heads[2]}"
    elif v["changes"] and person in (1, 2):
        why = f"{german} 在 du 和 er / sie / es 时词干要变：du {heads[1]}, er {heads[2]}"
    elif v["changes"]:
        why = f"{german} 的词干只在 du 和 er / sie / es 时变，{PERSONS[person]} → {form}"
    else:
        end = ENDINGS[person]
        if person in (3, 5) and not form.endswith("en"):
            end = "-n"
        elif person == 1 and not form.endswith("st"):
            end = "-t"
        extra = "，词尾前加 e 方便发音" if person in (1, 2, 4) and form.endswith(("et", "est")) else ""
        why = f"{PERSONS[person]} 的词尾是 {end}{extra} → {form}"
    return why + (f"；可分动词：前缀 {v['particle']} 放句末" if v["particle"] else "")


def question(row, v, person, prompt, zh, source, fill=None, short=False):
    answer = v["heads"][person]
    picks = stem_picks(v, person)
    others = [h for h in dict.fromkeys(v["heads"]) if h != answer and h not in picks]
    wrong = random.sample(picks, len(picks)) + random.sample(others, len(others))
    note = " · du 和 er 词干要变" if v["changes"] else " · 不规则" if v["irregular"] else ""
    return {"word_id": row["id"], "german": row["german"], "meaning": row["meaning"], "prompt": prompt, "answer": answer,
            "fill": fill or (answer.capitalize() if prompt.startswith("___") else answer), "options": [answer] + wrong[:3],
            "explain": explain(row, v, person), "zh": zh, "source": source, "must": f"（{row['german']}）",
            "hint": f"{row['german']} · {PERSONS[person]}{note}", "person": person, "verb": True, "stem_picks": picks,
            "short": short}


def person_of(tokens, lows, i, v, participle):
    """第 i 个词是这个动词的变位时, 句子能确定是第几人称吗。确定不了返回 None:
    sie / Sie 做主语分不清人称; 第三人称复数只看名词主语也判断不了, 所以不用"""
    word = lows[i]
    fits = [p for p in range(6) if v["heads"][p] == word]
    near = {lows[i - 1] if i else "", lows[i + 1] if i + 1 < len(lows) else ""}
    if 3 in fits and i >= 2 and lows[i - 1] == "wir" and lows[i + 1:i + 2] != ["wir"]:
        return None                      # können wir faulenzen: 这里是不定式, 不是 wir 的变位
    for p, subject in ((0, "ich"), (1, "du"), (3, "wir"), (4, "ihr")):
        if p in fits and subject in near:
            return p
    if 5 in fits and i + 1 < len(tokens) and tokens[i + 1] == "Sie":
        return 5
    if 2 in fits and word != participle and "ihr" not in lows and "sie" not in near:
        return 2
    return None


def example_sentences(row, v):
    """真实例句里的变位; 只用陈述句和问句, 祈使句的动词形式另有规则"""
    forms = json.loads(row["forms"])
    past = forms.get("past") or []
    participle = past[1].split()[-1].lower() if len(past) == 2 and past[1] else ""
    details = json.loads(row["details"]) if row["details"] else {}
    out = []
    for raw in [row["example"]] + list(details.get("examples") or []):
        lines = [x.strip() for x in (raw or "").split("\n") if x.strip()]
        if len(lines) != 2 or CHINESE.search(lines[0]) or not CHINESE.search(lines[1]) or NOT_SIMPLE.search(lines[0]):
            continue
        de, zh = lines
        matches = list(TOKEN.finditer(de))
        tokens = [m.group() for m in matches]
        lows = [t.lower() for t in tokens]
        if not 3 <= len(tokens) <= 14 or de.endswith("!") or "bitte" in lows:
            continue
        if (lows[-1] != v["particle"]) if v["particle"] else (lows[-1] in PARTICLES):
            continue                     # 可分动词要有句末的前缀; holt … ab 不是 holen 的例句
        for i, m in enumerate(matches):
            if lows[i] not in v["heads"] or lows.count(lows[i]) != 1:
                continue
            if tokens[i] != lows[i] and i:           # 句中大写的是名词
                continue
            person = person_of(tokens, lows, i, v, participle)
            if person is None or (person == 2 and i == 0 and not de.endswith("?")):
                continue                 # 句首的 -t 陈述句是祈使句
            out.append((person, de[:m.start()] + "___" + de[m.end():], zh, m.group(), "example"))
            break
    return out


def make_question(row, weights):
    v = verb_info(row)
    if not v:
        return None
    weight = {p: weights[p] * (FOCUS if (v["changes"] or v["irregular"]) and p in (1, 2) else 1) for p in range(6)}
    pool = [(p, prompt, zh, None, "written") for p, prompt, zh in WRITTEN.get(row["german"], [])]
    pool += example_sentences(row, v)
    if pool:
        person, prompt, zh, fill, source = random.choices(pool, [weight[x[0]] for x in pool])[0]
        return question(row, v, person, prompt, zh, source, fill)
    person = random.choices(range(6), [weight[p] for p in range(6)])[0]
    tail = " " + v["particle"] if v["particle"] else ""
    return question(row, v, person, f"{SHORT_SUBJECT[person]} ___{tail}", short_meaning(row["meaning"]) or row["meaning"],
                    "template", short=True)


def make_round(rows, n, weights, make=make_question):
    out = []
    for r in rows:
        if len(out) >= n:
            break
        q = make(r, weights)
        if q:
            out.append(q)
    return out


# 现在时和完成时是两种能力, 记录分开存, 接口结构一样。完成时在 perfekt_quiz.py 里登记
# kinds = 前端能传的错因, 其中 person 不改记忆状态, 其他算忘了
KINDS = {"verbs": {"tense": "praesens", "practice": "verb_practice", "list": "verb_list", "kinds": ("stem", "person"),
                   "make": make_question}}


def marks(cfg):
    """练习记录和手动加的词; 别名和定冠词一样, 错题本和“最容易忘”的条件才能共用"""
    return (f"LEFT JOIN {cfg['practice']} np ON np.word_id = w.id AND np.user_id = :uid "
            f"LEFT JOIN {cfg['list']} nl ON nl.word_id = w.id AND nl.user_id = :uid")


def person_weights(uid, tense):
    rows = get_db().execute("SELECT person, ok FROM verb_answers WHERE user_id = ? AND tense = ? AND person IS NOT NULL "
                            "ORDER BY id DESC LIMIT ?", (uid, tense, RECENT_ANSWERS)).fetchall()
    return aq.weights_from([tuple(r) for r in rows], range(6))


@bp.route(f"/api/grammar/{ROUTE}")
@login_required
def verbs(which):
    """?scope=单词书或 wrong&n=14: 一组题, 每个动词最多一题。不带 scope 时用当前单词书。选词规则同定冠词"""
    cfg = KINDS[which]
    uid = current_user_id()
    scope = request.args.get("scope") or current_book(uid)
    if scope not in nq.SCOPES:
        return err("范围无效")
    try:
        n = min(max(int(request.args.get("n", "14")), 1), nq.MAX_ROUND)
    except ValueError:
        return err("题数无效")
    weights = person_weights(uid, cfg["tense"])
    make = cfg["make"]
    base = ("SELECT w.id, w.german, w.meaning, w.example, w.forms, d.details FROM my_words w {join} "
            f"LEFT JOIN word_details d ON d.word_id = w.id {marks(cfg)} "
            f"LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid WHERE {IS_VERB} {{where}}")
    now = now_str()
    if scope == "wrong":
        rows = query(base.format(join="", where=nq.IN_WRONG) + f" ORDER BY {nq.RISK} LIMIT :pool", pool=nq.POOL, now=now).fetchall()
        questions = make_round(rows, n, weights, make)
        random.shuffle(questions)
        return jsonify({"questions": questions})
    join, args, order = book_filter(scope)
    end = local_day(read_tz())[2]
    def rows(where, tail):
        return query(base.format(join=join, where=where) + f" ORDER BY {tail} LIMIT :pool",
                     pool=nq.POOL, now=now, end=end, **args).fetchall()
    due = rows("AND np.word_id IS NOT NULL AND (np.next_review IS NULL OR np.next_review < :end)", nq.RISK)
    new = rows("AND np.word_id IS NULL", f"p.word_id IS NULL, {order}")
    spare = rows("AND np.next_review >= :end", nq.RISK)
    fresh = sorted(make_round(new, nq.POOL, weights, make), key=lambda q: q["short"])      # 新词里有句子的先出
    return jsonify({"questions": nq.pick_round(make_round(due, n, weights, make), fresh,
                                               make_round(spare, n, weights, make), n)})


@bp.route(f"/api/grammar/{ROUTE}/books")
@login_required
def verb_books(which):
    """练习范围, 格式同 /api/grammar/nouns/books(前端共用), nouns = 这本书的动词数"""
    join_marks = marks(KINDS[which])
    counts = ("COUNT(*) AS nouns, COUNT(np.word_id) AS practiced, "
              f"COALESCE(SUM(CASE WHEN 1 {nq.IN_WRONG} THEN 1 ELSE 0 END), 0) AS weak, "
              "COALESCE(SUM(np.stability >= :master), 0) AS mastered")
    by = {}
    for table_name, key in (("word_levels", "level"), ("word_books", "book")):
        for r in query(f"SELECT l.{key} AS book, {counts} FROM my_words w JOIN {table_name} l ON l.word_id = w.id "
                       f"{join_marks} WHERE {IS_VERB} GROUP BY l.{key}", master=nq.MASTER_S).fetchall():
            by[r["book"]] = dict(r)
    whole = query(f"SELECT {counts} FROM my_words w {join_marks} WHERE {IS_VERB}", master=nq.MASTER_S).fetchone()
    by["all"] = {**dict(whole), "book": "all"}
    return jsonify({"current": current_book(current_user_id()), "wrong": whole["weak"],
                    "books": [by[b] for b in nq.BOOKS if b in by]})


@bp.route(f"/api/grammar/{ROUTE}/words")
@login_required
def verb_words(which):
    """查看一个范围里的动词 ?scope=&page=: 带练习记录, manual = 手动加进错题本的"""
    scope = request.args.get("scope", "")
    if scope not in nq.SCOPES:
        return err("范围无效")
    try:
        page = max(int(request.args.get("page", "1")), 1)
    except ValueError:
        return err("页码无效")
    if scope == "wrong":
        join, where, args, order = "", nq.IN_WRONG, {}, "np.last_at DESC, w.german"
    else:
        join, args, order = book_filter(scope)
        where = ""
    source = f"FROM my_words w {join} {marks(KINDS[which])} WHERE {IS_VERB} {where}"
    total = query(f"SELECT COUNT(*) {source}", **args).fetchone()[0]
    rows = query(
        "SELECT w.id, w.german, w.gender, w.meaning, COALESCE(np.wrong, 0) AS wrong, COALESCE(np.streak, 0) AS streak, "
        f"nl.word_id IS NOT NULL AS manual {source} ORDER BY {order} LIMIT :lim OFFSET :off",
        lim=nq.PAGE_SIZE, off=(page - 1) * nq.PAGE_SIZE, **args,
    ).fetchall()
    return jsonify({"words": [{**dict(r), "manual": bool(r["manual"])} for r in rows], "total": total, "page": page,
                    "pages": max((total + nq.PAGE_SIZE - 1) // nq.PAGE_SIZE, 1)})


@bp.route(f"/api/grammar/{ROUTE}/result", methods=["POST"])
@login_required
def result(which):
    """记一次作答 {word_id, ok, person, kind, hinted}: 只记每组第一次作答, 不影响今日学习。kind 见 KINDS"""
    cfg = KINDS[which]
    data = json_body()
    word_id, ok = (data.get("word_id"), data.get("ok")) if data else (None, None)
    if isinstance(word_id, bool) or not isinstance(word_id, int) or not isinstance(ok, bool):
        return err("参数无效")
    if query("SELECT 1 FROM all_my_words WHERE id = :id", id=word_id).fetchone() is None:
        return err("单词不存在", 404)
    person, kind = data.get("person"), data.get("kind")
    person = person if person in range(6) and not isinstance(person, bool) else None
    kind = kind if isinstance(kind, str) and kind in cfg["kinds"] and not ok else None
    if data.get("hinted") is True or kind == "person":
        rating = None
    else:
        rating = 3 if ok else 1
    db = get_db()
    uid = current_user_id()
    nq.update_practice(db, uid, word_id, rating, cfg["practice"])
    db.execute("INSERT INTO verb_answers (user_id, word_id, tense, person, ok, kind, answered_at) VALUES (?,?,?,?,?,?,?)",
               (uid, word_id, cfg["tense"], person, ok, kind, now_str()))
    db.commit()
    return jsonify({"ok": True})


@bp.route(f"/api/grammar/{ROUTE}/list", methods=["POST"])
@login_required
def add_verbs(which):
    """加入错题本 {text: "fahren, geben"}: 逗号、空格或换行分隔, 变化形式也能找到原形。返回 added / skipped / missing"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    names = [x for x in re.split(r"[,，;；、\s]+", text(data.get("text"), 3000)) if x]
    if not names:
        return err("请输入要加入的动词")
    ids, missing = [], []
    for name in names[:100]:
        hit = find_word(name)
        if hit and query(f"SELECT 1 FROM my_words w WHERE w.id = :id AND {IS_VERB}", id=hit["id"]).fetchone():
            ids.append(hit["id"])
        else:
            missing.append(name)
    db = get_db()
    added = 0
    for word_id in dict.fromkeys(ids):
        added += db.execute(f"INSERT OR IGNORE INTO {KINDS[which]['list']} (user_id, word_id, added_at) VALUES (?,?,?)",
                            (current_user_id(), word_id, now_str())).rowcount
    db.commit()
    return jsonify({"added": added, "skipped": len(set(ids)) - added, "missing": missing})


@bp.route(f"/api/grammar/{ROUTE}/list/<int:word_id>", methods=["DELETE"])
@login_required
def remove_verb(which, word_id):
    """移出错题本: 手动加的删掉, 错过的记录清零; 练过几次还留着"""
    db = get_db()
    cfg = KINDS[which]
    db.execute(f"DELETE FROM {cfg['list']} WHERE user_id = ? AND word_id = ?", (current_user_id(), word_id))
    db.execute(f"UPDATE {cfg['practice']} SET wrong = 0, streak = 0, weak = 0 WHERE user_id = ? AND word_id = ?",
               (current_user_id(), word_id))
    db.commit()
    return jsonify({"ok": True})
