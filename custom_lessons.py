"""自建工作对话: 用中文描述场景, AI 写成课程, 用户确认后保存。保存后和自带的情景课用同一套页面

AI 只在后端调用, 只有管理员能用(防止别人消耗额度)。Key 来自环境变量 GEMINI_API_KEY 或文件 .gemini_key,
不进版本库。没有 Key 或额度用完时, 可以把提示词复制到免费 AI, 再把返回的 JSON 粘贴回来(/check)。
AI 的结果不可信: 一律经过 clean_lesson 检查, 只留下认识的字段。
"""
import json
import os
import re
import urllib.error
import urllib.request

from flask import Blueprint, jsonify, request

from auth import admin_required
from database import BASE, get_db, now_str
from helpers import current_user_id, err, json_body, login_required
from lessons import ROLE, as_lesson, my_lessons, roleplay_items

bp = Blueprint("custom_lessons", __name__)

KEY_FILE = os.path.join(BASE, ".gemini_key")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
LEVELS = ("A1", "A2", "B1")
GENDERS = ("", "der", "die", "das")
MIN_ROLEPLAY = 2       # 至少有几次「对方说 → Li 回答」
TOKEN = re.compile(r"[A-Za-zÄÖÜäöüß]+(?:-[A-Za-zÄÖÜäöüß]+)*")
CHINESE = re.compile(r"[一-鿿]")

SCHEMA_TEXT = """{
  "level": "A2",
  "title": "中文课名，10 字以内",
  "scene": "用一句中文说明场景",
  "lines": [{"who": "司机", "de": "德语句子", "zh": "中文翻译",
             "map": {"句中的词": "原形，只给可分动词、过去分词、不规则变位的词；没有就省略这个字段"}}],
  "glossary": [{"german": "Lieferschein", "gender": "der", "pos": "名词", "plural": "Lieferscheine", "meaning": "送货单"}],
  "cloze": [{"line": 1, "answer": "句子里原样出现且只出现一次的一个词", "base": "原形", "gender": "", "meaning": "中文"}],
  "task": {"prompt": "中文任务：让学习者用德语写 3 句", "tips": ["句型提示"],
           "model": [{"de": "参考答案", "zh": "中文"}]}
}"""


def build_prompt(level, want):
    return f"""你是德语老师，为在德国海外仓工作的中文学习者写一段工作对话。

场景要求：{want}
德语水平：{level}（词汇和语法不要超过这个水平）

规则：
- 学习者的角色固定叫 "{ROLE}"，对方用中文身份或德语名字，如 "司机"、"Anna"。
- 写 8–12 句，{ROLE} 和对方基本轮流说话，{ROLE} 至少回答 3 次。
- 德语必须正确、自然，是仓库工作中真实会说的话。句子不要太长。
- 不要写真实公司、客户、地址和订单信息，全部虚构。
- glossary 只列本课的仓储和工作词汇，名词必须有 gender，gender 只能是 der、die、das 或空字符串。
- cloze 出 3–4 题，line 是 lines 的下标（从 0 开始）。
- task 的 model 给 3 句德语参考答案。
- 只输出一个 JSON 对象，不要 Markdown 代码块，不要其他文字。

JSON 格式：
{SCHEMA_TEXT}"""


def text(v, limit):
    return v.strip()[:limit] if isinstance(v, str) else ""


def extract_json(raw):
    """AI 有时会包上 ```json 或多写几句话, 只取最外层的 {...}"""
    if not isinstance(raw, str):
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def clean_lines(raw):
    if not isinstance(raw, list) or not 4 <= len(raw) <= 16:
        return None, "对话要有 4–16 句"
    lines = []
    for x in raw:
        if not isinstance(x, dict):
            return None, "对话格式错误"
        who, de, zh = text(x.get("who"), 20), text(x.get("de"), 300), text(x.get("zh"), 300)
        if not who or not de or not zh:
            return None, "每句都要有说话人、德语和中文"
        if CHINESE.search(de) or not TOKEN.search(de):
            return None, f"这句不是德语：{de[:30]}"
        if not CHINESE.search(zh):
            return None, f"这句缺中文翻译：{de[:30]}"
        line = {"who": who, "de": de, "zh": zh}
        tokens = set(TOKEN.findall(de))
        mapping = x.get("map")
        if isinstance(mapping, dict):
            mapping = {k: text(v, 60) for k, v in mapping.items() if k in tokens and text(v, 60)}
            if mapping:
                line["map"] = mapping
        lines.append(line)
    return lines, None


