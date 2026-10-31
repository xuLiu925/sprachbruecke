"""第 2 步(只在电脑上运行): 整理单词书 —— 歌德 A1/A2/B1 词表 + 按词频补 B2/C1, 加上冠词/复数/变格/变位

输入:  data/raw/goethe.zip             歌德学院 A1/A2/B1 词表的整理版
                                        (github.com/ilkermeliksitki/goethe-institute-wordlist)
       data/raw/de_50k.txt             德语词频(FrequencyWords, OpenSubtitles 2018)
       data/work/de_entries.jsonl      第 1 步的输出(德语维基词典)
       tools/wordbook_exclude.txt      手工排除的词(每行一个, # 开头是注释)
输出:  data/work/wordbook_base.jsonl   每行一个词(还没有中文), 下一步 translate_wordbook.py 加中文

运行:  python tools/build_wordbook.py
B2/C1 不是官方等级: 歌德没有公开 B2/C1 词表, 这里用「词频表里排除 A1-B1 以后最常用的词」近似
"""
import collections
import json
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOETHE = os.path.join(ROOT, "data", "raw", "goethe.zip")
FREQ = os.path.join(ROOT, "data", "raw", "de_50k.txt")
ENTRIES = os.path.join(ROOT, "data", "work", "de_entries.jsonl")
EXCLUDE = os.path.join(ROOT, "tools", "wordbook_exclude.txt")
OUT = os.path.join(ROOT, "data", "work", "wordbook_base.jsonl")

GOETHE_LEVELS = ["A1", "A2", "B1"]
EXTRA_LEVELS = [("B2", 2100), ("C1", 3500)]     # 按词频补充的数量
KEEP_POS = {"noun", "verb", "adj", "adv", "pron", "prep", "conj", "particle", "num", "intj", "det", "postp"}
CLOSED_POS = {"pron", "det", "conj", "prep", "postp", "particle", "num"}
AUX = {"sein", "haben", "werden"}
POS_ZH = {"noun": "名词", "verb": "动词", "adj": "形容词", "adv": "副词", "pron": "代词", "prep": "介词",
          "postp": "介词", "conj": "连词", "particle": "小品词", "num": "数词", "intj": "感叹词", "det": "冠词"}
GRAMMAR_TAGS = {"nominative", "genitive", "dative", "accusative", "present", "past", "participle-2",
                "comparative", "superlative", "first-person", "second-person", "third-person"}
GENDER = {"masculine": "der", "feminine": "die", "neuter": "das"}
CASES = ["nominative", "genitive", "dative", "accusative"]
PERSONS = [("first-person", "singular"), ("second-person", "singular"), ("third-person", "singular"),
           ("first-person", "plural"), ("second-person", "plural"), ("third-person", "plural")]
FORM_OF = re.compile(r"\b(?:des|der) (?:Verbs|Substantivs|Adjektivs|Pronomens|Artikels|Numerales|Zahlworts|"
                     r"Possessivpronomens|Personalpronomens|Demonstrativpronomens|Indefinitpronomens|"
                     r"Relativpronomens|Interrogativpronomens|Reflexivpronomens|bestimmten Artikels|"
                     r"unbestimmten Artikels)\s+(\S+)\s*$")
UMLAUT = {"a": "ä", "o": "ö", "u": "ü", "A": "Ä", "O": "Ö", "U": "Ü"}


def log(*a):
    print(*a, file=sys.stderr)


# ---------- 歌德词表 ----------
def umlaut(word):
    """Apfel → Äpfel, Haus → Häus (au → äu), 只改最后一个 a/o/u"""
    for i in range(len(word) - 1, -1, -1):
        if word[i] in UMLAUT:
            if word[i] in "uU" and i > 0 and word[i - 1] in "aA":
                return word[:i - 1] + UMLAUT[word[i - 1]] + word[i:]
            return word[:i] + UMLAUT[word[i]] + word[i + 1:]
    return word


def plural_from_note(word, note):
    """歌德词表的复数写法: '-en' → Wort+en, '-' → 不变, '¨-e' → 变音+e, '-s' ..."""
    note = note.strip().replace(" ", "")
    if not note or not note.startswith(("-", "¨")):
        return ""
    base = umlaut(word) if "¨" in note else word
    return base + note.replace("¨", "").lstrip("-")


