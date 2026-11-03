"""今日学习: 学习计划和每天学多少(思路同墨墨背单词)

学习计划 = 当前单词书的词 + 用户自己加入的词(study_queue)。
只有一个设置: 每日学习量(user_settings 的 daily_goal)。先复习, 再学新词:
    今日新词 = 每日学习量 + 今天加的量 − 今天已学的词 − 还没复习的到期词
复习多的日子新词少, 复习少的日子新词多; 到期词再多也要全部复习, 这时没有新词。
今天单个加的词(study_queue.bonus = 1)不占上面的名额, 今天一定能学到, 所以学习量相当于 +1。

到期和“今天”都按用户设备的本地日期算, 凌晨 4 点换日。前端用 ?tz= 传 getTimezoneOffset() 的分钟数。
"""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from database import fmt_time, get_db
from helpers import current_user_id, err, json_body, login_required
from srs import DAY_HOUR
from vocab import WORD_COLS, book_filter, card, current_book, query

bp = Blueprint("today", __name__)

DEFAULT_GOAL = 40
MIN_GOAL, MAX_GOAL = 10, 500
MORE = 10                # “再学 10 个”
REVIEW_LIMIT = 50        # 一轮最多多少个到期词
NEW_PER_REQUEST = 50     # 一轮最多多少个新词
MAX_TZ = 840


def read_tz():
    try:
        return min(max(int(request.args.get("tz", "0")), -MAX_TZ), MAX_TZ)
    except ValueError:
        return 0


def local_day(tz):
    """(今天的日期, 今天开始, 今天结束): 后两个是 UTC 字符串"""
    local = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=tz)
    day = (local - timedelta(hours=DAY_HOUR)).date()
    start = datetime(day.year, day.month, day.day, DAY_HOUR) + timedelta(minutes=tz)
    return day.isoformat(), fmt_time(start), fmt_time(start + timedelta(days=1))


def get_setting(uid, key):
    row = get_db().execute("SELECT value FROM user_settings WHERE user_id = ? AND key = ?", (uid, key)).fetchone()
    return row["value"] if row else None


def set_setting(db, uid, key, value):
    db.execute("INSERT INTO user_settings (user_id, key, value) VALUES (?,?,?) "
               "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value", (uid, key, str(value)))


def goal_of(uid):
    return int(get_setting(uid, "daily_goal") or DEFAULT_GOAL)


def extra_of(uid, day):
    return int(get_setting(uid, "extra_count") or 0) if get_setting(uid, "extra_day") == day else 0


LEARNED_TODAY = "SELECT word_id FROM review_log WHERE user_id = :uid AND reviewed_at >= :start"
NOT_LEARNED = "w.id NOT IN (SELECT word_id FROM progress WHERE user_id = :uid)"
BONUS_TODAY = "q.bonus = 1 AND q.added_at >= :start"


def plan(tz):
    """今天的数字和这一轮的卡片"""
    uid = current_user_id()
    day, start, end = local_day(tz)
    goal, extra = goal_of(uid), extra_of(uid, day)
    args = {"start": start, "end": end}
    done = query(f"SELECT COUNT(DISTINCT word_id) FROM ({LEARNED_TODAY})", **args).fetchone()[0]
    due_join = "FROM progress p JOIN my_words w ON w.id = p.word_id WHERE p.user_id = :uid AND p.next_review < :end"
    due_total = query(f"SELECT COUNT(*) {due_join}", **args).fetchone()[0]
    due_left = query(f"SELECT COUNT(*) {due_join} AND w.id NOT IN ({LEARNED_TODAY})", **args).fetchone()[0]
    due = query(f"SELECT {WORD_COLS}, p.reps, p.spell_ok, p.stability, p.difficulty, p.last_review, 0 AS is_new {due_join} ORDER BY p.next_review LIMIT :lim",
                lim=REVIEW_LIMIT, **args).fetchall()
    bonus_join = "FROM study_queue q JOIN my_words w ON w.id = q.word_id WHERE q.user_id = :uid"
    bonus_all = query(f"SELECT COUNT(*) {bonus_join} AND {BONUS_TODAY}", **args).fetchone()[0]
    new_cols = f"SELECT {WORD_COLS}, 0 AS reps, 0 AS spell_ok, 1 AS is_new"
    bonus = query(f"{new_cols} {bonus_join} AND {BONUS_TODAY} AND {NOT_LEARNED} ORDER BY q.added_at, w.id LIMIT :lim",
                  lim=NEW_PER_REQUEST, **args).fetchall()
    bonus_done = bonus_all - query(f"SELECT COUNT(*) {bonus_join} AND {BONUS_TODAY} AND {NOT_LEARNED}",
                                   **args).fetchone()[0]
    room = min(max(goal + extra - (done - bonus_done) - due_left, 0), NEW_PER_REQUEST)
    queued = query(f"{new_cols} {bonus_join} AND NOT ({BONUS_TODAY}) AND {NOT_LEARNED} "
                   "ORDER BY q.added_at, w.id LIMIT :lim", lim=room, **args).fetchall()
    book_join, book_args, order = book_filter(current_book(uid))
    fresh = query(f"{new_cols} FROM my_words w {book_join} WHERE {NOT_LEARNED} "
                  f"AND w.id NOT IN (SELECT word_id FROM study_queue WHERE user_id = :uid) ORDER BY {order} LIMIT :lim",
                  lim=room - len(queued), **book_args).fetchall()
    new = list(bonus) + list(queued) + list(fresh)
    return {"goal": goal, "extra": extra, "target": goal + extra + bonus_all, "done": done, "due_total": due_total,
            "due": list(due), "new": new}


