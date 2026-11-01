"""动词完成时填空题: 一题两个空, 助动词 + 过去分词。接口在 verb_quiz.py, 这里只管出题

句子: 手写句子(verb_sentences.PERFEKT) + 真实例句(助动词能确定人称, 过去分词在句末)。都没有时出短题 `du ___ ___`。
词库有 145 个动词标了两种助动词(ist/hat), 而且首选不可靠(passieren 标成 hat), 这些词只用句子出题, 由句子决定助动词。
答错分三种: aux = 助动词错, part = 过去分词错, 都算忘了; person = 助动词的人称错, 不改记忆状态。
"""
import json
import random
import re

import verb_quiz as vq
from custom_lessons import CHINESE
from gender_hint import short_meaning
from verb_sentences import PERFEKT

AUX = {"sein": ["bin", "bist", "ist", "sind", "seid", "sind"],
       "haben": ["habe", "hast", "hat", "haben", "habt", "haben"]}
PAST = re.compile(rf"(hat|ist|ist/hat|hat/ist) ([{vq.LETTERS}]+)")
INSIDE_END = re.compile(r"[.?!] ")           # 两句话连在一起
STANDARD_HABEN = ("stehen", "sitzen", "liegen")   # 南德用 sein, 考试按标准德语
SEIN_WORDS = ("sein", "bleiben", "werden", "passieren")


def perf_info(row):
    """现在时信息 + 过去分词和助动词; 两种助动词都标了的 aux 为空。数据不完整时返回 None"""
    v = vq.verb_info(row)
    past = (json.loads(row["forms"]) if v else {}).get("past") or []
    m = PAST.fullmatch(past[1]) if len(past) == 2 and past[1] else None
    if not m:
        return None
    aux = {"ist": "sein", "hat": "haben"}.get(m.group(1))
    return {**v, "part": m.group(2), "aux": aux}


def split_prefix(german, v):
    """(去掉可分前缀的不定式, 去掉可分前缀的过去分词)"""
    particle, part = v["particle"], v["part"]
    if particle and german.startswith(particle) and part.startswith(particle):
        return german[len(particle):], part[len(particle):]
    return german, part


def has_ge(word, core):
    """过去分词有没有 ge-: gehen → gegangen、geben → gegeben 有, gewinnen → gewonnen、besuchen → besucht 没有"""
    return core.startswith(("gege", "gega", "gego") if word.startswith("ge") else "ge")


def weak_stem(word):
    return "sein" if word == "sein" else word[:-1] if word.endswith(("ern", "eln", "tun")) else word[:-2]


def weak_form(stem):
    """按规则动词变出来的过去分词"""
    return "ge" + stem + ("et" if stem.endswith(("t", "d")) else "t")


def wrong_participle(german, v):
    """最常见的错法: 不该加 ge 的加了(gebesucht), ge 放错位置(geabholt), 强变化按规则变(getrinkt), 规则动词按强变化变(gemachen)"""
    word, core = split_prefix(german.lower(), v)
    if not has_ge(word, core):
        wrong = "ge" + v["part"]
    elif v["particle"]:
        wrong = "ge" + v["particle"] + core[2:]
    else:
        stem = weak_stem(word)
        wrong = weak_form(stem) if v["part"] != weak_form(stem) else "ge" + stem + "en"
    return wrong if wrong != v["part"] else ""


def participle_note(german, v):
    word, core = split_prefix(german.lower(), v)
    if not has_ge(word, core):
        return "-ieren 结尾的动词不加 ge-" if word.endswith("ieren") else "不可分前缀的动词不加 ge-"
    if v["particle"]:
        return f"可分动词，ge 放在前缀 {v['particle']} 后面"
    if core == weak_form(weak_stem(word)):
        return "规则变化 ge-…-t"
    return "混合变化，要单独记" if core.endswith("t") else "不规则，过去分词要单独记"


def aux_note(german, v, aux):
    if german in STANDARD_HABEN:
        return f"{german} 在标准德语里用 haben（南德常用 sein）"
    if not v["aux"]:
        return f"{german} 有时用 haben，有时用 sein：带第四格宾语用 haben，表示移动或变化用 sein"
    if aux == "haben":
        return f"{german} 用 haben"
    return f"{german} 要单独记，用 sein" if german in SEIN_WORDS else f"{german} 表示移动或状态变化，用 sein"