def clean_glossary(raw):
    out, seen = [], set()
    for g in raw if isinstance(raw, list) else []:
        if not isinstance(g, dict):
            continue
        german, meaning = text(g.get("german"), 60), text(g.get("meaning"), 100)
        gender, pos = g.get("gender", ""), text(g.get("pos"), 20)
        if not german or not meaning or gender not in GENDERS or german.lower() in seen:
            continue
        if pos == "名词" and not gender:
            continue
        seen.add(german.lower())
        out.append({"german": german, "gender": gender, "pos": pos, "plural": text(g.get("plural"), 60),
                    "meaning": meaning})
    return out[:30]


def clean_cloze(raw, lines):
    """用户改过句子后, 对不上的题直接去掉"""
    out = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict):
            continue
        i, answer = c.get("line"), text(c.get("answer"), 60)
        if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(lines):
            continue
        base, meaning, gender = text(c.get("base"), 60), text(c.get("meaning"), 100), c.get("gender", "")
        if not base or not meaning or gender not in GENDERS or TOKEN.findall(lines[i]["de"]).count(answer) != 1:
            continue
        out.append({"line": i, "answer": answer, "base": base, "gender": gender, "meaning": meaning})
    return out[:6]


def clean_task(raw):
    if not isinstance(raw, dict):
        return None
    prompt = text(raw.get("prompt"), 300)
    tips = [text(t, 80) for t in raw.get("tips", []) if text(t, 80)] if isinstance(raw.get("tips"), list) else []
    model = []
    for m in raw.get("model", []) if isinstance(raw.get("model"), list) else []:
        if isinstance(m, dict) and text(m.get("de"), 300) and text(m.get("zh"), 300):
            model.append({"de": text(m.get("de"), 300), "zh": text(m.get("zh"), 300)})
    return {"prompt": prompt, "tips": tips[:5], "model": model[:5]} if prompt and model else None


def clean_lesson(d):
    """返回 (干净的课程, 错误信息)。level / title / scene 也在里面, 保存时拆开"""
    if not isinstance(d, dict):
        return None, "内容不是 JSON 对象"
    level, title, scene = d.get("level"), text(d.get("title"), 40), text(d.get("scene"), 200)
    if level not in LEVELS:
        return None, "级别只能是 A1 / A2 / B1"
    if not title or not scene:
        return None, "缺少课名或场景说明"
    lines, e = clean_lines(d.get("lines"))
    if e:
        return None, e
    lesson = {"id": "", "level": level, "title": title, "scene": scene, "lines": lines,
              "glossary": clean_glossary(d.get("glossary")), "cloze": clean_cloze(d.get("cloze"), lines),
              "task": clean_task(d.get("task"))}
    if lesson["task"] is None:
        return None, "缺少写作任务或参考答案"
    if len(roleplay_items(lesson)) < MIN_ROLEPLAY:
        return None, f"{ROLE} 的回答太少，至少要回答 {MIN_ROLEPLAY} 次"
    return lesson, None


