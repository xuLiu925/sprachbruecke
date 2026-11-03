"""构词解释: 把复合词、派生词、前缀词拆开, 说明每一部分和字面意思

用户点了按钮才调用 AI, 结果按词保存在 word_parts, 之后直接显示。不用拆的词也保存, 不会重复调用。
生成只有管理员能做(会消耗额度, 而且保存的内容大家共用)。
AI 可能讲错字面义, 程序只能检查结构: 各部分拼起来必须等于原词。
"""
import json
import re

from flask import Blueprint, jsonify, request

from auth import admin_required, is_admin
from custom_lessons import CHINESE, AiError, api_key, call_gemini, extract_json, text
from database import get_db, now_str
from explain import feedback_text
from helpers import current_user_id, err, json_body, login_required
from trial import arg_word, guest_open

bp = Blueprint("word_parts", __name__)

MAX_WORD = 100
MAX_STEPS = 3       # 最多拆三层: Wahrscheinlichkeit → wahrscheinlich → wahr + schein + lich
MAX_PARTS = 6
TYPES = ("word", "prefix", "suffix", "link")
CLARITY = ("clear", "partial", "memo")
SCHEMA_TEXT = """{
  "split": true,
  "steps": [
    {"word": "Wahrscheinlichkeit",
     "parts": [{"text": "wahrscheinlich", "base": "wahrscheinlich", "zh": "可能的", "type": "word"},
               {"text": "keit", "base": "keit", "zh": "把形容词变成名词，都是 die", "type": "suffix"}]},
    {"word": "wahrscheinlich",
     "parts": [{"text": "wahr", "base": "wahr", "zh": "真的", "type": "word"},
               {"text": "schein", "base": "scheinen", "zh": "看起来", "type": "word"},
               {"text": "lich", "base": "lich", "zh": "构成形容词", "type": "suffix"}]}
  ],
  "literal": "看起来是真的 → 很可能 → 可能性",
  "clarity": "partial"
}"""


def normalize(german):
    """保存时只看词本身, 不看冠词和 sich"""
    return re.sub(r"^(der|die|das|sich)\s+", "", text(german, MAX_WORD + 1), flags=re.I)


def letters(s):
    return "".join(ch for ch in s.casefold() if ch.isalpha())


def load_parts(word):
    row = get_db().execute("SELECT data FROM word_parts WHERE german = ?", (word,)).fetchone()
    return json.loads(row["data"]) if row else None


def report_reason(word):
    row = get_db().execute("SELECT reason FROM content_reports WHERE kind = 'parts' AND sent_key = ?",
                           (word,)).fetchone()
    return row["reason"] if row else None


def build_prompt(word, meaning, reason=None):
    return f"""你是德语构词法老师，学习者的母语是中文。请解释这个德语词是怎么构成的，帮助他记住。

词：{word}
意思：{meaning or "（未提供）"}
{feedback_text(reason)}
规则：
- 复合词拆成几个词，派生词拆成词 + 前缀或后缀。需要时再拆一层，最多 {MAX_STEPS} 层。
- 拆不开的简单词（如 Haus、gehen、schön）只输出 {{"split": false}}。词根加动词词尾 -en 不算可拆。
- steps 第一项的 word 必须是这个词。后面每一项的 word 必须是前面拆出来的部分。
- text 是这部分在词里的原样写法，所有 text 按顺序连起来必须正好等于 word（不分大小写）。不要写横线。
- base 是这部分的原形：Schulbuch 的 Schul 写 Schule，Wärme 的 Wärm 写 warm，词形没变就和 text 一样。
- type：word = 独立的词，prefix = 前缀，suffix = 后缀，link = 连接成分（如 Arbeitsplatz 的 s）。
- zh 用简短的中文写这部分的意思。link 写“连接成分”。
- literal 写字面意思怎么走到现在的词义，用 → 连接，30 字以内。
- clarity：clear = 看字面就能猜到词义；partial = 字面有关但要联想；memo = 词义已经转变，拆开只帮助记忆。
- 不要编造词源。不确定某部分的来历时，选 memo，不要硬讲。
- 只输出一个 JSON 对象，不要 Markdown 代码块，不要其他文字。

JSON 格式：
{SCHEMA_TEXT}"""


