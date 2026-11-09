"""听写: 听发音写出单词(名词按设置带冠词), 不用 AI, 不影响今日学习

结构照定冠词练习(noun_quiz.py):
- 练习范围: 单词书(A1–C1、专题书、全部)或错题本
- 记忆用 FSRS 排期(dict_practice), 和词义的 progress 分开: 认得这个词 ≠ 听得出、写得对。
  写对 = 良好, 写错 = 忘了(最早明天再出); 同一天再写对不算数(update_practice 的规则)
- 每组出题: 到期的(最容易忘的优先, 最多 n - 4 个) > 没练过的(今日学习学过的优先, 再按词频) > 未到期里最容易忘的
- 错题本 = 写错过的词(稳定性到 7 天才移出) + 手动加的(dict_list, 手动移除才走)
- 判对错在前端(review.js 的 checkSpell, ae/oe/ue/ss 也算对), 这里只记结果
"""
import re

from flask import Blueprint, jsonify, request

from custom_lessons import text
from database import get_db, now_str
from helpers import current_user_id, err, json_body, login_required
from lessons import find_word
from noun_quiz import MASTER_S, MIN_NEW, PAGE_SIZE, pick_round, update_practice
from today import local_day, read_tz
from vocab import BOOKS, book_filter, current_book, query

bp = Blueprint("dictation", __name__)

SCOPES = BOOKS + ["wrong"]
POOL = 60
DEFAULT_N = 20
MAX_ROUND = 30
COLS = "w.id, w.german, w.gender, w.pos, w.plural, w.meaning, w.example"
MARKS = ("LEFT JOIN dict_practice dp ON dp.word_id = w.id AND dp.user_id = :uid "
         "LEFT JOIN dict_list dl ON dl.word_id = w.id AND dl.user_id = :uid")
IN_WRONG = "AND (dp.weak = 1 OR dl.word_id IS NOT NULL)"
RISK = "COALESCE((julianday(:now) - julianday(dp.last_review)) / dp.stability, 1e9) DESC, dp.last_at"
# 能听写的词: 不太长, 只有字母、空格、连字符(缩写、带数字、带括号的词读出来没法写)
USABLE = "AND length(w.german) <= 40 AND w.german NOT GLOB '*[0-9()/.,]*'"
assert MIN_NEW < DEFAULT_N


def read_n():
    try:
        return min(max(int(request.args.get("n", DEFAULT_N)), 1), MAX_ROUND)
    except ValueError:
        return None


@bp.route("/api/dictation")
@login_required
def dictation():
    """?scope=单词书或 wrong&n=20: 一组听写题, 每个词一题。不带 scope 时用当前单词书"""
    scope = request.args.get("scope") or current_book(current_user_id())
    if scope not in SCOPES + ["due"]:
        return err("范围无效")
    n = read_n()
    if n is None:
        return err("题数无效")
    base = (f"SELECT {COLS}, dp.stability FROM my_words w {{join}} {MARKS} "
            f"LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid WHERE 1 {USABLE} {{where}}")
    now = now_str()
    if scope == "wrong":                 # 错题本: 到没到期都出, 最容易忘的优先
        rows = query(base.format(join="", where=IN_WRONG) + f" ORDER BY {RISK} LIMIT :n", n=n, now=now).fetchall()
        words = [dict(r) for r in rows]
        return jsonify({"words": pick_round(words, [], [], n)})
    end = local_day(read_tz())[2]        # 到期按本地日期, 和今日学习一样
    due_where = "AND dp.word_id IS NOT NULL AND (dp.next_review IS NULL OR dp.next_review < :end)"
    if scope == "due":                   # 今天页: 只出到期的, 不管哪本单词书
        rows = query(base.format(join="", where=due_where) + f" ORDER BY {RISK} LIMIT :n", n=n, now=now, end=end).fetchall()
        return jsonify({"words": pick_round([dict(r) for r in rows], [], [], n)})
    join, args, order = book_filter(scope)

    def rows(where, tail):
        return [dict(r) for r in query(base.format(join=join, where=where) + f" ORDER BY {tail} LIMIT :pool",
                                       pool=POOL, now=now, end=end, **args).fetchall()]
    due = rows(due_where, RISK)
    new = rows("AND dp.word_id IS NULL", f"p.word_id IS NULL, {order}")
    spare = rows("AND dp.next_review >= :end", RISK)
    return jsonify({"words": pick_round(due, new, spare, n)})


