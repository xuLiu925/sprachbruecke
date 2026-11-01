"""复数练习: 从单词书或错题本出题, 看单数写复数, 不用 AI, 不影响复习计划

结构和定冠词练习(noun_quiz.py)一样, 但能力不同, 记录分开存:
练习记录在 plural_practice: 出题时优先错过的词, 其次没练过的, 再次很久没练的。
错题本 = 错过的词(连续答对 3 次自动移出) + 用户手动加的词(plural_list, 手动移除才走)。
已掌握 = 连续 3 个不同的日子答对。
每题带这个词符合哪条规律; 规律内容和前端的速查表(plural-rules.js)要保持一致。
"""
import re

from flask import Blueprint, jsonify, request

from custom_lessons import text
from database import get_db, now_str
from form_drills import question
from helpers import current_user_id, err, json_body, login_required
from noun_quiz import OPTIONS, PAGE_SIZE, POOL, resolve_noun
from today import local_day, read_tz
from vocab import BOOKS, book_filter, current_book, query

bp = Blueprint("plural_quiz", __name__)

SCOPES = BOOKS + ["wrong"]
ROUND_SIZE = 10
STREAK_DONE = 3       # 错过的词连续答对几次后移出错题本
MASTER_DAYS = 3       # 连续几天答对算已掌握
HAS_PLURAL = "w.gender != '' AND w.plural != '' AND w.plural NOT GLOB '*[^A-Za-zÄÖÜäöüßé-]*'"   # 挡掉 Poulets(CH) 这类数据; é 是 Cafés
MARKS = ("LEFT JOIN plural_practice pp ON pp.word_id = w.id AND pp.user_id = :uid "
         "LEFT JOIN plural_list pl ON pl.word_id = w.id AND pl.user_id = :uid")
IN_WRONG = "AND ((pp.wrong > 0 AND pp.streak < :done) OR pl.word_id IS NOT NULL)"

UMLAUT = {"Au": "Äu", "au": "äu", "A": "Ä", "a": "ä", "O": "Ö", "o": "ö", "U": "Ü", "u": "ü"}
LAST_VOWEL = re.compile(r"(Au|au|A|a|O|o|U|u)(?=[^AaOoUuÄäÖöÜü]*$)")
UNMARKED = "这个词没有可靠的规律，要单独记"


def umlaut(word):
    """最后一个 a / o / u / au 变音: Apfel → Äpfel, Haus → Häus"""
    return LAST_VOWEL.sub(lambda m: UMLAUT[m.group(1)], word, count=1)


def adds(end):
    return lambda german, plural: plural == german + end


def unchanged(german, plural):
    return plural == german


def maybe_umlaut(german, plural):
    return plural in (german, umlaut(german))


def um_to_en(german, plural):
    return plural == german[:-2] + "en"


# -er / -el / -en 只算弱读词尾: Tier、Spiel、Meer 的 ie / ee 是长元音, 不是这类词。Feier、Schleier 的 ei 不受影响
WEAK = r"(?<![^aeiouäöü][ie])"
# (词性, 词尾的正则, 判断这个词是否符合, 说明); None = 不限词性。按顺序取第一条对得上词尾的规律
RULES = [
    ("die", re.compile(r"(ung|heit|keit|schaft|ion|tät)$"), adds("en"), "阴性词尾 -{e}：加 -en"),
    ("die", re.compile(r"(in)$"), adds("nen"), "阴性词尾 -in：变 -innen"),
    ("die", re.compile(r"(e)$"), adds("n"), "阴性词尾 -e：加 -n"),
    ("die", re.compile(WEAK + r"(el|er)$"), adds("n"), "阴性词尾 -{e}：加 -n"),
    ("das", re.compile(r"(chen|lein)$"), unchanged, "词尾 -{e}：复数不变"),
    (("der", "das"), re.compile(WEAK + r"(er|el|en)$"), maybe_umlaut, "阳性、中性词尾 -{e}：复数不变，部分变音"),
    ("der", re.compile(r"[^e](e)$"), adds("n"), "阳性词尾 -e（多指人或动物）：加 -n"),
    ("der", re.compile(r"(ent|ant|ist|or)$"), adds("en"), "阳性词尾 -{e}（多指人）：大多加 -en"),
    (None, re.compile(r"(nis)$"), adds("se"), "词尾 -nis：变 -nisse"),
    ("das", re.compile(r"(um)$"), um_to_en, "外来词尾 -um：变 -en"),
    (None, re.compile(r"((?<![aeäö])[iu]|o)$"), adds("s"), "词尾 -{e}：大多加 -s"),
    (None, re.compile(r"^([A-ZÄÖÜ]{2,})$"), adds("s"), "缩写词：大多加 -s"),
]


