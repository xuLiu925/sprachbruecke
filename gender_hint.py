"""词性解释: 说明一个名词为什么是这个冠词。只用规则, 不用 AI

顺序: 明确的词尾 > 复合词 > 动词变来的名词 > 时间和方位 > -e 结尾。规则对不上这个词的实际冠词时就跳过,
所以 der Sprung 不会被说成 -ung。都判断不了时直接说没有明显规律, 不编原因。
复合词要求前半段是真实的词, 最后一个词的冠词也一致, 防止把词随便拆开。
"""
from flask import Blueprint, jsonify, request

from database import get_db
from helpers import err, login_required

bp = Blueprint("gender_hint", __name__)

GENDERS = ("der", "die", "das")
NO_RULE = "这个词没有明显规律，要和冠词一起记"
# (词尾, 冠词, 说明里的说法)
ENDINGS = [
    ("ung", "die", "基本都是"), ("heit", "die", "基本都是"), ("keit", "die", "基本都是"), ("schaft", "die", "基本都是"),
    ("tion", "die", "基本都是"), ("tät", "die", "基本都是"), ("chen", "das", "都是"), ("lein", "das", "都是"),
    ("ismus", "der", "基本都是"), ("ling", "der", "大多是"), ("ist", "der", "大多是"), ("ment", "das", "大多是"),
]
TIME_WORDS = {
    "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag",
    "januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november",
    "dezember", "frühling", "sommer", "herbst", "winter", "norden", "süden", "osten", "westen",
}
LINKS = ("s", "es", "n", "en", "e")   # 连接成分: Arbeit-s-platz
MIN_PART = 3


def ending_reason(word, gender):
    low = word.lower()
    for end, art, how in ENDINGS:
        if art == gender and low.endswith(end) and len(low) > len(end) + 2:
            return f"以 -{end} 结尾的名词{how} {art}"
    return None


def stems(prefix):
    """复合词前半段可能的原形: 本身, 去掉连接成分, 动词词干加 -n / -en(Liefer → liefern)"""
    low = prefix.lower()
    out = {low, low + "n", low + "en"}
    out.update(low[:-len(x)] for x in LINKS if low.endswith(x) and len(low) - len(x) >= MIN_PART)
    return out


def compound_reason(word, gender):
    """从最长的后半段开始找: 冠词相同的名词 + 前半段也是真实的词"""
    db = get_db()
    for i in range(MIN_PART, len(word) - MIN_PART + 1):
        tail = word[i:].capitalize()
        hit = db.execute("SELECT 1 FROM words WHERE german = ? AND gender = ? AND owner_id IS NULL LIMIT 1",
                         (tail, gender)).fetchone()
        if not hit:
            continue
        names = sorted(stems(word[:i]))
        marks = ",".join("?" * len(names))
        real = db.execute(
            f"SELECT 1 FROM words WHERE owner_id IS NULL AND (lower(german) IN ({marks}) OR lower(plural) IN ({marks})) LIMIT 1",
            names + names,
        ).fetchone()
        if real:
            return f"复合词，词性看最后一个词：{gender} {tail}"
    return None


def verb_reason(word, gender):
    if gender != "das" or not word.endswith("en"):
        return None
    hit = get_db().execute("SELECT 1 FROM words WHERE german = ? AND pos LIKE '动词%' AND owner_id IS NULL LIMIT 1",
                           (word[:1].lower() + word[1:],)).fetchone()
    return "由动词原形变来的名词都是 das" if hit else None


def gender_reason(word, gender):
    word = word.strip().split(" ")[-1]
    return (ending_reason(word, gender) or compound_reason(word, gender) or verb_reason(word, gender)
            or ("星期、月份、季节和方位都是 der" if gender == "der" and word.lower() in TIME_WORDS else None)
            or ("以 -e 结尾的名词大多是 die，但有例外" if gender == "die" and word.endswith("e") and len(word) > 3 else None)
            or NO_RULE)


@bp.route("/api/gender_reason")
@login_required
def reason():
    german, gender = request.args.get("german", "").strip(), request.args.get("gender", "")
    if not german or len(german) > 100 or gender not in GENDERS:
        return err("参数无效")
    return jsonify({"reason": gender_reason(german, gender)})