def clean_step(step):
    """一层拆分; 不合格返回 None。各部分拼起来必须等于这个词, 防止 AI 拆错或编造"""
    if not isinstance(step, dict) or not isinstance(step.get("parts"), list):
        return None
    word, raw = text(step.get("word"), MAX_WORD), step["parts"]
    if not 2 <= len(raw) <= MAX_PARTS:
        return None
    parts = []
    for p in raw:
        if not isinstance(p, dict):
            return None
        t, kind = text(p.get("text"), 50).strip("-"), p.get("type")
        zh = text(p.get("zh"), 40) or ("连接成分" if kind == "link" else "")
        if not letters(t) or kind not in TYPES or not CHINESE.search(zh):
            return None
        parts.append({"text": t, "base": text(p.get("base"), 50).strip("-") or t, "zh": zh, "type": kind})
    if letters("".join(p["text"] for p in parts)) != letters(word):
        return None
    return {"word": word, "parts": parts}


def clean_parts(data, word):
    """返回 (解释, 错误)。第二层以后不合格就去掉, 第一层必须合格"""
    if not isinstance(data, dict):
        return None, "内容不是 JSON 对象"
    if data.get("split") is False:
        return {"split": False}, None
    raw = data.get("steps") if isinstance(data.get("steps"), list) else []
    first = clean_step(raw[0]) if raw else None
    if first is None or letters(first["word"]) != letters(word):
        return None, "拆开后拼不回原词"
    literal, clarity = text(data.get("literal"), 80), data.get("clarity")
    if not CHINESE.search(literal):
        return None, "缺少字面意思"
    if clarity not in CLARITY:
        return None, "缺少判断"
    steps, known = [first], set()
    for s in raw[1:MAX_STEPS]:
        for p in steps[-1]["parts"]:
            known.update((letters(p["text"]), letters(p["base"])))
        step = clean_step(s)
        if step and letters(step["word"]) in known:
            steps.append(step)
    return {"split": True, "steps": steps, "literal": literal, "clarity": clarity}, None


def save_parts(word, parts):
    db = get_db()
    db.execute(
        "INSERT INTO word_parts (german, data, created_at) VALUES (?,?,?) "
        "ON CONFLICT(german) DO UPDATE SET data = excluded.data, created_at = excluded.created_at",
        (word, json.dumps(parts, ensure_ascii=False), now_str()),
    )
    db.execute("DELETE FROM content_reports WHERE kind = 'parts' AND sent_key = ?", (word,))
    db.commit()


@bp.route("/api/parts")
@guest_open(arg_word)   # 游客能看试学的词
def get_parts():
    """?german=词 → 已保存的解释(没有是 null); can = 这个用户能生成; ai = 配置了 Key"""
    word = normalize(request.args.get("german", ""))
    if not word or len(word) > MAX_WORD:
        return err("参数无效")
    return jsonify({"parts": load_parts(word), "report": report_reason(word),
                    "can": is_admin(current_user_id()), "ai": bool(api_key())})


@bp.route("/api/parts/generate", methods=["POST"])
@admin_required
def generate():
    """{german, meaning, again}: 已保存就直接返回; again = 重新生成, 带上报错内容, 失败时旧内容不动"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    word = normalize(data.get("german"))
    if not word or len(word) > MAX_WORD:
        return err("参数无效")
    if not data.get("again"):
        saved = load_parts(word)
        if saved:
            return jsonify({"parts": saved})
    try:
        raw = call_gemini(build_prompt(word, text(data.get("meaning"), 100), report_reason(word)))
    except AiError as ex:
        return err(ex.msg, ex.code)
    parts, e = clean_parts(extract_json(raw), word)
    if e:
        return err("AI 解释不合格（" + e + "），请再试一次", 502)
    save_parts(word, parts)
    return jsonify({"parts": parts})


@bp.route("/api/parts/report", methods=["POST"])
@login_required
def report():
    """报错 {german, reason}: 记下哪里有问题, 重新生成时告诉 AI"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    word, reason = normalize(data.get("german")), text(data.get("reason"), 200)
    if len(reason) < 2:
        return err("请写一下哪里有问题")
    if not load_parts(word):
        return err("这个词还没有解释", 404)
    db = get_db()
    db.execute(
        "INSERT INTO content_reports (kind, sent_key, reason, reported_by, created_at) VALUES ('parts',?,?,?,?) "
        "ON CONFLICT(kind, sent_key) DO UPDATE SET reason = excluded.reason, "
        "reported_by = excluded.reported_by, created_at = excluded.created_at",
        (word, reason, current_user_id(), now_str()),
    )
    db.commit()
    return jsonify({"ok": True})
