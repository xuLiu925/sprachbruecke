"""句子讲解: 词形、第几格、语序、为什么这样用、类似用法

讲解按句子保存在 sentence_notes(用德语原句的哈希做主键), 每句只生成一次, 所有课程共用。
生成和保存只有管理员能做(会消耗额度, 而且保存的内容大家共用); 没有 Key 时可以复制提示词到免费 AI, 再粘贴回来。
"""
import hashlib
import json
import re

from flask import Blueprint, jsonify, request

from auth import admin_required, is_admin
from custom_lessons import CHINESE, LEVELS, TOKEN, AiError, api_key, call_gemini, extract_json, text
from database import get_db, now_str
from helpers import current_user_id, err, json_body, login_required

bp = Blueprint("explain", __name__)

MAX_SENTENCE = 300
SCHEMA_TEXT = """{
  "words": [{"word": "句子里原样出现的词或短语，如 dem Hubwagen",
             "base": "原形，如 der Hubwagen",
             "form": "这里的形式，如 单数第三格 / wir 的现在时 / 过去分词",
             "why": "为什么是这个形式，一两句中文"}],
  "order": "用中文说明语序：动词在哪里，为什么这样放；没有特别之处就写一句话说明",
  "point": "这句最值得记住的一个语法点或固定搭配，一句中文",
  "similar": [{"de": "同样语法的海外仓工作例句", "zh": "中文翻译"}]
}"""


def key_of(de):
    return hashlib.sha1(de.encode("utf-8")).hexdigest()


def build_prompt(de, zh, level):
    return f"""你是德语语法老师，学习者的母语是中文，水平 {level}，在德国海外仓工作。请讲解这句德语。

德语：{de}
中文：{zh}

规则：
- 用简单的中文解释，德语术语后面加中文。
- 讲解句子里的主要名词短语（第几格、单复数、冠词为什么这样变）、动词（人称、时态、是否可分）、介词（支配第几格）和固定搭配。
- 格、时态和语法规则必须准确；不确定时不要编造。
- words 里的 word 必须和句子中的写法完全一样。
- similar 给 2–3 个例句，必须用同样的语法结构，内容是仓库工作场景，水平不超过 {level}。
- 只输出一个 JSON 对象，不要 Markdown 代码块，不要其他文字。

JSON 格式：
{SCHEMA_TEXT}"""


def clean_note(data, de):
    """返回 (讲解, 错误)。词组必须真的来自这句话, 防止 AI 讲别的句子"""
    if not isinstance(data, dict):
        return None, "内容不是 JSON 对象"
    sentence = {t.lower() for t in TOKEN.findall(de)}
    words = []
    for w in data.get("words") if isinstance(data.get("words"), list) else []:
        if not isinstance(w, dict):
            continue
        word, base, form, why = (text(w.get(k), n) for k, n in
                                 (("word", 100), ("base", 100), ("form", 100), ("why", 300)))
        tokens = [t.lower() for t in TOKEN.findall(word)]
        if word and form and why and tokens and all(t in sentence for t in tokens):
            words.append({"word": word, "base": base, "form": form, "why": why})
    similar = []
    for s in data.get("similar") if isinstance(data.get("similar"), list) else []:
        if not isinstance(s, dict):
            continue
        sde, szh = text(s.get("de"), 300), text(s.get("zh"), 300)
        if sde and szh and not CHINESE.search(sde) and CHINESE.search(szh):
            similar.append({"de": sde, "zh": szh})
    if not words:
        return None, "讲解里没有这句话的词"
    if not similar:
        return None, "缺少类似例句"
    return {"words": words[:12], "order": text(data.get("order"), 400), "point": text(data.get("point"), 300),
            "similar": similar[:3]}, None


def read_sentence(data):
    """{de, zh, level} → (de, zh, level, 错误)"""
    if data is None:
        return None, None, None, "请求格式错误"
    de, zh, level = text(data.get("de"), MAX_SENTENCE + 1), text(data.get("zh"), MAX_SENTENCE), data.get("level")
    if not de or len(de) > MAX_SENTENCE or CHINESE.search(de) or not TOKEN.search(de):
        return None, None, None, "句子无效"
    if level not in LEVELS:
        return None, None, None, "级别无效"
    return de, zh, level, None


def load_note(de):
    row = get_db().execute("SELECT data FROM sentence_notes WHERE sent_key = ?", (key_of(de),)).fetchone()
    return json.loads(row["data"]) if row else None


def save_note(de, note):
    db = get_db()
    db.execute(
        "INSERT INTO sentence_notes (sent_key, de, data, created_at) VALUES (?,?,?,?) "
        "ON CONFLICT(sent_key) DO UPDATE SET data = excluded.data, created_at = excluded.created_at",
        (key_of(de), de, json.dumps(note, ensure_ascii=False), now_str()),
    )
    db.commit()


@bp.route("/api/explain")
@login_required
def get_note():
    """?de=句子 → 已保存的讲解(没有是 null); can = 这个用户能生成; ai = 配置了 Key"""
    de = request.args.get("de", "").strip()
    if not de or len(de) > MAX_SENTENCE:
        return err("句子无效")
    return jsonify({"note": load_note(de), "can": is_admin(current_user_id()), "ai": bool(api_key())})


@bp.route("/api/explain/prompt", methods=["POST"])
@admin_required
def prompt_text():
    de, zh, level, e = read_sentence(json_body())
    if e:
        return err(e)
    return jsonify({"prompt": build_prompt(de, zh, level)})


@bp.route("/api/explain/generate", methods=["POST"])
@admin_required
def generate():
    """已经有讲解就直接返回, 不再调用 AI"""
    de, zh, level, e = read_sentence(json_body())
    if e:
        return err(e)
    saved = load_note(de)
    if saved:
        return jsonify({"note": saved})
    try:
        raw = call_gemini(build_prompt(de, zh, level))
    except AiError as ex:
        return err(ex.msg, ex.code)
    note, e = clean_note(extract_json(raw), de)
    if e:
        return err("AI 讲解不完整（" + e + "），请再试一次", 502)
    save_note(de, note)
    return jsonify({"note": note})


@bp.route("/api/explain/check", methods=["POST"])
@admin_required
def check():
    """保存用户从免费 AI 粘贴回来的讲解 {de, zh, level, text}"""
    body = json_body()
    de, _zh, _level, e = read_sentence(body)
    if e:
        return err(e)
    data = extract_json(body.get("text"))
    if data is None:
        return err("没有找到完整的 JSON，请把 AI 的回复全部复制过来")
    note, e = clean_note(data, de)
    if e:
        return err(e)
    save_note(de, note)
    return jsonify({"note": note})
