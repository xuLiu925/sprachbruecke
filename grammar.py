"""语法题库: 手写题和以后扩充的题存数据库 grammar_questions(语法说明、速查表、程序生成的题还在前端)

管理员可以用 AI 出草稿、手动加题、修改、停用; 别的用户只能做题和报错。
AI 的题一律经过 clean_question 检查, 但系统判断不了语法对不对, 所以页面上标“AI 生成，未核对”。
"""
import json
import re

from flask import Blueprint, jsonify, request

from auth import admin_required, is_admin
from custom_lessons import CHINESE, TOKEN, AiError, api_key, call_gemini, extract_json, text
from database import get_db, now_str
from helpers import current_user_id, err, json_body, login_required

bp = Blueprint("grammar", __name__)

# 能用题库的知识点。options 对这个知识点的每道题都一样, 按钮顺序不变
TOPICS = {
    "art-def": {
        "title": "定冠词", "level": "A2", "options": ["der", "die", "das", "den", "dem", "des"],
        "rule": "考定冠词的性、数、格。覆盖第一到第四格。",
    },
}
MAX_ROUND = 30
MAX_DRAFTS = 30
COLS = "id, prompt, answer, hint, explain, zh, source"
HINT_NOUN = re.compile(r"(der|die|das) ([^\s·]+)")   # 定冠词题的提示开头写着名词原形: der Karton · 这里是复数


def topic_of(name):
    return TOPICS.get(name)


def public_question(row, topic):
    return {**dict(row), "options": topic["options"], "fixed": True}


@bp.route("/api/grammar/<name>/quiz")
@login_required
def quiz(name):
    topic = topic_of(name)
    if topic is None:
        return err("知识点不存在", 404)
    try:
        n = min(max(int(request.args.get("n", "10")), 1), MAX_ROUND)
    except ValueError:
        return err("题数无效")
    rows = get_db().execute(
        f"SELECT {COLS} FROM grammar_questions WHERE topic = ? AND status = 'active' ORDER BY RANDOM() LIMIT ?",
        (name, n),
    ).fetchall()
    return jsonify({"questions": [public_question(r, topic) for r in rows],
                    "can": is_admin(current_user_id()), "ai": bool(api_key())})


@bp.route("/api/grammar/questions/<int:qid>/report", methods=["POST"])
@login_required
def report(qid):
    """报错 {reason}: 记下问题, 管理员在题库页能看到"""
    data = json_body()
    reason = text(data.get("reason"), 200) if data else ""
    if len(reason) < 2:
        return err("请写一下哪里有问题")
    db = get_db()
    if db.execute("SELECT 1 FROM grammar_questions WHERE id = ?", (qid,)).fetchone() is None:
        return err("题目不存在", 404)
    db.execute(
        "INSERT INTO content_reports (kind, sent_key, reason, reported_by, created_at) VALUES ('grammar',?,?,?,?) "
        "ON CONFLICT(kind, sent_key) DO UPDATE SET reason = excluded.reason, "
        "reported_by = excluded.reported_by, created_at = excluded.created_at",
        (str(qid), reason, current_user_id(), now_str()),
    )
    db.commit()
    return jsonify({"ok": True})


# ---------- 检查题目 ----------
def clean_question(d, topic):
    """返回 (干净的题目, 错误)。只留下认识的字段"""
    if not isinstance(d, dict):
        return None, "题目格式错误"
    prompt, answer = text(d.get("prompt"), 200), text(d.get("answer"), 30)
    hint, explain, zh = text(d.get("hint"), 100), text(d.get("explain"), 300), text(d.get("zh"), 300)
    if prompt.count("___") != 1:
        return None, "题目里要有且只有一个 ___"
    if CHINESE.search(prompt) or not TOKEN.search(prompt):
        return None, f"题目要是德语句子：{prompt[:30]}"
    if answer not in topic["options"]:
        return None, f"答案不在选项里：{prompt[:30]}"
    if not CHINESE.search(explain) or not CHINESE.search(zh):
        return None, f"缺少中文解释或翻译：{prompt[:30]}"
    return {"prompt": prompt, "answer": answer, "hint": hint, "explain": explain, "zh": zh}, None


def clean_questions(data, topic):
    """AI 的结果: 去掉不合格的题, 全都不合格才算失败"""
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None, "内容格式不对"
    good = [q for q, e in (clean_question(x, topic) for x in items[:MAX_DRAFTS]) if q]
    if not good:
        return None, "没有合格的题"
    return good, None


def build_prompt(topic, want, n):
    options = "、".join(topic["options"])
    return f"""你是德语老师，为在德国海外仓工作的中文学习者出语法选择题。

知识点：{topic["title"]}（{topic["rule"]}）
水平：{topic["level"]}
要求：{want}
数量：{n} 道

规则：
- 每题是一句仓库工作场景的德语，用 ___ 代替要填的词，只有一个空。
- 选项固定是：{options}。answer 必须是其中一个，而且只有这一个答案是对的。
- 不要出有两个答案都说得通的题。特别注意单复数同形的名词（Scanner、Artikel、Hubwagen、Stapler）：放在第四格、第三格的句子里时，单复数都可能成立，不要用。
- hint 写这个名词和性别，如 "die Palette · 阴性"，不要写第几格。
- explain 用中文说明为什么是这个答案。zh 是整句的中文翻译。
- 德语必须正确、自然，不要写真实公司、客户和订单信息。
- 只输出一个 JSON 对象，不要 Markdown 代码块，不要其他文字。

JSON 格式：
{{"questions": [{{"prompt": "Die Ware steht in ___ Halle.", "answer": "der", "hint": "die Halle · 阴性", "explain": "in 表示位置 + 第三格；阴性第三格 → der", "zh": "货物放在库房里。"}}]}}"""


