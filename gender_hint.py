"""词性解释: 说明一个名词为什么是这个冠词, 并举几个同类词

第一层是规则, 不用 AI。顺序: 明确的词尾 > 复合词 > 动词变来的名词 > 时间和方位 > -e 结尾。
规则对不上这个词的实际冠词时就跳过, 所以 der Sprung 不会被说成 -ung。
复合词要求前半段是真实的词, 最后一个词的冠词也一致, 防止把词随便拆开。

第二层是 AI 联想记忆: 规则判断不了时才显示, 用户点了才生成, 保存在 gender_memos。
联想只是帮助记忆, 不是语法原因, 页面上要写明。
"""
import re

from flask import Blueprint, jsonify, request

from ai_inputs import known_genders, word_meaning
from content_filter import AI_MSG, SAFETY_RULE, added
from auth import admin_required, is_admin
from billing import ai_block, ai_can_generate, ai_done
from custom_lessons import CHINESE, AiError, api_key, call_gemini, extract_json, text
from database import get_db, now_str
from dictionary import all_glossary
from helpers import current_user_id, err, json_body, login_required
from trial import arg_word, guest_open

bp = Blueprint("gender_hint", __name__)

GENDERS = ("der", "die", "das")
NO_RULE = "这个词没有明显规律，要和冠词一起记"
EXAMPLES = 3
# (词尾, 冠词, 说明里的说法)
ENDINGS = [
    ("ung", "die", "基本都是"), ("heit", "die", "基本都是"), ("keit", "die", "基本都是"), ("schaft", "die", "基本都是"),
    ("tion", "die", "基本都是"), ("tät", "die", "基本都是"), ("chen", "das", "都是"), ("lein", "das", "都是"),
    ("ismus", "der", "基本都是"), ("ling", "der", "大多是"), ("ist", "der", "大多是"), ("ment", "das", "大多是"),
    ("enz", "die", "大多是"), ("anz", "die", "大多是"), ("ei", "die", "大多是"), ("ik", "die", "大多是"),
    ("ie", "die", "大多是"), ("ur", "die", "大多是"), ("um", "das", "大多是"),
]
TIME_WORDS = {
    "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag",
    "januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november",
    "dezember", "frühling", "sommer", "herbst", "winter", "norden", "süden", "osten", "westen",
}
LINKS = ("s", "es", "n", "en", "e")   # 连接成分: Arbeit-s-platz
MIN_PART = 3


def ending_rule(word, gender):
    low = word.lower()
    for end, art, how in ENDINGS:
        if art == gender and low.endswith(end) and len(low) > len(end) + 2:
            return f"以 -{end} 结尾的名词{how} {art}", end, None
    return None


def stems(prefix):
    """复合词前半段可能的原形: 本身, 去掉连接成分, 动词词干加 -n / -en(Liefer → liefern)"""
    low = prefix.lower()
    out = {low, low + "n", low + "en"}
    out.update(low[:-len(x)] for x in LINKS if low.endswith(x) and len(low) - len(x) >= MIN_PART)
    return out


def compound_rule(word, gender):
    """从最长的后半段开始找: 冠词相同的名词 + 前半段也是真实的词。情景课的仓储词也算"""
    db = get_db()
    glossary = all_glossary()
    known = {g["german"].lower() for g in glossary} | {g["plural"].lower() for g in glossary if g["plural"]}
    tails = {g["german"] for g in glossary if g["gender"] == gender}
    for i in range(MIN_PART, len(word) - MIN_PART + 1):
        tail = word[i:].capitalize()
        hit = tail in tails or db.execute(
            "SELECT 1 FROM words WHERE german = ? AND gender = ? AND status = 'public' LIMIT 1", (tail, gender),
        ).fetchone()
        if not hit:
            continue
        names = sorted(stems(word[:i]))
        marks = ",".join("?" * len(names))
        real = known & set(names) or db.execute(
            f"SELECT 1 FROM words WHERE status = 'public' AND (lower(german) IN ({marks}) OR lower(plural) IN ({marks})) LIMIT 1",
            names + names,
        ).fetchone()
        if real:
            return f"复合词，词性看最后一个词：{gender} {tail}", tail.lower(), tail
    return None


def is_verb(name):
    return get_db().execute("SELECT 1 FROM words WHERE german = ? AND pos LIKE '动词%' AND status = 'public' LIMIT 1",
                            (name,)).fetchone() is not None


def verb_rule(word, gender):
    low = word[:1].lower() + word[1:]
    if gender == "das" and low.endswith("en") and is_verb(low):
        return "由动词原形变来的名词都是 das", None, None
    if gender == "der" and low.endswith("er") and len(low) > 4 and is_verb(low[:-2] + "en"):
        return "动词加 -er 表示人或工具的名词大多是 der", "er", None
    return None


def analyze(word, gender):
    """返回 (说明, 同类词的词尾, 最后一个词); 没有规则时说明是 None"""
    word = word.strip().split(" ")[-1]
    found = ending_rule(word, gender) or compound_rule(word, gender) or verb_rule(word, gender)
    if found:
        return (*found, word)
    if gender == "der" and word.lower() in TIME_WORDS:
        return "星期、月份、季节和方位都是 der", None, None, word
    if gender == "die" and word.endswith("e") and len(word) > 3:
        return "以 -e 结尾的名词大多是 die，但有例外", "e", None, word
    return None, None, None, word


