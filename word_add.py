"""添加单词和管理员审核。放进词库的规则在 word_store.py

审核列表有两种词: pending = 词典里没有, 等管理员决定公不公开; no_meaning = 公开了但没有公共释义, 等管理员补上。
AI 只出草稿, 管理员确认后才写入。
"""
from flask import Blueprint, jsonify, request

import lexicon
from auth import admin_required
from custom_lessons import CHINESE, AiError, api_key, call_gemini, extract_json, text
from database import get_db
from dictionary import build_prompt, clean_ai_word
from helpers import current_user_id, err, json_body, login_required
from vocab import enqueue
from word_store import MISSING_MEANING, add_word

bp = Blueprint("word_add", __name__)

MAX_ITEMS = 2000
MAX_INVALID = 20     # 报告里最多列多少个无效的词
MAX_MEANING = 300
STATUSES = ("public", "rejected")


@bp.route("/api/words", methods=["POST"])
@login_required
def add_words():
    """加词 = 加入学习计划。单个 {german, ...}: 今天的学习量 +1, 是变化形式时返回 form_of 让用户确认;
    批量 [...]: 只排队, 变化形式自动用原形。返回 added / skipped / queued / pending / lemma / invalid"""
    data = request.get_json(silent=True)
    single = isinstance(data, dict)
    items = [data] if single else data if isinstance(data, list) else None
    if not items:
        return err("请求格式错误")
    if len(items) > MAX_ITEMS:
        return err(f"一次最多导入 {MAX_ITEMS} 个")
    db = get_db()
    uid = current_user_id()
    report = {"added": 0, "skipped": 0, "queued": 0, "pending": 0, "lemma": 0, "invalid": []}
    for d in items:
        out = add_word(db, uid, d, use_lemma=not single)
        if out["kind"] == "form_of":
            return jsonify({**report, "form_of": out["lemma"]})
        if out["kind"] == "invalid":
            if single:
                return err(out["error"])
            report["invalid"].append(out["german"])
            continue
        report["lemma"] += "lemma" in out
        report["pending"] += out["kind"] == "pending"
        new = out["kind"] != "existing" or out["restored"]
        report["added" if new else "skipped"] += 1
        report["queued"] += enqueue(db, uid, out["word_id"], 1 if single else 0)
    report["invalid_count"] = len(report["invalid"])
    report["invalid"] = report["invalid"][:MAX_INVALID]
    db.commit()
    return jsonify(report)


@bp.route("/api/admin/pending")
@admin_required
def pending():
    """审核列表: 加过的人数多的在前, compound = 疑似复合词的拆法; ai = 配置了 Key"""
    rows = get_db().execute(
        "SELECT w.id, w.german, w.gender, w.pos, w.meaning, COUNT(a.user_id) AS users, "
        "CASE w.status WHEN 'pending' THEN 'pending' ELSE 'no_meaning' END AS kind FROM words w "
        "LEFT JOIN user_added_words a ON a.word_id = w.id "
        "WHERE w.status = 'pending' OR (w.status = 'public' AND w.meaning = ?) "
        "GROUP BY w.id ORDER BY users DESC, w.id LIMIT 200", (MISSING_MEANING,),
    ).fetchall()
    words = [{**dict(r), "compound": lexicon.compound(r["german"]) if r["kind"] == "pending" else None} for r in rows]
    return jsonify({"words": words, "ai": bool(api_key())})


@bp.route("/api/admin/pending/<int:word_id>", methods=["POST"])
@admin_required
def review(word_id):
    """{status: public | rejected}: 通过后所有人都能查到; 拒绝后还留在加过的人的学习计划里"""
    data = json_body()
    status = data.get("status") if data else None
    if status not in STATUSES:
        return err("状态无效")
    db = get_db()
    cur = db.execute("UPDATE words SET status = ? WHERE id = ? AND status = 'pending'", (status, word_id))
    db.commit()
    if cur.rowcount == 0:
        return err("这个词不在待审核里", 404)
    return jsonify({"ok": True})


def missing_word(word_id):
    return get_db().execute("SELECT german FROM words WHERE id = ? AND meaning = ?",
                            (word_id, MISSING_MEANING)).fetchone()


@bp.route("/api/admin/words/<int:word_id>/draft", methods=["POST"])
@admin_required
def draft(word_id):
    """AI 写一条释义草稿, 不保存"""
    row = missing_word(word_id)
    if row is None:
        return err("这个词不缺释义", 404)
    try:
        raw = call_gemini(build_prompt(row["german"]))
    except AiError as ex:
        return err(ex.msg, ex.code)
    word, e = clean_ai_word(extract_json(raw))
    if e:
        return err("AI 没写好，请再试一次", 502)
    return jsonify({"meaning": word["meaning"]})


@bp.route("/api/admin/words/<int:word_id>/meaning", methods=["POST"])
@admin_required
def set_meaning(word_id):
    """管理员确认公共释义 {meaning, ai}: ai = 来自 AI 草稿, 详情页标成机器翻译"""
    data = json_body()
    meaning = text(data.get("meaning"), MAX_MEANING) if data else ""
    if not CHINESE.search(meaning):
        return err("请写中文释义")
    if missing_word(word_id) is None:
        return err("这个词不缺释义", 404)
    db = get_db()
    db.execute("UPDATE words SET meaning = ? WHERE id = ?", (meaning, word_id))
    if data.get("ai"):
        db.execute("INSERT OR IGNORE INTO word_details (word_id, details) VALUES (?, ?)", (word_id, '{"machine": true}'))
    db.commit()
    return jsonify({"ok": True})