def parse_head(raw):
    """一个词头可能写了多个词('der Student, -en / die Studentin, -nen'), 返回 [(german, gender, plural, note)]"""
    raw = re.sub(r"\(\d+\)\s*$", "", raw.strip()).strip()
    plural_only = "(Pl.)" in raw
    raw = raw.replace("(Pl.)", "").replace("(Sg.)", "").strip()
    out = []
    for part in raw.split(" / "):
        part = part.strip()
        note = ""
        if "(sich)" in part:
            note = "sich"
            part = part.replace("(sich)", "").strip(" ,")
        m = re.match(r"^(der|die|das)\s+(.+)$", part)
        gender = m.group(1) if m else ""
        rest = m.group(2) if m else part
        word, _, after = rest.partition(",")
        word = re.sub(r"\(e\)$", "", word.split("/")[0].strip()).strip()   # vorn(e), Hähnchen/Hühnchen
        if not word or word.startswith("-") or word.endswith("-") or "(" in word or ")" in word:
            continue
        plural = ""
        if gender and not plural_only:
            plural = plural_from_note(word, after.split(",")[0]) if after else ""
        if plural_only:
            plural, gender = word, ""
        out.append((word, gender, plural, note))
    return out


def read_goethe(lemmas):
    """返回 {(german, gender): {...}} , level 取最低的一级"""
    z = zipfile.ZipFile(GOETHE)
    words = {}
    for level in GOETHE_LEVELS:
        names = sorted(n for n in z.namelist()
                       if f"/{level.lower()}/" in n and n.endswith(".tsv") and not n.endswith(f"/{level.lower()}.tsv"))
        last = []
        for n in names:
            for line in z.read(n).decode("utf-8").splitlines():
                cols = line.split("\t")
                if len(cols) < 2 or not cols[0].strip() or cols[0].strip() == "german word":
                    continue
                parsed = parse_head(cols[0]) or last      # 只有 '(2)' 的行属于上一个词
                last = parsed
                for word, gender, plural, note in parsed:
                    if not cols[1].strip() and word not in lemmas:   # 'chattet' 这类变形行
                        continue
                    key = (word, gender)
                    w = words.setdefault(key, {"german": word, "gender": gender, "plural": plural, "note": note,
                                               "level": level, "examples": []})
                    if GOETHE_LEVELS.index(level) < GOETHE_LEVELS.index(w["level"]):
                        w["level"] = level
                    w["plural"] = w["plural"] or plural
                    ex = (cols[1].strip(), cols[2].strip() if len(cols) > 2 else "")
                    if ex[0] and ex not in w["examples"]:
                        w["examples"].append(ex)
    return words


# ---------- 维基词典 ----------
def gram_forms(e):
    """带语法标签的变形(排除缩写、异体、小称、命令式等)"""
    for f in e["forms"]:
        tags = set(f.get("tags", []))
        if GRAMMAR_TAGS & tags and "imperative" not in tags:
            yield f


def bare(form):
    """'ich fahre' → 'fahre'"""
    s = form.strip()
    parts = s.split(" ", 1)
    if len(parts) == 2 and parts[0] in ("ich", "du", "er/sie/es", "es", "wir", "ihr", "sie"):
        s = parts[1]
    return s


