"""定冠词填空题: 从单词书或错题本的名词出题, 不用 AI

每个名词的句子优先级: 手写句子(grammar_questions, 提示开头的名词对得上) > 真实例句(把名词前的冠词挖空) >
通用句型 + 词库的变格表。不是每个名词都有例句, 但几乎都有变格表, 所以能覆盖全部名词。
没有变格表的词(如自己加的词)只考第一格。
单复数同形的词不用例句出题(填 den 和 die 都说得通); 通用句型会写明单数还是复数。
练习记录在 noun_practice: 出题时优先错过的词, 其次没练过的, 再次很久没练的, 减少重复。
错题本 = 错过的词(连续答对 3 次自动移出) + 用户手动加的词(noun_list, 手动移除才走)。
"""
import collections
import json
import random
import re

from flask import Blueprint, jsonify, request

from auth import admin_required
from custom_lessons import CHINESE, text
from database import get_db, now_str
from dictionary import all_glossary
from gender_hint import short_meaning
from grammar import HINT_NOUN
from helpers import current_user_id, err, json_body, login_required
from lessons import find_word
from today import local_day, read_tz
from vocab import BOOKS, book_filter, current_book, query
from word_store import word_id_for

bp = Blueprint("noun_quiz", __name__)

OPTIONS = ["der", "die", "das", "den", "dem", "des"]
SCOPES = BOOKS + ["wrong"]
STREAK_DONE = 3       # 错过的词连续答对几次后移出错题本
POOL = 60             # 一次取多少个词来出题
MAX_ROUND = 30
PAGE_SIZE = 100       # 查看单词时一页多少个
MASTER_DAYS = 3       # 连续几天答对算已掌握
CASE_IN_TEXT = re.compile("第([一二三四])格")
# 练习记录和手动加的词; 下面的查询都带这两张表, 错题本的条件要用到
MARKS = ("LEFT JOIN noun_practice np ON np.word_id = w.id AND np.user_id = :uid "
         "LEFT JOIN noun_list nl ON nl.word_id = w.id AND nl.user_id = :uid")
IN_WRONG = "AND ((np.wrong > 0 AND np.streak < :done) OR nl.word_id IS NOT NULL)"
GENDER_ZH = {"der": "阳性", "die": "阴性", "das": "中性"}
CASE_NAMES = ["第一格", "第二格", "第三格", "第四格"]
# 通用句型, 下标同 forms 里的格(一、二、三、四格): (单数句子, 复数句子, 解释, 单数翻译, 复数翻译)。几乎任何名词都说得通
FRAMES = [
    ("Das ist {x}.", "Das sind {x}.", "Das ist / sind … 后面是第一格", "这是{m}。", "这些是{m}。"),
    ("Wir kommen wegen {x}.", "Wir kommen wegen {x}.", "wegen + 第二格", "我们是因为{m}来的。", "我们是因为这些{m}来的。"),
    ("Wir sprechen von {x}.", "Wir sprechen von {x}.", "von + 第三格", "我们在说{m}。", "我们在说这些{m}。"),
    ("Wir sprechen über {x}.", "Wir sprechen über {x}.", "über + 第四格", "我们在谈论{m}。", "我们在谈论这些{m}。"),
]
LETTERS = "A-Za-zÄÖÜäöüß"
ARTICLE_NOUN = re.compile(rf"(?<![{LETTERS}])(der|die|das|den|dem|des|Der|Die|Das|Den|Dem|Des) ([{LETTERS}-]+)")


def split_form(form):
    """'des Mannes / des Manns' → ('des', 'Mannes'); 不是「冠词 + 名词」时返回 None"""
    parts = (form or "").split(" / ")[0].split()
    return (parts[0], parts[1]) if len(parts) == 2 and parts[0] in OPTIONS else None


