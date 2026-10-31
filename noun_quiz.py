"""定冠词填空题: 从词库的名词自动出题, 不用 AI, 也不用把题存进数据库

优先用真实例句(把名词前的冠词挖空), 没有合适的例句时用通用句型 + 词库的变格表。
不是每个名词都有例句, 但几乎都有变格表, 所以能覆盖全部名词。没有变格表的词(如自己加的词)只考第一格。
单复数同形的词不用例句出题(填 den 和 die 都说得通); 通用句型会写明单数还是复数。
练习记录在 noun_practice: 出题时优先错过的词, 其次没练过的, 再次很久没练的, 减少重复。
"我的词性本"(noun_list)是用户自己挑的词。
"""
import json
import random
import re

from flask import Blueprint, jsonify, request

from auth import admin_required
from custom_lessons import CHINESE, text
from database import get_db, now_str
from dictionary import all_glossary
from helpers import current_user_id, err, json_body, login_required
from lessons import find_word, private_word_id
from vocab import book_filter, current_book, query

bp = Blueprint("noun_quiz", __name__)

OPTIONS = ["der", "die", "das", "den", "dem", "des"]
SCOPES = ("learned", "book", "mine", "wrong", "all")
STREAK_DONE = 3       # 错过的词连续答对几次后不再算“错过的词”
POOL = 60             # 一次取多少个词来出题
MIN_LEARNED = 5       # 学过的词凑出的题少于这个数时, 用当前单词书补
MAX_ROUND = 30
GENDER_ZH = {"der": "阳性", "die": "阴性", "das": "中性"}
CASE_NAMES = ["第一格", "第二格", "第三格", "第四格"]
# 通用句型, 下标同 forms 里的格(一、二、三、四格): (单数句子, 复数句子, 解释)。几乎任何名词都说得通
FRAMES = [
    ("Das ist {x}.", "Das sind {x}.", "Das ist / sind … 后面是第一格"),
    ("Wir kommen wegen {x}.", "Wir kommen wegen {x}.", "wegen + 第二格"),
    ("Wir sprechen von {x}.", "Wir sprechen von {x}.", "von + 第三格"),
    ("Wir sprechen über {x}.", "Wir sprechen über {x}.", "über + 第四格"),
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


def base_question(row, prompt, answer, number, explain, zh, source, fill=None):
    gender = row["gender"]
    return {"word_id": row["id"], "meaning": row["meaning"], "prompt": prompt, "answer": answer, "fill": fill or answer,
            "options": OPTIONS, "fixed": True, "explain": explain, "zh": zh, "source": source,
            "must": number, "hint": f"{gender} {row['german']} · {GENDER_ZH[gender]} · {number}"}


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
            where = "或".join(CASE_NAMES[i] for num, i in hits if num == number)
            return base_question(row, de[:m.start()] + "___" + de[m.start() + len(m.group(1)):], art, number,
                                 f"这里是{number}{where} → {art}", zh, "example", m.group(1))
    return None


def template_question(row, forms):
    """通用句型; 单数多出一些, 第二格少出一些"""
    weights = [(4 if num == "单数" else 2) * (1 if i == 1 else 3) for num, i, _a, _n in forms]
    number, i, art, noun = random.choices(forms, weights)[0]
    frame = FRAMES[i][0 if number == "单数" else 1].format(x="___ " + noun)
    return base_question(row, frame, art, number, f"{FRAMES[i][2]}；{number} → {art}",
                         f"{noun}：{row['meaning']}", "template")


def make_question(row):
    forms = table(row)
    if not forms:
        return None
    return example_question(row, forms) or template_question(row, forms)


def make_round(rows, seen, n):
    out = []
    for r in rows:
        if len(out) >= n:
            break
        q = make_question(r) if r["id"] not in seen else None
        if q:
            seen.add(r["id"])
            out.append(q)
    return out


@bp.route("/api/grammar/nouns")
@login_required
def nouns():
    """?scope=learned|book|mine|wrong|all&n=14: 一组定冠词题, 每个词最多一题。
    学过的词太少时用当前单词书补; 我的词性本和错过的词不补, 没有就是没有"""
    scope = request.args.get("scope", "book")
    if scope not in SCOPES:
        return err("范围无效")
    try:
        n = min(max(int(request.args.get("n", "14")), 1), MAX_ROUND)
    except ValueError:
        return err("题数无效")
    cols = "w.id, w.german, w.gender, w.meaning, w.example, w.forms, d.details"
    details = ("LEFT JOIN word_details d ON d.word_id = w.id "
               "LEFT JOIN noun_practice np ON np.word_id = w.id AND np.user_id = :uid")
    book_join, book_args, _order = book_filter(current_book(current_user_id()))

    def pick(join, where="", **args):
        # 错过的词 > 没练过的 > 很久没练的; 同一档随机
        return query(
            f"SELECT {cols} FROM my_words w {join} {details} WHERE w.gender != '' {where} "
            "ORDER BY CASE WHEN np.wrong > 0 AND np.streak < :done THEN 0 WHEN np.word_id IS NULL THEN 1 ELSE 2 END, "
            "np.last_at, RANDOM() LIMIT :pool",
            pool=POOL, done=STREAK_DONE, **args,
        ).fetchall()

    seen = set()
    if scope == "learned":
        out = make_round(pick("JOIN progress p ON p.word_id = w.id AND p.user_id = :uid"), seen, n)
        if len(out) < MIN_LEARNED:
            out += make_round(pick(book_join, **book_args), seen, n - len(out))
    elif scope == "book":
        out = make_round(pick(book_join, **book_args), seen, n)
    elif scope == "mine":
        out = make_round(pick("JOIN noun_list nl ON nl.word_id = w.id AND nl.user_id = :uid"), seen, n)
    elif scope == "wrong":
        out = make_round(pick("", "AND np.wrong > 0 AND np.streak < :done"), seen, n)
    else:
        out = make_round(pick(""), seen, n)
    return jsonify({"questions": out})


@bp.route("/api/grammar/nouns/result", methods=["POST"])
@login_required
def result():
    """记一次作答 {word_id, ok}: 只记每组第一次作答, 不影响复习计划"""
    data = json_body()
    word_id, ok = (data.get("word_id"), data.get("ok")) if data else (None, None)
    if isinstance(word_id, bool) or not isinstance(word_id, int) or not isinstance(ok, bool):
        return err("参数无效")
    if query("SELECT 1 FROM all_my_words WHERE id = :id", id=word_id).fetchone() is None:
        return err("单词不存在", 404)
    db = get_db()
    db.execute(
        "INSERT INTO noun_practice (user_id, word_id, seen, wrong, streak, last_at) VALUES (?,?,1,?,?,?) "
        "ON CONFLICT(user_id, word_id) DO UPDATE SET seen = seen + 1, wrong = wrong + excluded.wrong, "
        "streak = CASE WHEN excluded.wrong = 1 THEN 0 ELSE streak + 1 END, last_at = excluded.last_at",
        (current_user_id(), word_id, 0 if ok else 1, 1 if ok else 0, now_str()),
    )
    db.commit()
    return jsonify({"ok": True})


# ---------- 我的词性本 ----------
@bp.route("/api/grammar/nouns/list")
@login_required
def list_nouns():
    rows = query(
        "SELECT w.id, w.german, w.gender, w.meaning FROM noun_list nl JOIN my_words w ON w.id = nl.word_id "
        "WHERE nl.user_id = :uid AND w.gender != '' ORDER BY nl.added_at DESC, w.german",
    ).fetchall()
    return jsonify({"words": [dict(r) for r in rows]})


def resolve_noun(name):
    """一个词 → 词库里的名词编号; 情景课的仓储词加成私有词; 找不到返回 None"""
    hit = find_word(name)
    if hit and hit["gender"]:
        return hit["id"]
    key = name.lower()
    for g in all_glossary():
        if g["gender"] and key in (g["german"].lower(), g["plural"].lower()):
            return private_word_id((g["german"], g["pos"], g["gender"], g["plural"], g["meaning"], ""))
    return None


@bp.route("/api/grammar/nouns/list", methods=["POST"])
@login_required
def add_nouns():
    """加入词性本 {word_id} 或 {text: "Palette, Karton"}: text 用逗号、空格或换行分隔。返回 added / skipped / missing"""
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
    db = get_db()
    db.execute("DELETE FROM noun_list WHERE user_id = ? AND word_id = ?", (current_user_id(), word_id))
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