@bp.route("/api/dictation/books")
@login_required
def dict_books():
    """练习范围: 各单词书的词数和听写进度、错题本词数、当前单词书。字段名和定冠词练习一样(nouns = 词数), 前端共用"""
    counts = ("COUNT(*) AS nouns, COUNT(dp.word_id) AS practiced, "
              f"COALESCE(SUM(CASE WHEN 1 {IN_WRONG} THEN 1 ELSE 0 END), 0) AS weak, "
              "COALESCE(SUM(dp.stability >= :master), 0) AS mastered")
    by = {}
    for table_name, key in (("word_levels", "level"), ("word_books", "book")):
        for r in query(f"SELECT l.{key} AS book, {counts} FROM my_words w JOIN {table_name} l ON l.word_id = w.id "
                       f"{MARKS} WHERE 1 {USABLE} GROUP BY l.{key}", master=MASTER_S).fetchall():
            by[r["book"]] = dict(r)
    whole = query(f"SELECT {counts} FROM my_words w {MARKS} WHERE 1 {USABLE}", master=MASTER_S).fetchone()
    by["all"] = {**dict(whole), "book": "all"}
    return jsonify({"current": current_book(current_user_id()), "wrong": whole["weak"],
                    "books": [by[b] for b in BOOKS if b in by]})


@bp.route("/api/dictation/words")
@login_required
def dict_words():
    """查看一个范围里的词 ?scope=&page=: 带 wrong / streak / manual"""
    scope = request.args.get("scope", "")
    if scope not in SCOPES:
        return err("范围无效")
    try:
        page = max(int(request.args.get("page", "1")), 1)
    except ValueError:
        return err("页码无效")
    if scope == "wrong":
        join, where, args, order = "", IN_WRONG, {}, "dp.last_at DESC, w.german"
    else:
        join, args, order = book_filter(scope)
        where = ""
    source = f"FROM my_words w {join} {MARKS} WHERE 1 {USABLE} {where}"
    total = query(f"SELECT COUNT(*) {source}", **args).fetchone()[0]
    rows = query(
        f"SELECT w.id, w.german, w.gender, w.plural, w.meaning, COALESCE(dp.wrong, 0) AS wrong, "
        f"COALESCE(dp.streak, 0) AS streak, dl.word_id IS NOT NULL AS manual {source} ORDER BY {order} LIMIT :lim OFFSET :off",
        lim=PAGE_SIZE, off=(page - 1) * PAGE_SIZE, **args,
    ).fetchall()
    words = [{**dict(r), "manual": bool(r["manual"])} for r in rows]
    return jsonify({"words": words, "total": total, "page": page, "pages": max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)})


@bp.route("/api/dictation/result", methods=["POST"])
@login_required
def result():
    """记一次作答 {word_id, ok}: 只记每组第一次作答(前端负责), 不影响今日学习"""
    data = json_body()
    word_id, ok = (data.get("word_id"), data.get("ok")) if data else (None, None)
    if isinstance(word_id, bool) or not isinstance(word_id, int) or not isinstance(ok, bool):
        return err("参数无效")
    if query("SELECT 1 FROM all_my_words WHERE id = :id", id=word_id).fetchone() is None:
        return err("单词不存在", 404)
    db = get_db()
    update_practice(db, current_user_id(), word_id, 3 if ok else 1, table="dict_practice")
    db.commit()
    return jsonify({"ok": True})


@bp.route("/api/dictation/list", methods=["POST"])
@login_required
def add_words():
    """加入错题本 {word_id} 或 {text: "Palette, abholen"}: 逗号、空格或换行分隔, 变化形式找原形。返回 added / skipped / missing"""
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
        added += db.execute("INSERT OR IGNORE INTO dict_list (user_id, word_id, added_at) VALUES (?,?,?)",
                            (uid, word_id, now_str())).rowcount
    db.commit()
    return jsonify({"added": added, "skipped": len(set(ids)) - added, "missing": missing})


@bp.route("/api/dictation/list/<int:word_id>", methods=["DELETE"])
@login_required
def remove_word(word_id):
    """移出错题本: 手动加的删掉, 错过的记录清零"""
    db = get_db()
    uid = current_user_id()
    db.execute("DELETE FROM dict_list WHERE user_id = ? AND word_id = ?", (uid, word_id))
    db.execute("UPDATE dict_practice SET wrong = 0, streak = 0, weak = 0 WHERE user_id = ? AND word_id = ?", (uid, word_id))
    db.commit()
    return jsonify({"ok": True})