def table(row):
    """变格表 → [(单复数, 第几格, 冠词, 名词)]; 数据有问题(冠词和词性对不上)时返回空
    没有变格表的词只给单数第一格: 其他格的名词可能变形(den Kunden), 不能猜"""
    cases = (json.loads(row["forms"]) if row["forms"] else {}).get("cases") or {}
    sg, pl = cases.get("sg") or [], cases.get("pl") or []
    if not sg:
        return [("单数", 0, row["gender"], row["german"])] if row["german"].isalpha() else []
    if len(sg) != 4 or (split_form(sg[0]) or (None,))[0] != row["gender"]:
        return []
    out = [("单数", i, *split_form(f)) for i, f in enumerate(sg) if split_form(f)]
    if len(pl) == 4:
        out += [("复数", i, *split_form(f)) for i, f in enumerate(pl) if split_form(f)]
    return out


def base_question(row, prompt, answer, number, explain, zh, source, case_no, fill=None):
    gender = row["gender"]
    return {"word_id": row["id"], "meaning": row["meaning"], "prompt": prompt, "answer": answer, "fill": fill or answer,
            "options": OPTIONS, "fixed": True, "explain": explain, "zh": zh, "source": source,
            "must": number, "case": case_no, "hint": f"{gender} {row['german']} · {GENDER_ZH[gender]} · {number}"}


def example_question(row, forms):
    """真实例句: 冠词紧挨名词, 而且能在变格表里查到是第几格。查不到的不出题"""
    singular = {n for num, _i, _a, n in forms if num == "单数"}
    if row["german"] in {n for num, _i, _a, n in forms if num == "复数"} and row["german"] in singular:
        return None           # 单复数同形
    details = json.loads(row["details"]) if row["details"] else {}
    texts = [row["example"]] + list(details.get("examples") or [])
    random.shuffle(texts)
    for raw in texts:
        lines = [x.strip() for x in (raw or "").split("\n") if x.strip()]
        if len(lines) != 2 or CHINESE.search(lines[0]) or not CHINESE.search(lines[1]):
            continue
        de, zh = lines
        for m in ARTICLE_NOUN.finditer(de):
            art, noun = m.group(1).lower(), m.group(2)
            hits = [(num, i) for num, i, a, n in forms if a == art and n == noun]
            if not hits or de.count(m.group(0)) != 1:
                continue
            number = hits[0][0]
            cases = [i for num, i in hits if num == number]
            where = "或".join(CASE_NAMES[i] for i in cases)
            return base_question(row, de[:m.start()] + "___" + de[m.start() + len(m.group(1)):], art, number,
                                 f"这里是{number}{where} → {art}", zh, "example", cases[0] if len(cases) == 1 else None,
                                 m.group(1))
    return None


def template_question(row, forms):
    """通用句型; 单数多出一些, 第二格少出一些"""
    weights = [(4 if num == "单数" else 2) * (1 if i == 1 else 3) for num, i, _a, _n in forms]
    number, i, art, noun = random.choices(forms, weights)[0]
    plural = number != "单数"
    frame = FRAMES[i][1 if plural else 0].format(x="___ " + noun)
    zh = FRAMES[i][4 if plural else 3].format(m=short_meaning(row["meaning"]) or row["meaning"])
    return base_question(row, frame, art, number, f"{FRAMES[i][2]}；{number} → {art}", zh, "template", i)


def written_questions():
    """手写句子按名词分组: {(冠词, 名词原形): [题, ...]}"""
    rows = get_db().execute(
        "SELECT id, prompt, answer, hint, explain, zh, source FROM grammar_questions "
        "WHERE topic = 'art-def' AND status = 'active'",
    ).fetchall()
    out = collections.defaultdict(list)
    for r in rows:
        m = HINT_NOUN.match(r["hint"])
        if m:
            out[m.groups()].append(r)
    return out


def written_case(explain):
    """手写题的解释里写着第几格; 没写就不计入统计"""
    m = CASE_IN_TEXT.search(explain)
    return "一二三四".index(m.group(1)) if m else None


