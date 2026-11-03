"""试学(Blueprint): 不登录也能先学一轮, 注册后把结果存进进度。文档 docs/features/guest-trial.md

- GET  /api/trial/cards   不用登录: A1 最常用的 10 个词, 卡片格式同 /api/review/today
- POST /api/trial/save    登录后: {answers: [{word_id, rating, mode}]} 按顺序记进 progress / review_log
                          只收试学的词; 已经学过的词跳过(不覆盖真实进度)

试学的评分只存在浏览器里(localStorage), 服务器不记游客的任何东西。
在线发音 /api/tts 游客新取有全站次数限制, 试学这几个词和例句不算(allowed_tts)。
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify

from database import get_db
from helpers import current_user_id, err, json_body, login_required
from vocab import WORD_COLS, apply_review, card, query

bp = Blueprint("trial", __name__)

TRIAL_N = 10
MAX_ANSWERS = 40   # 忘了的词本轮会再考一次拼写, 10 个词最多 20 次评分, 留点余量
NO_MEANING = "释义待补充"
COLS = f"SELECT {WORD_COLS}, 0 AS reps, 0 AS spell_ok, 1 AS is_new FROM my_words w "
GOOD = f"w.meaning != '' AND w.meaning != '{NO_MEANING}' AND NOT w.private"


# (词性, 冠词, 个数): 名词三种冠词各 2 个, 能展示颜色、复数、变格; 最常用的词多是 ich、und 这类虚词
MIX = [("名词", "der", 2), ("名词", "die", 2), ("名词", "das", 2), ("动词", "", 3), ("形容词", "", 1)]


def trial_rows():
    """A1 里按词性挑词频最高、有释义的词, 带中文翻译的例句优先, 再按词频排。
    单词书不够(测试库)时用词库里其他词补"""
    rows = []
    for pos, gender, n in MIX:
        rows += query(
            COLS.replace("SELECT ", "SELECT l.rank AS trank, ", 1)
            + "JOIN word_levels l ON l.word_id = w.id AND l.level = 'A1' "
            f"WHERE {GOOD} AND w.pos = :pos AND w.gender = :g ORDER BY instr(COALESCE(w.example, ''), char(10)) = 0, l.rank LIMIT :n",
            pos=pos, g=gender, n=n,
        ).fetchall()
    rows.sort(key=lambda r: r["trank"])
    if len(rows) < TRIAL_N:
        have = [r["id"] for r in rows] or [0]
        rows += query(
            COLS + f"WHERE {GOOD} AND w.id NOT IN ({','.join(map(str, have))}) ORDER BY w.id LIMIT :n",
            n=TRIAL_N - len(rows),
        ).fetchall()
    return rows


def allowed_tts(text):
    """游客能用在线发音读的文字: 试学的词(带冠词和不带)和例句第一行"""
    ok = set()
    for r in trial_rows():
        ok.add(r["german"])
        if r["gender"]:
            ok.add(r["gender"] + " " + r["german"])
        if r["example"]:
            ok.add(" ".join(r["example"].split("\n")[0].split()))
    return text in ok


@bp.route("/api/trial/cards")
def trial_cards():
    return jsonify({"cards": [card(r) for r in trial_rows()]})


@bp.route("/api/trial/save", methods=["POST"])
@login_required
def trial_save():
    data = json_body()
    answers = data.get("answers") if data else None
    if not isinstance(answers, list) or len(answers) > MAX_ANSWERS:
        return err("试学记录格式错误")
    uid, db = current_user_id(), get_db()
    ids = {r["id"] for r in trial_rows()}
    learned = {r[0] for r in db.execute("SELECT word_id FROM progress WHERE user_id = ?", (uid,))}
    now = datetime.now(timezone.utc)
    saved = set()
    for a in answers:
        if not isinstance(a, dict):
            continue
        wid, rating, mode = a.get("word_id"), a.get("rating"), a.get("mode")
        if (not isinstance(wid, int) or isinstance(wid, bool) or wid not in ids or wid in learned
                or isinstance(rating, bool) or rating not in (1, 2, 3, 4) or mode not in ("recall", "spell")):
            continue
        apply_review(db, uid, wid, rating, mode, now)
        saved.add(wid)
    db.commit()
    return jsonify({"saved": len(saved)})