def read_entries(tokens):
    lemmas = collections.defaultdict(list)   # 原形 → [词条, ...]
    form_of = collections.defaultdict(set)   # 变形 → {原形}
    with open(ENTRIES, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if "Grundformeintrag (Deutsch)" in e["categories"]:
                if e["pos"] in KEEP_POS:
                    lemmas[e["word"]].append(e)
            elif e["word"].lower() in tokens and e["senses"] and "form-of" in e["senses"][0]["tags"]:
                for s in e["senses"]:
                    if "imperative" in s["tags"]:
                        continue
                    m = FORM_OF.search(s["gloss"])
                    if m:
                        form_of[e["word"]].add(m.group(1))
    return lemmas, form_of


def word_scores(freq, lemmas, form_of):
    """每个原形的词频分(它所有变形的出现次数之和, 有歧义的按各原形本身的词频分摊)"""
    count = dict(freq)
    forms_of = collections.defaultdict(set)
    for head, es in lemmas.items():
        for e in es:
            for f in gram_forms(e):
                forms_of[bare(f["form"])].add(head)
    for w, heads in form_of.items():
        forms_of[w] |= {h for h in heads if h in lemmas}

    def is_noun(h):
        return any(e["pos"] == "noun" for e in lemmas[h])

    def closed(heads):
        return any(h in AUX or any(e["pos"] in CLOSED_POS for e in lemmas[h]) for h in heads)

    def candidates(t):
        """词频表全是小写, 一个词形可能属于好几个原形: ist → sein, tagen → Tag / tagen, gemacht → machen / gemacht"""
        cap = t[:1].upper() + t[1:]
        lower = ([t] if t in lemmas else []) + sorted(forms_of.get(t, set()) - {t})
        upper = ([cap] if cap != t and cap in lemmas and is_noun(cap) else []) + \
            sorted(h for h in forms_of.get(cap, set()) if h != cap and is_noun(h))
        if lower and closed(lower):        # ist / habe / ich: 不算给名词 das Ist / die Habe / das Ich
            upper = []
        return list(dict.fromkeys(lower + upper))

    # 两轮: 第一轮只数「原形本身的写法」和没有歧义的词形, 第二轮把有歧义的按第一轮的分数分摊(常见的原形分得多)
    cands = {t: candidates(t) for t, _ in freq}
    first = collections.Counter()
    for t, c in freq:
        cap = t[:1].upper() + t[1:]
        for h in cands[t]:
            if len(cands[t]) == 1 or h in (t, cap):
                first[h] += c
    verb_forms = {f for f, heads in forms_of.items() if any(e["pos"] == "verb" for h in heads for e in lemmas[h])}

    def is_form_of_other(h):
        """h 本身也是别的词的变形: stunden ← Stunden(Stunde), schönen ← schön, gemacht ← machen"""
        cap = h[:1].upper() + h[1:]
        return bool(forms_of.get(h, set()) - {h}) or any(x != cap and is_noun(x) for x in forms_of.get(cap, set()))

    def weight(h):
        w = 1 + first[h]
        # 和别的词的变形同形的动词/形容词(stunden, gemacht)主要算给那个常见词
        if h[:1].islower() and all(e["pos"] in ("verb", "adj") for e in lemmas[h]) and is_form_of_other(h):
            w *= 0.2
        return w
    score = collections.Counter()
    for t, c in freq:
        hs = cands[t]
        if not hs:
            continue
        weights = [weight(h) for h in hs]
        for h, wgt in zip(hs, weights):
            score[h] += c * wgt / sum(weights)
    return score, forms_of


def noun_info(e):
    gender = next((GENDER[t] for t in e["tags"] if t in GENDER), "")
    sg = {c: [] for c in CASES}
    pl = {c: [] for c in CASES}
    for f in gram_forms(e):
        tags = set(f.get("tags", []))
        case = next((c for c in CASES if c in tags), None)
        if not case or not f.get("article"):
            continue
        box = sg if "singular" in tags else pl if "plural" in tags else None
        if box is not None:
            s = f"{f['article']} {f['form']}"
            if s not in box[case]:
                box[case].append(s)
    plural = pl["nominative"][0].split(" ", 1)[1] if pl["nominative"] else ""
    forms = None
    if all(sg[c] for c in CASES):
        nom = sg["nominative"][0].split(" ", 1)[1]
        dat = [x for x in sg["dative"] if x.split(" ", 1)[1] == nom] or sg["dative"]   # 去掉古旧的 dem Tische
        sg_out = [sg["nominative"][0], " / ".join(sorted(sg["genitive"], key=len, reverse=True)[:2]),
                  dat[0], sg["accusative"][0]]
        pl_out = [pl[c][0] for c in CASES] if all(pl[c] for c in CASES) else [""] * 4
        forms = {"cases": {"sg": sg_out, "pl": pl_out}}
    return gender, plural, forms


def verb_info(e):
    pres, past1 = {}, None
    for f in e["forms"]:
        tags = set(f.get("tags", []))
        if "indicative" not in tags or "active" not in tags or tags & {"processual-passive", "statal-passive"}:
            continue
        for i, (p, n) in enumerate(PERSONS):
            if p in tags and n in tags:
                if "present" in tags and i not in pres:
                    pres[i] = bare(f["form"])
                if "past" in tags and i == 0 and past1 is None:
                    past1 = bare(f["form"])
    part2 = next((f["form"] for f in e["forms"] if "participle-2" in f.get("tags", [])), None)
    auxes = []
    for f in e["forms"]:
        if "auxiliary" in f.get("tags", []) and "perfect" in f.get("tags", []) and f["form"] in ("sein", "haben"):
            a = {"sein": "ist", "haben": "hat"}[f["form"]]
            if a not in auxes:
                auxes.append(a)
    forms = {}
    if len(pres) == 6:
        forms["praesens"] = [pres[i] for i in range(6)]
    if past1 and part2 and auxes:
        forms["past"] = [past1, "/".join(auxes) + " " + part2]
    return forms or None


def wiki_info(german, gender, es):
    """从维基词典取: 词性、冠词、复数、变格/变位、例句"""
    noun = next((e for e in es if e["pos"] == "noun"), None)
    verb = next((e for e in es if e["pos"] == "verb"), None)
    info = {"pos": "、".join(dict.fromkeys(POS_ZH.get(e["pos"], e["pos"]) for e in es)) if es else "",
            "gender": "", "plural": "", "forms": None, "example": ""}
    # 词表没给冠词时, 虚词优先于同形的名词: es 是代词, 不是 das Es
    function_word = next((e for e in es if e["pos"] in CLOSED_POS | {"intj"}), None)
    if noun and (gender or not (verb or function_word)):
        main = noun
    else:
        main = verb or function_word or (es[0] if es else None)
    if main is noun and noun:
        info["gender"], info["plural"], info["forms"] = noun_info(noun)
        info["pos"] = "名词"
    elif main is verb and verb:
        info["forms"] = verb_info(verb)
        info["pos"] = "动词"
    if main:
        info["example"] = next((x for s in main["senses"] for x in s["examples"] if good_example(x)), "")
    return info


QUOTES = "„“”\"«»‚‘’"


def good_example(s):
    """只要正常的短句: 不要引文(方言、诗歌常带引号), 要以句号 / 问号 / 感叹号结尾, 至少 3 个词"""
    return not any(q in s for q in QUOTES) and s.rstrip()[-1:] in ".!?" and len(s.split()) >= 3


WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß]{2,}")