def short_meaning(meaning):
    return re.split(r"[，,；;、(（]", meaning)[0].strip()[:12]


def examples_of(word, gender, ending, tail):
    """常用的同类词, 最后一个词排最前面。都来自词库, 点开能看详情"""
    if not ending:
        return []
    agent = ending == "er" and tail is None        # 动词加 -er: Vater、Bruder 只是碰巧以 -er 结尾, 不能当同类词
    rows = get_db().execute(
        "SELECT w.german, w.gender, w.meaning FROM words w LEFT JOIN word_levels l ON l.word_id = w.id "
        "WHERE w.status = 'public' AND w.gender = ? AND w.german LIKE ? AND w.german != ? "
        "ORDER BY w.german = ? DESC, COALESCE(l.rank, 1000000000), length(w.german) LIMIT ?",
        (gender, "%" + ending, word, tail or "", 200 if agent else EXAMPLES),
    ).fetchall()
    if agent:
        rows = [r for r in rows if is_verb(r["german"][:1].lower() + r["german"][1:-2] + "en")][:EXAMPLES]
    return [{"german": r["german"], "gender": r["gender"], "meaning": short_meaning(r["meaning"])} for r in rows]


def load_memo(word, gender):
    row = get_db().execute("SELECT memo FROM gender_memos WHERE german = ? AND gender = ?", (word, gender)).fetchone()
    return row["memo"] if row else None


def gender_reason(word, gender):
    return analyze(word, gender)[0] or NO_RULE


@bp.route("/api/gender_reason")
@guest_open(arg_word)   # 游客能看试学的词
def reason():
    german, gender = request.args.get("german", "").strip(), request.args.get("gender", "")
    if not german or len(german) > 100 or gender not in GENDERS:
        return err("参数无效")
    text_, ending, tail, word = analyze(german, gender)
    out = {"reason": text_ or NO_RULE, "no_rule": text_ is None, "examples": examples_of(word, gender, ending, tail)}
    if text_ is None:
        uid = current_user_id()
        out.update(memo=load_memo(word, gender), can=uid is not None and is_admin(uid),
                   gen=uid is not None and ai_can_generate(uid), ai=bool(api_key()))
    return jsonify(out)


def build_prompt(german, gender, meaning):
    colors = {"der": "蓝色", "die": "红色", "das": "绿色"}
    return f"""你在帮在德国生活、学习或工作的中文学习者记住德语名词的冠词。这个词没有明显的语法规律，所以需要一个联想。

词：{gender} {german}
意思：{meaning or "（未提供）"}
软件里 {gender} 的颜色是{colors[gender]}。

规则：
- 用一句简短的中文写一个好记的联想，把这个词的意思和“{gender}”或{colors[gender]}联系起来，30 字以内。
- 尽量用日常生活、学习或工作的场景。
{SAFETY_RULE}
- 不要声称这是语法规则，不要编造词源或“因为……所以是 {gender}”。
- 不要写真实公司、客户信息。
- 只输出一个 JSON 对象，不要 Markdown 代码块，不要其他文字。

JSON 格式：
{{"memo": "蓝色的 der 桌子上放着送货单"}}"""


def clean_memo(data):
    memo = text(data.get("memo"), 80) if isinstance(data, dict) else ""
    return memo if len(memo) >= 4 and CHINESE.search(memo) else None


@bp.route("/api/gender_memo", methods=["POST"])
@login_required
def memo():
    """生成联想记忆 {german, gender, meaning, again}: 已保存就直接返回, again = 换一个。有规律的词不生成"""
    data = json_body()
    if data is None:
        return err("请求格式错误")
    german, gender = text(data.get("german"), 100), data.get("gender")
    if not german or gender not in GENDERS:
        return err("参数无效")
    word = german.split(" ")[-1]
    if analyze(word, gender)[0]:
        return err("这个词有规律可循，不用联想")
    genders = known_genders(word)
    if genders and gender not in genders:       # 词库 / 词典里有这个词, 冠词对不上就不生成
        return err("这个词的冠词不对")
    uid = current_user_id()
    if data.get("again") and not is_admin(uid):   # 换一个只有管理员能用
        return err("没有权限", 403)
    if not data.get("again"):
        saved = load_memo(word, gender)
        if saved:
            return jsonify({"memo": saved})
    blocked = ai_block(uid, f"memo:{gender}:{word}", generate=True)
    if blocked:
        return blocked
    try:
        # 释义用词库 / 词典里的, 不信前端传的(联想记忆大家共用)
        meaning = word_meaning(word, gender)[:100]
        raw = call_gemini(build_prompt(word, gender, meaning))
    except AiError as ex:
        return err(ex.msg, ex.code)
    result = clean_memo(extract_json(raw))
    if result is None:
        return err("AI 没写好，请再试一次", 502)
    if added(result, word, meaning):
        return err(AI_MSG, 502)
    db = get_db()
    db.execute(
        "INSERT INTO gender_memos (german, gender, memo, created_at) VALUES (?,?,?,?) "
        "ON CONFLICT(german, gender) DO UPDATE SET memo = excluded.memo, created_at = excluded.created_at",
        (word, gender, result, now_str()),
    )
    db.commit()
    ai_done(uid, f"memo:{gender}:{word}", generated=True)
    return jsonify({"memo": result})