def tendency(german, gender, plural):
    """词尾没有规律时按词性看倾向; 对不上返回空"""
    if gender == "die" and plural in (german + "n", german + "en"):
        return "阴性：大多加 -(e)n"
    if gender == "die" and plural == umlaut(german) + "e":
        return "阴性单音节词：常加 -e 并变音"
    if gender == "der" and plural in (german + "e", umlaut(german) + "e"):
        return "阳性：大多加 -e，常变音"
    if gender == "das" and plural == german + "e":
        return "中性：常加 -e"
    if gender == "das" and plural == umlaut(german) + "er":
        return "中性短词：很多加 -er，能变音的都变音"
    return ""


def plural_rule(german, gender, plural):
    """这个词的规律: {kind, text}; kind = rule 符合词尾规律 / tendency 符合词性倾向 / exception 例外 / none 没有规律"""
    for genders, pattern, fits, note in RULES:
        match = pattern.search(german)
        if not match or (genders and gender not in genders):
            continue
        if fits(german, plural):
            return {"kind": "rule", "text": note.format(e=match.group(1))}
        if note.startswith("阴性词尾 -in"):       # Medizin 这类不是指人的 -in, 不算例外
            break
        return {"kind": "exception", "text": note.format(e=match.group(1)) + "。这个词是例外，要单独记"}
    found = tendency(german, gender, plural)
    return {"kind": "tendency", "text": found} if found else {"kind": "none", "text": UNMARKED}


def plural_question(row):
    german, gender, plural = row["german"], row["gender"], row["plural"]
    rule = plural_rule(german, gender, plural)
    q = question(row, "写出复数", "die ", plural, f"die {plural}")
    q.update(rule=rule["text"], rule_kind=rule["kind"],
             rule_hint=rule["text"] if rule["kind"] in ("rule", "tendency") else UNMARKED,
             recap=f"{gender} {german} → die {plural} — {row['meaning']}")
    return q


def scope_source(scope):
    """返回 (JOIN, 错题本条件, 命名参数, 查看单词时的顺序)"""
    if scope == "wrong":
        return "", IN_WRONG, {}, "pp.last_at DESC, w.german"
    join, args, order = book_filter(scope)
    return join, "", args, order


@bp.route("/api/plural")
@login_required
def questions():
    """?scope=单词书或 wrong: 一组题, 每个词一题。错过的词 > 没练过的 > 很久没练的; 同一档随机"""
    scope = request.args.get("scope") or current_book(current_user_id())
    if scope not in SCOPES:
        return err("范围无效")
    join, where, args, _order = scope_source(scope)
    rows = query(
        f"SELECT w.id, w.german, w.gender, w.plural, w.meaning FROM my_words w {join} {MARKS} "
        f"WHERE {HAS_PLURAL} {where} "
        "ORDER BY CASE WHEN pp.wrong > 0 AND pp.streak < :done THEN 0 WHEN pp.word_id IS NULL THEN 1 ELSE 2 END, "
        "pp.last_at, RANDOM() LIMIT :n",
        n=ROUND_SIZE, done=STREAK_DONE, **args,
    ).fetchall()
    return jsonify({"questions": [plural_question(r) for r in rows]})


@bp.route("/api/plural/books")
@login_required
def books():
    """练习范围: 各单词书能出题的词数和进度、错题本的词数、当前单词书。格式同 /api/grammar/nouns/books"""
    counts = ("COUNT(*) AS nouns, COUNT(pp.word_id) AS practiced, "
              f"COALESCE(SUM(CASE WHEN 1 {IN_WRONG} THEN 1 ELSE 0 END), 0) AS weak, "
              "COALESCE(SUM(pp.good_days >= :days), 0) AS mastered")
    by = {}
    for table_name, key in (("word_levels", "level"), ("word_books", "book")):
        for r in query(f"SELECT l.{key} AS book, {counts} FROM my_words w JOIN {table_name} l ON l.word_id = w.id "
                       f"{MARKS} WHERE {HAS_PLURAL} GROUP BY l.{key}", done=STREAK_DONE, days=MASTER_DAYS).fetchall():
            by[r["book"]] = dict(r)
    whole = query(f"SELECT {counts} FROM my_words w {MARKS} WHERE {HAS_PLURAL}", done=STREAK_DONE,
                  days=MASTER_DAYS).fetchone()
    by["all"] = {**dict(whole), "book": "all"}
    return jsonify({"current": current_book(current_user_id()), "wrong": whole["weak"],
                    "books": [by[b] for b in BOOKS if b in by]})