def written_question(row, q):
    """id 让报错记到这道手写题上, word_id 让作答记到这个词上"""
    fill = q["answer"].capitalize() if q["prompt"].startswith("___") else q["answer"]
    return {"id": q["id"], "word_id": row["id"], "meaning": row["meaning"], "prompt": q["prompt"], "answer": q["answer"],
            "fill": fill, "options": OPTIONS, "fixed": True, "explain": q["explain"], "zh": q["zh"],
            "source": q["source"], "must": "复数" if "复数" in q["hint"] else "单数", "hint": q["hint"],
            "case": written_case(q["explain"])}


def make_question(row, written=None):
    hits = (written or {}).get((row["gender"], row["german"]))
    if hits:
        return written_question(row, random.choice(hits))
    forms = table(row)
    if not forms:
        return None
    return example_question(row, forms) or template_question(row, forms)


def make_round(rows, n, written=None):
    out = []
    for r in rows:
        if len(out) >= n:
            break
        q = make_question(r, written)
        if q:
            out.append(q)
    return out


@bp.route("/api/grammar/nouns")
@login_required
def nouns():
    """?scope=单词书或 wrong&n=14: 一组定冠词题, 每个词最多一题。不带 scope 时用当前单词书"""
    scope = request.args.get("scope") or current_book(current_user_id())
    if scope not in SCOPES:
        return err("范围无效")
    try:
        n = min(max(int(request.args.get("n", "14")), 1), MAX_ROUND)
    except ValueError:
        return err("题数无效")
    if scope == "wrong":
        join, where, args = "", IN_WRONG, {}
    else:
        join, args, _order = book_filter(scope)
        where = ""
    # 错过的词 > 没练过的 > 很久没练的; 同一档随机
    rows = query(
        f"SELECT w.id, w.german, w.gender, w.meaning, w.example, w.forms, d.details FROM my_words w {join} "
        f"LEFT JOIN word_details d ON d.word_id = w.id {MARKS} WHERE w.gender != '' {where} "
        "ORDER BY CASE WHEN np.wrong > 0 AND np.streak < :done THEN 0 WHEN np.word_id IS NULL THEN 1 ELSE 2 END, "
        "np.last_at, RANDOM() LIMIT :pool",
        pool=POOL, done=STREAK_DONE, **args,
    ).fetchall()
    return jsonify({"questions": make_round(rows, n, written_questions())})


@bp.route("/api/grammar/nouns/books")
@login_required
def noun_books():
    """练习范围: 各单词书的名词数和进度(没有名词的书不列出来)、错题本的词数、当前单词书。
    practiced = 练过的名词, weak = 还在错题本里的, mastered = 连续 3 天答对的。和今日学习的进度是两回事"""
    counts = ("COUNT(*) AS nouns, COUNT(np.word_id) AS practiced, "
              f"COALESCE(SUM(CASE WHEN 1 {IN_WRONG} THEN 1 ELSE 0 END), 0) AS weak, "
              "COALESCE(SUM(np.good_days >= :days), 0) AS mastered")
    by = {}
    for table_name, key in (("word_levels", "level"), ("word_books", "book")):
        for r in query(f"SELECT l.{key} AS book, {counts} FROM my_words w JOIN {table_name} l ON l.word_id = w.id "
                       f"{MARKS} WHERE w.gender != '' GROUP BY l.{key}", done=STREAK_DONE, days=MASTER_DAYS).fetchall():
            by[r["book"]] = dict(r)
    whole = query(f"SELECT {counts} FROM my_words w {MARKS} WHERE w.gender != ''", done=STREAK_DONE,
                  days=MASTER_DAYS).fetchone()
    by["all"] = {**dict(whole), "book": "all"}
    return jsonify({"current": current_book(current_user_id()), "wrong": whole["weak"],
                    "books": [by[b] for b in BOOKS if b in by]})


