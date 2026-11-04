"""意见反馈和报错汇总

所有用户: 在「我的」页写意见反馈(页面打不开、建议之类, 不针对某道题), 存 feedback 表。
管理员: 一个列表看全部反馈和各处的报错(content_reports: 讲解、替换练习、语法题库、自动出的题、构词解释),
处理完点“已处理”: 报错直接删掉(和各处“清除报错”一样), 意见反馈记下处理时间, 不再显示。
"""
from content_filter import MSG as BLOCK_MSG, blocked
from flask import Blueprint, jsonify

from auth import admin_required
from database import get_db, now_str
from helpers import current_user_id, err, json_body, login_required

bp = Blueprint("feedback", __name__)

MAX_TEXT = 1000
DAILY_MAX = 20      # 每人每天最多写几条, 防止误操作刷屏

KIND_NAMES = {
    "note": "句子讲解",
    "drill": "替换练习",
    "grammar": "语法题库",
    "noun": "自动出的题",
    "parts": "构词解释",
}


@bp.route("/api/feedback", methods=["POST"])
@login_required
def submit():
    """{text, page}: page 是写反馈时所在的页面(前端的 #名字), 方便知道是哪里出的问题"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    text = str(data.get("text") or "").strip()
    page = str(data.get("page") or "").strip()[:50]
    if len(text) < 2:
        return err("请写一下遇到了什么问题")
    if len(text) > MAX_TEXT:
        return err(f"最多 {MAX_TEXT} 个字")
    if blocked(text):
        return err(BLOCK_MSG)
    db = get_db()
    uid = current_user_id()
    n = db.execute("SELECT COUNT(*) FROM feedback WHERE user_id = ? AND created_at >= ?",
                   (uid, now_str()[:10])).fetchone()[0]
    if n >= DAILY_MAX:
        return err("今天写得太多了, 明天再来", 429)
    db.execute("INSERT INTO feedback (user_id, text, page, created_at) VALUES (?,?,?,?)",
               (uid, text, page, now_str()))
    db.commit()
    return jsonify({"ok": True})


def report_target(db, kind, key):
    """报错对应的内容: 返回 (显示的文字, 词编号或 None)。内容已经被删掉时文字为空"""
    if kind in ("note", "drill"):
        table = "sentence_notes" if kind == "note" else "sentence_drills"
        row = db.execute(f"SELECT de FROM {table} WHERE sent_key = ?", (key,)).fetchone()
        return (row["de"] if row else ""), None
    if kind == "grammar":
        row = db.execute("SELECT topic, prompt, answer FROM grammar_questions WHERE id = ?",
                         (int(key) if key.isdigit() else -1,)).fetchone()
        return (f"{row['prompt']}（答案 {row['answer']}，知识点 {row['topic']}）" if row else ""), None
    if kind == "noun":
        row = db.execute("SELECT id, german, gender FROM words WHERE id = ?",
                         (int(key) if key.isdigit() else -1,)).fetchone()
        if row is None:
            return "", None
        return " ".join(x for x in (row["gender"], row["german"]) if x), row["id"]
    return key, None    # parts: 键就是词


@bp.route("/api/admin/feedback")
@admin_required
def admin_list():
    """反馈和报错, 新的在前。type = feedback(意见反馈, 带 id) / report(报错, 带 kind + key)"""
    db = get_db()
    items = []
    for r in db.execute("SELECT f.id, f.text, f.page, f.created_at, u.username FROM feedback f "
                        "LEFT JOIN users u ON u.id = f.user_id WHERE f.done_at IS NULL"):
        items.append({"type": "feedback", "id": r["id"], "kind_name": "意见反馈", "target": "",
                      "reason": r["text"], "page": r["page"], "user": r["username"],
                      "created_at": r["created_at"]})
    for r in db.execute("SELECT r.kind, r.sent_key, r.reason, r.created_at, u.username FROM content_reports r "
                        "LEFT JOIN users u ON u.id = r.reported_by"):
        target, word_id = report_target(db, r["kind"], r["sent_key"])
        reason = r["reason"]
        if r["kind"] == "noun" and "｜" in reason:     # 自动出的题: 存的是“题目｜原因”
            prompt, reason = reason.split("｜", 1)
            target = f"{target}：{prompt}" if prompt else target
        items.append({"type": "report", "kind": r["kind"], "key": r["sent_key"],
                      "kind_name": KIND_NAMES.get(r["kind"], r["kind"]), "target": target,
                      "word_id": word_id, "reason": reason, "user": r["username"],
                      "created_at": r["created_at"]})
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return jsonify({"items": items})


@bp.route("/api/admin/feedback/done", methods=["POST"])
@admin_required
def admin_done():
    """{type: feedback, id} 或 {type: report, kind, key}"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    db = get_db()
    if data.get("type") == "feedback":
        n = db.execute("UPDATE feedback SET done_at = ? WHERE id = ? AND done_at IS NULL",
                       (now_str(), data.get("id"))).rowcount
    elif data.get("type") == "report":
        n = db.execute("DELETE FROM content_reports WHERE kind = ? AND sent_key = ?",
                       (str(data.get("kind") or ""), str(data.get("key") or ""))).rowcount
    else:
        return err("type 无效")
    db.commit()
    return jsonify({"done": n})