@bp.route("/api/plural/words")
@login_required
def words():
    """查看一个范围里的词 ?scope=&page=: 带练习记录, manual = 手动加进错题本的"""
    scope = request.args.get("scope", "")
    if scope not in SCOPES:
        return err("范围无效")
    try:
        page = max(int(request.args.get("page", "1")), 1)
    except ValueError:
        return err("页码无效")
    join, where, args, order = scope_source(scope)
    source = f"FROM my_words w {join} {MARKS} WHERE {HAS_PLURAL} {where}"
    total = query(f"SELECT COUNT(*) {source}", done=STREAK_DONE, **args).fetchone()[0]
    rows = query(
        "SELECT w.id, w.german, w.gender, w.plural, w.meaning, COALESCE(pp.wrong, 0) AS wrong, "
        f"COALESCE(pp.streak, 0) AS streak, pl.word_id IS NOT NULL AS manual {source} "
        f"ORDER BY {order} LIMIT :lim OFFSET :off",
        done=STREAK_DONE, lim=PAGE_SIZE, off=(page - 1) * PAGE_SIZE, **args,
    ).fetchall()
    return jsonify({"words": [{**dict(r), "manual": bool(r["manual"])} for r in rows], "total": total, "page": page,
                    "pages": max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)})


@bp.route("/api/plural/result", methods=["POST"])
@login_required
def result():
    """记一次作答 {word_id, ok}: 只记每组第一次作答。?tz= 决定“今天”是哪一天"""
    data = json_body()
    word_id, ok = (data.get("word_id"), data.get("ok")) if data else (None, None)
    if isinstance(word_id, bool) or not isinstance(word_id, int) or not isinstance(ok, bool):
        return err("参数无效")
    if query("SELECT 1 FROM all_my_words WHERE id = :id", id=word_id).fetchone() is None:
        return err("单词不存在", 404)
    db = get_db()
    day = local_day(read_tz())[0]
    db.execute(
        "INSERT INTO plural_practice (user_id, word_id, seen, wrong, streak, last_at, good_days, last_good_day) "
        "VALUES (?,?,1,?,?,?,?,?) "
        "ON CONFLICT(user_id, word_id) DO UPDATE SET seen = seen + 1, wrong = wrong + excluded.wrong, "
        "streak = CASE WHEN excluded.wrong = 1 THEN 0 ELSE streak + 1 END, last_at = excluded.last_at, "
        "good_days = CASE WHEN excluded.wrong = 1 THEN 0 WHEN last_good_day = excluded.last_good_day THEN good_days "
        "ELSE good_days + 1 END, last_good_day = excluded.last_good_day",
        (current_user_id(), word_id, 0 if ok else 1, 1 if ok else 0, now_str(), 1 if ok else 0, day if ok else ""),
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/plural/list", methods=["POST"])
@login_required
def add_words():
    """加入错题本 {text: "Palette, Karton"}: 逗号、空格或换行分隔。没有复数数据的词算没找到。返回 added / skipped / missing"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    names = [x for x in re.split(r"[,，;；、\s]+", text(data.get("text"), 3000)) if x and x not in OPTIONS]
    if not names:
        return err("请输入要加入的名词")
    ids, missing = [], []
    for name in names[:100]:
        word_id = resolve_noun(name)
        if word_id and query(f"SELECT 1 FROM my_words w WHERE w.id = :id AND {HAS_PLURAL}", id=word_id).fetchone():
            ids.append(word_id)
        else:
            missing.append(name)
    db = get_db()
    added = 0
    for word_id in dict.fromkeys(ids):
        added += db.execute("INSERT OR IGNORE INTO plural_list (user_id, word_id, added_at) VALUES (?,?,?)",
                            (current_user_id(), word_id, now_str())).rowcount
    db.commit()
    return jsonify({"added": added, "skipped": len(set(ids)) - added, "missing": missing})


@bp.route("/api/plural/list/<int:word_id>", methods=["DELETE"])
@login_required
def remove_word(word_id):
    """移出错题本: 手动加的删掉, 错过的记录清零; 练过几次还留着"""
    db = get_db()
    db.execute("DELETE FROM plural_list WHERE user_id = ? AND word_id = ?", (current_user_id(), word_id))
    db.execute("UPDATE plural_practice SET wrong = 0, streak = 0 WHERE user_id = ? AND word_id = ?",
               (current_user_id(), word_id))
    db.commit()
    return jsonify({"ok": True})