@bp.route("/api/grammar/nouns/words")
@login_required
def noun_words():
    """查看一个范围里的名词 ?scope=&page=: words 带练习记录, manual = 手动加进错题本的"""
    scope = request.args.get("scope", "")
    if scope not in SCOPES:
        return err("范围无效")
    try:
        page = max(int(request.args.get("page", "1")), 1)
    except ValueError:
        return err("页码无效")
    if scope == "wrong":
        join, where, args, order = "", IN_WRONG, {}, "np.last_at DESC, w.german"
    else:
        join, args, order = book_filter(scope)
        where = ""
    source = f"FROM my_words w {join} {MARKS} WHERE w.gender != '' {where}"
    total = query(f"SELECT COUNT(*) {source}", done=STREAK_DONE, **args).fetchone()[0]
    rows = query(
        "SELECT w.id, w.german, w.gender, w.meaning, COALESCE(np.wrong, 0) AS wrong, COALESCE(np.streak, 0) AS streak, "
        f"nl.word_id IS NOT NULL AS manual {source} ORDER BY {order} LIMIT :lim OFFSET :off",
        done=STREAK_DONE, lim=PAGE_SIZE, off=(page - 1) * PAGE_SIZE, **args,
    ).fetchall()
    words = [{**dict(r), "manual": bool(r["manual"])} for r in rows]
    return jsonify({"words": words, "total": total, "page": page, "pages": max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)})


@bp.route("/api/grammar/nouns/result", methods=["POST"])
@login_required
def result():
    """记一次作答 {word_id, ok, must, case}: 只记每组第一次作答, 不影响复习计划。?tz= 决定“今天”是哪一天"""
    data = json_body()
    word_id, ok = (data.get("word_id"), data.get("ok")) if data else (None, None)
    if isinstance(word_id, bool) or not isinstance(word_id, int) or not isinstance(ok, bool):
        return err("参数无效")
    if query("SELECT 1 FROM all_my_words WHERE id = :id", id=word_id).fetchone() is None:
        return err("单词不存在", 404)
    db = get_db()
    uid = current_user_id()
    day = local_day(read_tz())[0]
    db.execute(
        "INSERT INTO noun_practice (user_id, word_id, seen, wrong, streak, last_at, good_days, last_good_day) "
        "VALUES (?,?,1,?,?,?,?,?) "
        "ON CONFLICT(user_id, word_id) DO UPDATE SET seen = seen + 1, wrong = wrong + excluded.wrong, "
        "streak = CASE WHEN excluded.wrong = 1 THEN 0 ELSE streak + 1 END, last_at = excluded.last_at, "
        "good_days = CASE WHEN excluded.wrong = 1 THEN 0 WHEN last_good_day = excluded.last_good_day THEN good_days "
        "ELSE good_days + 1 END, last_good_day = excluded.last_good_day",
        (uid, word_id, 0 if ok else 1, 1 if ok else 0, now_str(), 1 if ok else 0, day if ok else ""),
    )
    must, case_no = data.get("must"), data.get("case")
    db.execute(
        "INSERT INTO noun_answers (user_id, word_id, number, case_no, ok, answered_at) VALUES (?,?,?,?,?,?)",
        (uid, word_id, must if must in ("单数", "复数") else None,
         case_no if case_no in (0, 1, 2, 3) and not isinstance(case_no, bool) else None, ok, now_str()),
    )
    db.commit()
    return jsonify({"ok": True})


# ---------- 错题本里手动加的词 ----------
def resolve_noun(name):
    """一个词 → 词库里的名词编号; 自建对话词表里的词加进词库; 找不到返回 None"""
    hit = find_word(name)
    if hit and hit["gender"]:
        return hit["id"]
    key = name.lower()
    for g in all_glossary():
        if g["gender"] and key in (g["german"].lower(), g["plural"].lower()):
            return word_id_for(get_db(), current_user_id(), (g["german"], g["pos"], g["gender"], g["plural"], g["meaning"], ""))
    return None