def options(row, v, person, aux):
    """{选项: 错因}。选项写成 “助动词 … 过去分词”, 练习引擎按 “ … ” 分段填空"""
    right, part = AUX[aux][person], v["part"]
    other = AUX["haben" if aux == "sein" else "sein"][person]
    wrong_part = wrong_participle(row["german"], v)
    kinds = {f"{other} … {part}": "aux"}
    if wrong_part:
        kinds[f"{right} … {wrong_part}"] = "part"
    others = [a for a in dict.fromkeys(AUX[aux]) if a != right]
    for form in random.sample(others, 2 if wrong_part else 3):
        kinds[f"{form} … {part}"] = "person"
    return dict(list(kinds.items())[:3])


def question(row, v, person, aux, prompt, zh, source, fill=None, short=False):
    german, form = row["german"], AUX[aux][person]
    answer = f"{form} … {v['part']}"
    first = form.capitalize() if prompt.startswith("___") else form
    kinds = options(row, v, person, aux)
    return {"word_id": row["id"], "german": german, "meaning": row["meaning"], "prompt": prompt, "answer": answer,
            "fill": fill or f"{first} … {v['part']}", "options": [answer, *kinds], "kinds": kinds,
            "explain": f"{aux_note(german, v, aux)}；{v['part']}：{participle_note(german, v)}", "zh": zh, "source": source,
            "must": f"（{german}）", "hint": f"{german} · {vq.PERSONS[person]} · 用 {aux}", "person": person, "verb": True,
            "stem_picks": [], "short": short}


def example_sentences(row, v):
    """真实例句: 过去分词在句末, 助动词是现在时而且能确定人称。hatte、wurde 那样的句子不是完成时。
    只标了 haben 的词遇到 ist 不用: Hier ist Rauchen verboten 是状态, 不是完成时"""
    details = json.loads(row["details"]) if row["details"] else {}
    auxes = [v["aux"]] if v["aux"] else ["sein", "haben"]
    out = []
    for raw in [row["example"]] + list(details.get("examples") or []):
        lines = [x.strip() for x in (raw or "").split("\n") if x.strip()]
        if len(lines) != 2 or CHINESE.search(lines[0]) or not CHINESE.search(lines[1]) or vq.NOT_SIMPLE.search(lines[0]):
            continue
        de, zh = lines
        matches = list(vq.TOKEN.finditer(de))
        tokens = [m.group() for m in matches]
        lows = [t.lower() for t in tokens]
        if not 3 <= len(tokens) <= 14 or de.endswith("!") or "bitte" in lows or INSIDE_END.search(de) or tokens[-1] != v["part"]:
            continue
        if any(a == b for a, b in zip(lows, lows[1:])):
            continue                     # 词库里有 Ich habe mich mich gebadet 这样的错句
        for i, m in enumerate(matches[:-1]):
            aux = next((a for a in auxes if lows[i] in AUX[a]), None)
            if not aux or lows.count(lows[i]) != 1 or (tokens[i] != lows[i] and i):
                continue
            person = vq.person_of(tokens, lows, i, {"heads": AUX[aux]}, "")
            if person is not None:
                last = matches[-1]
                prompt = de[:m.start()] + "___" + de[m.end():last.start()] + "___" + de[last.end():]
                out.append((person, prompt, zh, aux, f"{m.group()} … {v['part']}", "example"))
                break
    return out


def written_sentences(row, v):
    """手写句子 (人称, 句子, 翻译[, 助动词]); 两种助动词都标了的词要写明"""
    return [(x[0], x[1], x[2], x[3] if len(x) > 3 else v["aux"], None, "written") for x in PERFEKT.get(row["german"], [])]


def make_question(row, weights):
    v = perf_info(row)
    if not v:
        return None
    pool = written_sentences(row, v) + example_sentences(row, v)
    if pool:
        person, prompt, zh, aux, fill, source = random.choices(pool, [weights[x[0]] for x in pool])[0]
        return question(row, v, person, aux, prompt, zh, source, fill)
    if not v["aux"]:
        return None                      # 没有句子时判断不了用哪个助动词
    person = random.choices(range(6), [weights[p] for p in range(6)])[0]
    return question(row, v, person, v["aux"], f"{vq.SHORT_SUBJECT[person]} ___ ___",
                    short_meaning(row["meaning"]) or row["meaning"], "template", short=True)


vq.KINDS["perfekt"] = {"tense": "perfekt", "practice": "perfekt_practice", "list": "perfekt_list",
                       "kinds": ("aux", "part", "person"), "make": make_question}
