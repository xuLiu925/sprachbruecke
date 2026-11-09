"""学习路径(文档 docs/features/learning-path.md): 按 A1 → C1 告诉用户每一级学什么、学到哪了、下一步做什么。

每一级三部分, 都用已有的数据算, 只多存一样东西(语法成绩):
- 单词: 这一级单词书学过的词(progress 有记录) ≥ WORD_GOAL 算完成
- 语法: PATH 里这一级的知识点, 某一组得分 ≥ GRAMMAR_GOAL 算完成。成绩以前只在本机 localStorage,
  现在每组做完也存到 user_settings 的 grammar_best(JSON {知识点: [得分, 总题数]}, 只留最好的一次)
- 情景课: 这一级的自带课学完(user_settings 的 lesson_done, lessons.py 记)
B2、C1 暂时只有单词。知识点归哪一级、顺序是 Claude 排的, 要对照教材核对。
"""
import json

from flask import Blueprint, jsonify

from database import get_db
from helpers import current_user_id, err, json_body, login_required
import lessons
from vocab import LEVELS, current_book, query

bp = Blueprint("learn_path", __name__)

WORD_GOAL = 0.8       # 这一级单词书学过 80% 算完成
GRAMMAR_GOAL = 0.8    # 语法知识点有一组得分 ≥ 80% 算完成
BEST_KEY = "grammar_best"

# 每一级的语法知识点, 按建议的学习顺序(id 对应 static/js/grammar-data.js 的 GRAMMAR_TOPICS)
PATH = {
    "A1": ["art-def", "verb-sein", "verb-praes", "order-main", "w-fragen", "art-indef", "art-kein", "neg",
           "numbers", "time", "pron", "art-poss", "verb-modal", "sep-verbs", "prep-akk", "prep-dat"],
    "A2": ["perf-part", "perf-aux", "perf-bank", "order-sub", "prep-wechsel", "adj-weak", "adj-mixed",
           "comp-form", "comp-sentence"],
    "B1": ["verb-usage", "adj-strong", "adj-mix"],
    "B2": [],
    "C1": [],
}
TOPICS = {t for ts in PATH.values() for t in ts}


def read_best(uid):
    row = get_db().execute("SELECT value FROM user_settings WHERE user_id = ? AND key = ?", (uid, BEST_KEY)).fetchone()
    try:
        best = json.loads(row["value"]) if row else {}
    except ValueError:
        best = {}
    return best if isinstance(best, dict) else {}


def ratio(x):
    return x[0] / x[1] if x and x[1] else 0


@bp.route("/api/path")
@login_required
def path():
    uid = current_user_id()
    words = {r["level"]: dict(r) for r in query(
        "SELECT l.level, COUNT(*) AS total, COUNT(p.word_id) AS learned FROM my_words w "
        "JOIN word_levels l ON l.word_id = w.id LEFT JOIN progress p ON p.word_id = w.id AND p.user_id = :uid "
        "GROUP BY l.level").fetchall()}
    best = read_best(uid)
    _, done = lessons.lesson_state(uid)
    done = set(done)
    by_level = {}
    for l in lessons.load_items()["lessons"].values():
        by_level.setdefault(l["level"], []).append(l["id"])
    out = []
    for lv in LEVELS:
        w = words.get(lv, {"total": 0, "learned": 0})
        grammar = [{"id": t, "best": best.get(t), "done": ratio(best.get(t)) >= GRAMMAR_GOAL} for t in PATH[lv]]
        les = [{"id": i, "done": i in done} for i in by_level.get(lv, [])]
        word_part = min(w["learned"] / (w["total"] * WORD_GOAL), 1) if w["total"] else 1
        parts = [word_part]
        if grammar:
            parts.append(sum(g["done"] for g in grammar) / len(grammar))
        if les:
            parts.append(sum(x["done"] for x in les) / len(les))
        out.append({"level": lv, "words": {**w, "goal": int(w["total"] * WORD_GOAL + 0.999)},
                    "grammar": grammar, "lessons": les, "percent": round(sum(parts) / len(parts) * 100)})
    # 当前级别 = 第一个没学完的; 全学完了就停在最后一级
    current = next((x["level"] for x in out if x["percent"] < 100), LEVELS[-1])
    return jsonify({"levels": out, "current": current, "book": current_book(uid),
                    "word_goal": WORD_GOAL, "grammar_goal": GRAMMAR_GOAL})


@bp.route("/api/path/grammar", methods=["POST"])
@login_required
def save_grammar():
    """{items: [[知识点, 得分, 总题数], …]} 记语法成绩, 每个知识点只留得分率最高的一次。
    每组做完发一条; 打开学习路径时把本机以前的成绩(localStorage)一起发上来"""
    data = json_body()
    items = data.get("items") if data else None
    if not isinstance(items, list) or len(items) > 100:
        return err("请求格式错误")
    uid = current_user_id()
    best = read_best(uid)
    changed = False
    for it in items:
        if not (isinstance(it, list) and len(it) == 3):
            continue
        topic, score, total = it
        if topic not in TOPICS or not all(isinstance(x, int) and not isinstance(x, bool) for x in (score, total)):
            continue
        if not (0 <= score <= total <= 200 and total > 0):
            continue
        if ratio([score, total]) > ratio(best.get(topic)):
            best[topic] = [score, total]
            changed = True
    if changed:
        db = get_db()
        db.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?) "
                   "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value", (uid, BEST_KEY, json.dumps(best)))
        db.commit()
    return jsonify({"best": best})
