"""今天到期的练习: 定冠词、动词、听写、句子各有自己的 FSRS 排期, 这里数出每种今天(本地日期)到期的词数。
今天页“今天还要练”用; 点了用 scope=due 只练这些到期的词(各练习的出题接口里处理)。文档 docs/features/practice-due.md
情景课的整句复习数量另有 /api/roleplay/due?count=1, 前端一起显示。
"""
from flask import Blueprint, jsonify

import dictation
import sentences
import verb_quiz as vq
from helpers import login_required
from today import local_day, read_tz
from vocab import query

bp = Blueprint("practice_due", __name__)

# 和各练习出题时“到期”的条件一样: 练过(有记录)且 next_review 为空(老记录)或在今天结束之前
DUE = "({a}.next_review IS NULL OR {a}.next_review < :end)"


def due_count(table, alias, where, end, extra="", **args):
    sql = (f"SELECT COUNT(*) FROM my_words w JOIN {table} {alias} ON {alias}.word_id = w.id AND {alias}.user_id = :uid {extra} "
           f"WHERE {where} AND {DUE.format(a=alias)}")
    return query(sql, end=end, **args).fetchone()[0]


def due_counts(end):
    """{练习: 到期词数}; 键和前端 home.js 的 DUE_PRACTICE 对应"""
    out = {"nouns": due_count("noun_practice", "np", "w.gender != ''", end)}
    for which, cfg in vq.KINDS.items():           # verbs / perfekt / usage
        out[which] = due_count(cfg["practice"], "np", vq.verb_filter(cfg), end)
    out["dictation"] = due_count("dict_practice", "dp", "1 " + dictation.USABLE, end)
    for mode in sentences.MODES:
        out["sent-" + mode] = due_count("sent_practice", "sp", "1", end, "AND sp.mode = :mode", mode=mode)
    return out


@bp.route("/api/today/practice")
@login_required
def today_practice():
    """?tz=: {due: {nouns, verbs, perfekt, usage, dictation, sent-cloze, …}}, 只数, 不出题, 不算免费次数"""
    return jsonify({"due": due_counts(local_day(read_tz())[2])})