@bp.route("/api/grammar/nouns/list", methods=["POST"])
@login_required
def add_nouns():
    """加入错题本 {word_id} 或 {text: "Palette, Karton"}: text 用逗号、空格或换行分隔。返回 added / skipped / missing"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    db = get_db()
    uid = current_user_id()
    if "word_id" in data:
        word_id = data["word_id"]
        if isinstance(word_id, bool) or not isinstance(word_id, int):
            return err("单词无效")
        row = query("SELECT gender FROM my_words WHERE id = :id", id=word_id).fetchone()
        if row is None:
            return err("单词不存在", 404)
        if not row["gender"]:
            return err("只能加入名词")
        ids, missing = [word_id], []
    else:
        names = [x for x in re.split(r"[,，;；、\s]+", text(data.get("text"), 3000)) if x and x not in OPTIONS]
        if not names:
            return err("请输入要加入的名词")
        ids, missing = [], []
        for name in names[:100]:
            word_id = resolve_noun(name)
            if word_id:
                ids.append(word_id)
            else:
                missing.append(name)
    added = 0
    for word_id in dict.fromkeys(ids):
        added += db.execute("INSERT OR IGNORE INTO noun_list (user_id, word_id, added_at) VALUES (?,?,?)",
                            (uid, word_id, now_str())).rowcount
    db.commit()
    return jsonify({"added": added, "skipped": len(set(ids)) - added, "missing": missing})


@bp.route("/api/grammar/nouns/list/<int:word_id>", methods=["DELETE"])
@login_required
def remove_noun(word_id):
    """移出错题本: 手动加的删掉, 错过的记录清零; 练过几次还留着"""
    db = get_db()
    db.execute("DELETE FROM noun_list WHERE user_id = ? AND word_id = ?", (current_user_id(), word_id))
    db.execute("UPDATE noun_practice SET wrong = 0, streak = 0 WHERE user_id = ? AND word_id = ?",
               (current_user_id(), word_id))
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/grammar/nouns/report", methods=["POST"])
@login_required
def report():
    """自动出的题没有编号, 报错记在词上 {word_id, prompt, reason}"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    reason, prompt = text(data.get("reason"), 200), text(data.get("prompt"), 200)
    word_id = data.get("word_id")
    if len(reason) < 2:
        return err("请写一下哪里有问题")
    if isinstance(word_id, bool) or not isinstance(word_id, int):
        return err("单词无效")
    if query("SELECT 1 FROM all_my_words WHERE id = :id", id=word_id).fetchone() is None:
        return err("单词不存在", 404)
    db = get_db()
    db.execute(
        "INSERT INTO content_reports (kind, sent_key, reason, reported_by, created_at) VALUES ('noun',?,?,?,?) "
        "ON CONFLICT(kind, sent_key) DO UPDATE SET reason = excluded.reason, "
        "reported_by = excluded.reported_by, created_at = excluded.created_at",
        (str(word_id), f"{prompt}｜{reason}", current_user_id(), now_str()),
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/grammar/nouns/reports")
@admin_required
def reports():
    rows = get_db().execute(
        "SELECT w.id, w.german, r.reason FROM content_reports r JOIN words w ON CAST(r.sent_key AS INTEGER) = w.id "
        "WHERE r.kind = 'noun' ORDER BY r.created_at DESC",
    ).fetchall()
    return jsonify({"reports": [dict(r) for r in rows]})


@bp.route("/api/grammar/nouns/reports/<int:word_id>", methods=["DELETE"])
@admin_required
def clear_report(word_id):
    db = get_db()
    db.execute("DELETE FROM content_reports WHERE kind = 'noun' AND sent_key = ?", (str(word_id),))
    db.commit()
    return jsonify({"ok": True})