@bp.route("/api/review/today")
@login_required
def review_today():
    p = plan(read_tz())
    return jsonify({"cards": [card(r) for r in p["due"] + p["new"]], "due": len(p["due"]), "new": len(p["new"])})


HISTORY_DAYS = 60   # 连续天数最多往回算多少天


def history(tz):
    """(连续学习天数, 最近 7 天每天学了几个词[最早 → 今天])。按本地日期, 凌晨 4 点换日。
    今天还没学时, 连续天数算到昨天(今天学了就接上)。review_log 2026-10-27 才开始记"""
    day, start, _ = local_day(tz)
    since = fmt_time(datetime.strptime(start, "%Y-%m-%d %H:%M:%S") - timedelta(days=HISTORY_DAYS))
    rows = get_db().execute(
        "SELECT word_id, reviewed_at FROM review_log WHERE user_id = ? AND reviewed_at >= ?",
        (current_user_id(), since)).fetchall()
    per_day = {}
    for r in rows:
        t = datetime.strptime(r["reviewed_at"], "%Y-%m-%d %H:%M:%S") - timedelta(minutes=tz, hours=DAY_HOUR)
        per_day.setdefault(t.date(), set()).add(r["word_id"])
    today_d = datetime.strptime(day, "%Y-%m-%d").date()
    week = [len(per_day.get(today_d - timedelta(days=i), ())) for i in range(6, -1, -1)]
    d = today_d if today_d in per_day else today_d - timedelta(days=1)
    streak = 0
    while d in per_day:
        streak += 1
        d -= timedelta(days=1)
    return streak, week


def summary(tz):
    p = plan(tz)
    return {"goal": p["goal"], "extra": p["extra"], "target": p["target"], "done": p["done"],
            "due": p["due_total"], "new": len(p["new"])}


@bp.route("/api/today")
@login_required
def today():
    """首页的数字: target = 今日学习量, done = 今天已学的词, due = 待复习, new = 还能学的新词;
    streak = 连续学习天数, week = 最近 7 天每天学的词数(最早 → 今天)"""
    tz = read_tz()
    streak, week = history(tz)
    return jsonify({**summary(tz), "streak": streak, "week": week})


@bp.route("/api/today/goal", methods=["POST"])
@login_required
def set_goal():
    data = json_body()
    goal = data.get("goal") if data else None
    if isinstance(goal, bool) or not isinstance(goal, int) or not MIN_GOAL <= goal <= MAX_GOAL:
        return err(f"每日学习量要在 {MIN_GOAL}–{MAX_GOAL} 之间")
    db = get_db()
    set_setting(db, current_user_id(), "daily_goal", goal)
    db.commit()
    return jsonify(summary(read_tz()))


@bp.route("/api/today/more", methods=["POST"])
@login_required
def more():
    """再学 10 个: 只加今天的量, 明天恢复"""
    tz = read_tz()
    uid = current_user_id()
    day = local_day(tz)[0]
    db = get_db()
    set_setting(db, uid, "extra_count", extra_of(uid, day) + MORE)
    set_setting(db, uid, "extra_day", day)
    db.commit()
    return jsonify(summary(tz))