def read_request(topic):
    """{request, n} → (要求, 数量, 错误)"""
    data = json_body()
    if data is None:
        return None, None, "请求格式错误"
    want = text(data.get("request"), 300)
    n = data.get("n", 5)
    if len(want) < 2:
        return None, None, "请写一下想出什么题"
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 10:
        return None, None, "一次出 1–10 题"
    return want, n, None


# ---------- 管理员: 题库 ----------
@bp.route("/api/grammar/<name>/questions")
@admin_required
def list_questions(name):
    if topic_of(name) is None:
        return err("知识点不存在", 404)
    rows = get_db().execute(
        f"SELECT q.id, q.prompt, q.answer, q.hint, q.explain, q.zh, q.source, q.status, r.reason AS report "
        "FROM grammar_questions q LEFT JOIN content_reports r ON r.kind = 'grammar' AND r.sent_key = CAST(q.id AS TEXT) "
        "WHERE q.topic = ? ORDER BY r.reason IS NULL, q.status, q.id DESC",
        (name,),
    ).fetchall()
    return jsonify({"questions": [dict(r) for r in rows], "options": TOPICS[name]["options"]})


@bp.route("/api/grammar/<name>/prompt", methods=["POST"])
@admin_required
def prompt_text(name):
    topic = topic_of(name)
    if topic is None:
        return err("知识点不存在", 404)
    want, n, e = read_request(topic)
    if e:
        return err(e)
    return jsonify({"prompt": build_prompt(topic, want, n)})


@bp.route("/api/grammar/<name>/generate", methods=["POST"])
@admin_required
def generate(name):
    """AI 出草稿, 不保存"""
    topic = topic_of(name)
    if topic is None:
        return err("知识点不存在", 404)
    want, n, e = read_request(topic)
    if e:
        return err(e)
    try:
        raw = call_gemini(build_prompt(topic, want, n))
    except AiError as ex:
        return err(ex.msg, ex.code)
    questions, e = clean_questions(extract_json(raw), topic)
    if e:
        return err("AI 出题不完整（" + e + "），请再试一次", 502)
    return jsonify({"questions": [{**q, "source": "ai"} for q in questions]})


@bp.route("/api/grammar/<name>/check", methods=["POST"])
@admin_required
def check(name):
    """检查从免费 AI 粘贴回来的题 {text}, 通过就返回草稿, 不保存"""
    topic = topic_of(name)
    if topic is None:
        return err("知识点不存在", 404)
    data = json_body()
    parsed = extract_json(data.get("text")) if data else None
    if parsed is None:
        return err("没有找到完整的 JSON，请把 AI 的回复全部复制过来")
    questions, e = clean_questions(parsed, topic)
    if e:
        return err(e)
    return jsonify({"questions": [{**q, "source": "ai"} for q in questions]})


@bp.route("/api/grammar/<name>/questions", methods=["POST"])
@admin_required
def save(name):
    """保存 {questions: [...]}: 带 id 的是修改, 其他是新题。一题不合格就全部不保存, 题目重复的跳过"""
    topic = topic_of(name)
    if topic is None:
        return err("知识点不存在", 404)
    data = json_body()
    items = data.get("questions") if data else None
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_DRAFTS:
        return err(f"一次保存 1–{MAX_DRAFTS} 题")
    cleaned = []
    for item in items:
        q, e = clean_question(item, topic)
        if e:
            return err(e)
        cleaned.append((q, item))
    db = get_db()
    saved = skipped = 0
    for q, item in cleaned:
        fields = (q["prompt"], q["answer"], q["hint"], q["explain"], q["zh"])
        qid = item.get("id")
        if qid is None:
            source = "ai" if item.get("source") == "ai" else "manual"
            cur = db.execute(
                "INSERT OR IGNORE INTO grammar_questions (topic, prompt, answer, hint, explain, zh, source, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)", (name, *fields, source, now_str()),
            )
        else:
            cur = db.execute(
                "UPDATE OR IGNORE grammar_questions SET prompt = ?, answer = ?, hint = ?, explain = ?, zh = ? "
                "WHERE id = ? AND topic = ?", (*fields, qid, name),
            )
            db.execute("DELETE FROM content_reports WHERE kind = 'grammar' AND sent_key = ?", (str(qid),))
        saved += cur.rowcount
        skipped += 1 - cur.rowcount
    db.commit()
    return jsonify({"saved": saved, "skipped": skipped, "missing": outside_warehouse(q["hint"] for q, _item in cleaned)})


def outside_warehouse(hints):
    """这些题的名词不在海外仓词汇里(提示写法不对的也算), 选这本书时练不到"""
    missing = []
    for hint in hints:
        m = HINT_NOUN.match(hint)
        found = m and get_db().execute(
            "SELECT 1 FROM words w JOIN word_books b ON b.word_id = w.id AND b.book = 'warehouse' "
            "WHERE w.gender = ? AND w.german = ? LIMIT 1", m.groups(),
        ).fetchone()
        if not found:
            missing.append(m.group(2) if m else hint)
    return sorted(set(missing))


@bp.route("/api/grammar/questions/<int:qid>/status", methods=["POST"])
@admin_required
def set_status(qid):
    """停用 / 启用 {status: active|hidden}。停用的题不再出现, 但保留着"""
    data = json_body()
    status = data.get("status") if data else None
    if status not in ("active", "hidden"):
        return err("状态无效")
    db = get_db()
    cur = db.execute("UPDATE grammar_questions SET status = ? WHERE id = ?", (status, qid))
    if status == "hidden":
        db.execute("DELETE FROM content_reports WHERE kind = 'grammar' AND sent_key = ?", (str(qid),))
    db.commit()
    if not cur.rowcount:
        return err("题目不存在", 404)
    return jsonify({"ok": True})