def api_key():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    try:
        with open(KEY_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


class AiError(Exception):
    """msg 给用户看; 绝不能带上 Key"""
    def __init__(self, msg, code=502):
        super().__init__(msg)
        self.msg, self.code = msg, code


def call_gemini(prompt):
    """返回 AI 的文字。Key 放在请求头里, 不进网址(网址容易进日志)"""
    key = api_key()
    if not key:
        raise AiError("还没有配置 Gemini API Key", 503)
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}}
    req = urllib.request.Request(
        GEMINI_URL.format(model), data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise AiError("AI 免费额度暂时用完了，稍后再试，或用下面的“复制提示词”", 429)
        if e.code in (400, 401, 403):
            raise AiError("Gemini 拒绝了请求，请检查 API Key 和所在地区是否可用")
        if e.code == 404:
            raise AiError("这个 Gemini 模型不可用，请换一个模型")
        raise AiError("AI 服务暂时不可用，请稍后再试")
    except (OSError, ValueError):
        raise AiError("连接 AI 服务失败，请稍后再试")
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        raise AiError("AI 没有返回内容，换个说法再试一次")


def read_request():
    """{level, request} → (级别, 场景描述, 错误)"""
    data = json_body()
    if data is None:
        return None, None, "请求格式错误"
    level, want = data.get("level"), text(data.get("request"), 500)
    if level not in LEVELS:
        return None, None, "级别只能是 A1 / A2 / B1"
    if len(want) < 4:
        return None, None, "请先写一下想练的场景"
    return level, want, None


@bp.route("/api/custom_lessons")
@login_required
def list_custom():
    return jsonify({"lessons": my_lessons(), "ai": bool(api_key())})


@bp.route("/api/custom_lessons/prompt", methods=["POST"])
@login_required
def prompt_text():
    """不用 API: 把提示词给用户, 他自己粘贴到免费 AI"""
    level, want, e = read_request()
    if e:
        return err(e)
    return jsonify({"prompt": build_prompt(level, want)})


@bp.route("/api/custom_lessons/generate", methods=["POST"])
@admin_required
def generate():
    level, want, e = read_request()
    if e:
        return err(e)
    try:
        raw = call_gemini(build_prompt(level, want))
    except AiError as ex:
        return err(ex.msg, ex.code)
    data = extract_json(raw)
    if data is None:
        return err("AI 返回的格式不对，请重新生成", 502)
    data["level"] = level
    lesson, e = clean_lesson(data)
    if e:
        return err("AI 写得不完整（" + e + "），请重新生成", 502)
    return jsonify({"lesson": lesson})


@bp.route("/api/custom_lessons/check", methods=["POST"])
@login_required
def check():
    """检查用户从免费 AI 粘贴回来的文字 {level, text}, 通过就返回草稿"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    lesson_data = extract_json(data.get("text"))
    if lesson_data is None:
        return err("没有找到完整的 JSON，请把 AI 的回复全部复制过来")
    if data.get("level"):
        lesson_data["level"] = data["level"]
    lesson, e = clean_lesson(lesson_data)
    if e:
        return err(e)
    return jsonify({"lesson": lesson})


@bp.route("/api/custom_lessons", methods=["POST"])
@login_required
def save():
    data = json_body()
    if data is None:
        return err("请求格式错误")
    lesson, e = clean_lesson(data)
    if e:
        return err(e)
    body = {k: lesson[k] for k in ("lines", "glossary", "cloze", "task")}
    db = get_db()
    new_id = db.execute(
        "INSERT INTO custom_lessons (user_id, level, title, scene, data, created_at) VALUES (?,?,?,?,?,?)",
        (current_user_id(), lesson["level"], lesson["title"], lesson["scene"],
         json.dumps(body, ensure_ascii=False), now_str()),
    ).lastrowid
    db.commit()
    row = db.execute("SELECT * FROM custom_lessons WHERE id = ?", (new_id,)).fetchone()
    return jsonify({"lesson": as_lesson(row)})


@bp.route("/api/custom_lessons/<int:lesson_id>", methods=["DELETE"])
@login_required
def delete(lesson_id):
    db = get_db()
    cur = db.execute("DELETE FROM custom_lessons WHERE id = ? AND user_id = ?", (lesson_id, current_user_id()))
    db.commit()
    if not cur.rowcount:
        return err("课程不存在", 404)
    return jsonify({"ok": True})
