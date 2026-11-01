"""把用户加的词放进总词库。对用户来说是“所有德语词都有, 他只是加入学习计划”

words 里每个词只有一行, user_added_words 记谁加过, 用户写的内容放 user_word_edits(只对他显示)。
  词库已有            → 共用这一行
  词典有(lexicon)     → 新建公开词, 冠词、复数、变格以词典为准, 所有人都能查到
  词典里是变化形式    → 用原形
  词典没有            → status = pending, 只有加过的人看得到, 等管理员审核
公共释义只用可靠来源。词典没有释义时用户要自己写(只对他显示), 公开词显示“释义待补充”, 由管理员确认后补上。
"""
import re

import lexicon
from database import now_str
from vocab import GENDERS, clean_forms

MISSING_MEANING = "释义待补充"
WORD = re.compile(r"[A-Za-zÄÖÜäöüßẞ0-9][A-Za-zÄÖÜäöüßẞ0-9' .-]*")
ARTICLE = re.compile(r"(der|die|das)\s+(.+)", re.I)


def read_item(d):
    """{german, gender, ...} → 去掉空格的字典; 写成 der Tisch 时把冠词分出来"""
    if not isinstance(d, dict):
        return None
    get = lambda k, n: str(d.get(k, "") or "").strip()[:n]   # noqa: E731
    item = {"german": str(d.get("german", "") or "").strip(), "gender": get("gender", 10).lower(), "pos": get("pos", 20),
            "plural": get("plural", 100), "meaning": get("meaning", 300), "example": get("example", 300)}
    m = ARTICLE.fullmatch(item["german"])
    if m and not item["gender"]:
        item["gender"], item["german"] = m.group(1).lower(), m.group(2).strip()
    return item


def find_word(db, german, gender):
    """词库里的一行: 没写冠词时公开的优先"""
    return db.execute(
        "SELECT id, status, pos, plural, meaning, example FROM words WHERE german = ? AND owner_id IS NULL "
        "AND (gender = ? OR ? = '') ORDER BY status != 'public', id LIMIT 1", (german, gender, gender),
    ).fetchone()


def join_word(db, uid, word_id):
    """贴上标签; 删掉过的词恢复。返回 (是不是第一次贴, 是不是恢复回来的)"""
    tagged = db.execute("INSERT OR IGNORE INTO user_added_words (user_id, word_id, added_at) VALUES (?,?,?)",
                        (uid, word_id, now_str())).rowcount > 0
    return tagged, db.execute("DELETE FROM user_hidden_words WHERE user_id = ? AND word_id = ?",
                              (uid, word_id)).rowcount > 0


def keep_own_text(db, uid, word_id, item, row):
    """用户写的释义或例句和词库不同: 存成他自己的版本, 公共内容不变"""
    meaning, example = item["meaning"] or row["meaning"], item["example"] or row["example"]
    if (meaning, example) == (row["meaning"], row["example"]):
        return
    base = db.execute("SELECT german, pos, gender, plural FROM words WHERE id = ?", (word_id,)).fetchone()
    forms = db.execute("SELECT forms FROM word_forms WHERE word_id = ?", (word_id,)).fetchone()
    db.execute(
        "INSERT OR IGNORE INTO user_word_edits (user_id, word_id, german, pos, gender, plural, meaning, example, "
        "forms, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (uid, word_id, *tuple(base), meaning, example, forms[0] if forms else None, now_str()),
    )


def insert_word(db, values, status, forms):
    word_id = db.execute(
        "INSERT INTO words (german, pos, gender, plural, meaning, example, status) VALUES (?,?,?,?,?,?,?)",
        (*values, status),
    ).lastrowid
    if forms:
        db.execute("INSERT INTO word_forms (word_id, forms) VALUES (?, ?)", (word_id, forms))
    return word_id


def no_meaning(item):
    """不放进没有释义的卡片: 宁可让用户写一条, 也不用不可靠的来源"""
    return {"kind": "invalid", "german": item["german"], "error": "这个词还没有中文释义，请写上释义再加入"}


def add_word(db, uid, d, use_lemma=False):
    """加一个词。返回 {kind, word_id, ...}, kind:
    existing 词库已有 / new 新公开词 / pending 待审核 / form_of 是变化形式(use_lemma = False 时不加, 让用户确认) / invalid"""
    item = read_item(d)
    if item is None or not WORD.fullmatch(item["german"]) or len(item["german"]) > 100:
        return {"kind": "invalid", "german": str((d or {}).get("german", "")) if isinstance(d, dict) else "",
                "error": "这不是德语单词"}
    if item["gender"] not in GENDERS:
        return {"kind": "invalid", "german": item["german"], "error": "性别只能是 der / die / das 或留空"}
    row = find_word(db, item["german"], item["gender"])
    hit, lemma = (None, None) if row else lexicon.find(item["german"], item["gender"])
    if lemma:
        if not use_lemma:
            return {"kind": "form_of", "german": item["german"], "lemma": lemma}
        out = add_word(db, uid, {**item, "german": lemma, "gender": ""})
        return {**out, "lemma": lemma}
    if hit:       # 用词典的写法再找一次: tisch → Tisch
        row = find_word(db, hit["german"], hit["gender"])
    if row and row["meaning"] == MISSING_MEANING and not item["meaning"] and not db.execute(
            "SELECT 1 FROM user_word_edits WHERE user_id = ? AND word_id = ?", (uid, row["id"])).fetchone():
        return no_meaning(item)
    if row:
        tagged, restored = join_word(db, uid, row["id"])
        keep_own_text(db, uid, row["id"], item, row)
        # 别人加的待审核的词他之前看不到, 对他来说是新加的
        return {"kind": "existing", "word_id": row["id"], "restored": restored or (tagged and row["status"] != "public")}
    if not item["meaning"] and not (hit and hit["meaning"]):
        return no_meaning(item)
    if hit:
        forms, _e = clean_forms(hit["forms"])
        public = (hit["german"], hit["pos"], hit["gender"], hit["plural"], hit["meaning"] or MISSING_MEANING, "")
        word_id = insert_word(db, public, "public", forms)
        join_word(db, uid, word_id)
        keep_own_text(db, uid, word_id, item, {"meaning": public[4], "example": ""})
        return {"kind": "new", "word_id": word_id}
    forms, e = clean_forms(d.get("forms"))
    if e:
        return {"kind": "invalid", "german": item["german"], "error": e}
    values = (item["german"], item["pos"], item["gender"], item["plural"], item["meaning"], item["example"])
    word_id = insert_word(db, values, "pending", forms)
    join_word(db, uid, word_id)
    return {"kind": "pending", "word_id": word_id}


def word_id_for(db, uid, row):
    """课文、AI 查词里的词要进学习计划: row = (德语, 词性, 冠词, 复数, 释义, 例句)。这些词不一定规范, 不合格也留下"""
    d = dict(zip(("german", "pos", "gender", "plural", "meaning", "example"), row))
    out = add_word(db, uid, d, use_lemma=True)
    if out["kind"] != "invalid":
        return out["word_id"]
    word_id = insert_word(db, row, "pending", None)
    join_word(db, uid, word_id)
    return word_id