def is_vocab(head, es):
    """能放进单词书的词: 只由字母组成(不要 50er、3D), 不是纯感叹词(aah、oh、hm)"""
    return bool(WORD_RE.fullmatch(head)) and not all(e["pos"] == "intj" for e in es)


def load_exclude():
    if not os.path.exists(EXCLUDE):
        return set()
    with open(EXCLUDE, encoding="utf-8") as f:
        return {l.split("#")[0].strip() for l in f if l.split("#")[0].strip()}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    freq = []
    with open(FREQ, encoding="utf-8") as f:
        for line in f:
            w, c = line.split()
            freq.append((w, int(c)))
    exclude = load_exclude()
    log("读维基词典词条 ...")
    lemmas, form_of = read_entries({w for w, _ in freq})
    score, forms_of = word_scores(freq, lemmas, form_of)
    goethe = read_goethe(lemmas)
    log(f"歌德词表: {len(goethe)} 个词 " + str(collections.Counter(w['level'] for w in goethe.values())))

    records = []
    # A1-B1: 歌德词表, 同一级里按词频排
    for w in goethe.values():
        if w["german"] in exclude:   # 排除名单对歌德词表的词也生效
            continue
        es = lemmas.get(w["german"], [])
        info = wiki_info(w["german"], w["gender"], es)
        gender = w["gender"] or (info["gender"] if info["pos"] == "名词" and not w["plural"] else "")
        pos = info["pos"] or ("名词" if w["gender"] else "")
        if w["note"] == "sich":
            pos = (pos or "动词") + "（反身 sich）"
        forms = info["forms"] if (not w["gender"] or info["gender"] == w["gender"]) else None
        ex_de, ex_en = w["examples"][0] if w["examples"] else (info["example"], "")
        records.append({
            "german": w["german"], "gender": gender, "pos": pos,
            "plural": info["plural"] or w["plural"] if gender else w["plural"],
            "forms": forms, "example": ex_de, "example_en": ex_en,
            "level": w["level"], "score": score.get(w["german"], 0), "source": "goethe",
        })
    # 词频总排名(去掉名词化的 das Jetzt / das Muss 和手工排除的词)
    nonnoun = {h.lower() for h, es in lemmas.items() if any(e["pos"] != "noun" for e in es)}
    nonnoun |= {f.lower() for f, heads in forms_of.items() if any(h[:1].islower() for h in heads)}
    ranked = [h for h, _ in score.most_common()
              if h not in exclude and is_vocab(h, lemmas[h])
              and not (h[:1].isupper() and h.lower() in nonnoun)]
    # 歌德词表(这个整理版)有缺词: 不在表里的常用词按词频总排名补级别 —— 前 650 A1, 前 1300 A2, 前 2400 B1,
    # 再往后 B2 / C1 各取一定数量
    taken = {w["german"] for w in goethe.values()} | {w["german"].lower() for w in goethe.values()}
    left = dict(EXTRA_LEVELS)
    for grank, head in enumerate(ranked, 1):
        if head in taken or head.lower() in taken:
            continue
        level = "A1" if grank <= 650 else "A2" if grank <= 1300 else "B1" if grank <= 2400 else None
        if level is None:
            level = next((lv for lv, _ in EXTRA_LEVELS if left[lv] > 0), None)
            if level is None:
                break
            left[level] -= 1
        info = wiki_info(head, "", lemmas[head])
        records.append({
            "german": head, "gender": info["gender"], "pos": info["pos"], "plural": info["plural"],
            "forms": info["forms"], "example": info["example"], "example_en": "",
            "level": level, "score": score[head], "source": "frequency",
        })
    # 每一级里按词频从高到低编 rank
    order = {lv: k for k, lv in enumerate(GOETHE_LEVELS + [l for l, _ in EXTRA_LEVELS])}
    records.sort(key=lambda r: (order[r["level"]], -r["score"], r["german"]))
    with open(OUT, "w", encoding="utf-8") as out:
        for rank, r in enumerate(records, 1):
            r["rank"] = rank
            del r["score"]
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    log(f"完成: {len(records)} 个词 → {OUT} " + str(collections.Counter(r['level'] for r in records)))


if __name__ == "__main__":
    main()
