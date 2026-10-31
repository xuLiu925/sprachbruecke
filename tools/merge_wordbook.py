"""第 4 步(只在电脑上运行, 几秒钟): 用人工整理的词典改进单词书 —— 换掉谷歌机翻的释义, 补例句 / 用法, 加新词和专题单词书

输入:  data/work/wordbook_translated.json   第 3 步的输出(机翻版, 这一步不改它, 所以可以反复运行)
       data/raw/A1_Goethe_760__/            Anki 牌组(解压的 .apkg): 人工中文、带翻译的例句、提示
       data/raw/欧标A1单词*.csv 等 3 个      德语助手生词本导出: 释义、音标、例句
       data/raw/德福DSH*.epub               用法、词根、近反义词、功能动词、常用词组
       data/work/zh_glosses.json            中文维基词典(tools/extract_zh_glosses.py 的输出)
       tools/wordbook_fixes.tsv             手工写的释义(虚词), 优先级最高
输出:  data/wordbook.json                   再用 tools/import_wordbook.py 导入数据库
运行:  python tools/merge_wordbook.py

释义优先级: 手工 > Anki > 德语助手 > DSH > 中文维基词典 > 谷歌。EPUB 主题词表和复合词有印刷错误(der Sandstorm), 只用来匹配已有的词, 不加新词
"""
import collections
import csv
import glob
import html
import json
import os
import re
import sqlite3
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
SRC = os.path.join(ROOT, "data", "work", "wordbook_translated.json")
OUT = os.path.join(ROOT, "data", "wordbook.json")
FIXES = os.path.join(ROOT, "tools", "wordbook_fixes.tsv")
EXCLUDE = os.path.join(ROOT, "tools", "wordbook_exclude.txt")
REVIEWED = os.path.join(ROOT, "tools", "wordbook_reviewed.txt")
TODO = os.path.join(ROOT, "data", "待查单词.txt")
ANKI = os.path.join(RAW, "A1_Goethe_760__", "collection.anki21")
FREQ = os.path.join(RAW, "de_50k.txt")
ZH_GLOSSES = os.path.join(ROOT, "data", "work", "zh_glosses.json")

LEVELS = ["A1", "A2", "B1", "B2", "C1"]
GENDER = {"m": "der", "f": "die", "n": "das"}
POS_ZH = [("vt", "动词"), ("vi", "动词"), ("v", "动词"), ("refl", "动词"), ("adj", "形容词"), ("a", "形容词"),
          ("adv", "副词")]
CJK = re.compile(r"[一-鿿]")
WORD = re.compile(r"[A-Za-zÄÖÜäöüß]{2,}")
POS_PREFIX = re.compile(r"^(?:\s*[A-Za-z]{1,5}\.(?:\s*/\s*|\s*))+")
MAX_MEANING = 60     # 释义超过这么长就只留前几个义项, 卡片上放不下
LIMITS = {"usage": 6, "examples": 3, "phrases": 6, "synonyms": 6, "antonyms": 4, "related": 6, "notes": 3}


def log(*a):
    print(*a, file=sys.stderr)


def clean_meaning(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = POS_PREFIX.sub("", s.strip())
    s = re.sub(r"\s*[;；]\s*", "；", s)
    s = re.sub(r"\s+", " ", s).strip(" ；,，")
    if len(s) <= MAX_MEANING:
        return s
    kept = ""
    for part in s.split("；"):
        if kept and len(kept) + len(part) + 1 > MAX_MEANING:
            break
        kept += ("；" if kept else "") + part
    return kept[:MAX_MEANING * 2]


def new_entry(source, german, gender="", pos="", meaning=""):
    return {"source": source, "german": german, "gender": gender, "pos": pos, "meaning": meaning, "ipa": "",
            "examples": [], "usage": [], "phrases": [], "synonyms": [], "antonyms": [], "related": [],
            "notes": [], "root": ""}


# ---------- 德语助手 CSV ----------
def read_frdic(path):
    entries = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            m = re.search(r'class="\.expDiv">(.*?)</div>', r["释义"], re.S)
            raw = html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).strip() if m else ""
            labels = [x.lower() for x in re.findall(r"[A-Za-z]{1,5}(?=\.)", POS_PREFIX.match(raw).group(0))] \
                if POS_PREFIX.match(raw) else []
            word = r["单词"].strip()
            gender = next((GENDER[x] for x in labels if x in GENDER), "") if word[:1].isupper() else ""
            pos = "名词" if gender else next((z for k, z in POS_ZH if k in labels), "")
            e = new_entry("frdic", word, gender, pos, clean_meaning(raw))
            ipa = re.search(r"\[(.+?)\]", r["音标"])
            e["ipa"] = ipa.group(1).replace("`", "ˈ").split(",")[0].strip() if ipa else ""
            for de, zh in re.findall(r'<div>([^<]+?)\s*(?:<span class="exp">(.*?)</span>)?</div>', r["释义"]):
                e["examples"].append((html.unescape(de).strip(), html.unescape(zh).strip()))
            entries.append(e)
    return entries


# ---------- Anki ----------
def read_anki():
    db = sqlite3.connect(f"file:{ANKI.replace(os.sep, '/')}?mode=ro", uri=True)
    entries = []
    for (flds,) in db.execute("SELECT flds FROM notes"):
        word, genus, label, _, _, zh, _, grammar, tip, examples = flds.split("\x1f")[:10]
        if not WORD.fullmatch(word):    # ihr/ihm/ihn 这种一行几个词的, 对不上单个词条
            continue
        m = re.search(r"\b(der|die|das)\b", genus.lower())
        gender = m.group(1) if m else GENDER.get(genus.strip().lower()[:1], "")
        e = new_entry("anki", word, gender, "名词" if gender else "", clean_meaning(zh))
        grammar = html.unescape(re.sub(r"<[^>]+>", " ", grammar))
        if grammar.strip():
            e["usage"].append(re.sub(r"\s+", " ", grammar).strip())
        if tip.strip():
            e["notes"].append(html.unescape(re.sub(r"<[^>]+>", "", tip)).strip())
        for de, zh2 in re.findall(r'bsp-de">(.*?)</div>\s*<div class="bsp-zh">(.*?)</div>', examples, re.S):
            de = re.sub(r"\[sound:[^\]]*\]", "", html.unescape(re.sub(r"<[^>]+>", "", de)))
            e["examples"].append((de.strip(" „“\"\n"), html.unescape(zh2).strip()))
        entries.append(e)
    return entries


# ---------- EPUB (德福 DSH 核心词汇详解) ----------
def epub_paragraphs(z, n):
    text = z.read(f"OEBPS/text{n:05d}.html").decode("utf-8", "ignore")
    out = []
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", text, re.S):
        s = html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
        s = re.sub(r"[ \t\r\n]+", " ", s).strip()
        if s:
            out.append(("<b>" in m.group(1), s))
    return out


def base_form(head):
    """ab/bauen → abbauen, sich freuen → freuen, achten auf → achten"""
    parts = [p for p in head.split() if p != "sich"]
    return parts[0].replace("/", "") if parts else ""


def split_zh(s):
    """'etw. (A)～　略微修改' → ('etw. (A)～', '略微修改')"""
    m = re.search(r"[（(]?[一-鿿]", s)    # 中文前面的括号算中文的: （铃）响
    return (s[:m.start()].strip(" 　"), s[m.start():].strip()) if m else (s.strip(), "")


def is_sentence(s):
    return not CJK.search(s) and s[-1:] in ".!?" and len(s.split()) >= 3


def parse_plain_verbs(paragraphs, fix):
    """第 1 章: 词头 / '+ A　注意' / 例句 ……"""
    entries, e = [], None
    for _, s in paragraphs:
        if is_sentence(s):
            if e:
                e["examples"].append((fix(s), ""))
        elif CJK.search(s):
            if e:
                s = s.lstrip("①②③④⑤⑥⑦⑧⑨ ")
                e["usage"].append(re.sub(r"\s+", " ", s.replace("　", " ")))
                meaning = split_zh(s)[1]
                if meaning and meaning not in e["meaning"]:
                    e["meaning"] += ("；" if e["meaning"] else "") + meaning
        elif base_form(s) and WORD.fullmatch(base_form(s)):
            e = new_entry("dsh", base_form(s), pos="动词")
            entries.append(e)
    return entries


SECTIONS = {"【用法】": "usage", "【名词】": "related", "【形容词】": "related", "【副词】": "related",
            "【联想】": "related", "【复合】": "related", "【固搭】": "related", "【近义词】": "synonyms",
            "【反义词】": "antonyms", "【趣记】": "notes", "【注意】": "notes"}
HEAD = re.compile(r"^([a-zäöüß]+(?:/[a-zäöüß]+)?)(?:\s*=\s*(.+))?$")


def parse_prefix_verbs(paragraphs, fix):
    """第 2 章: 粗体词头(ab/bauen = ab（去除）+ bauen（建造）)、【用法】【近义词】…… z.B. 后面是例句"""
    entries, e, section = [], None, None
    for bold, s in paragraphs:
        head = HEAD.match(s) if bold else None
        if head:
            e, section = new_entry("dsh", head.group(1).replace("/", ""), pos="动词"), None
            e["root"] = head.group(2) or ""
            entries.append(e)
        elif e is None or s in ("z.B.", "z. B."):
            continue
        elif bold:
            m = CJK.match(s)     # '起飞　vi.　ist abgeflogen'
            if m and not e["meaning"]:
                e["meaning"] = re.split(r"[　 ]", s)[0]
            section = None
        elif s in SECTIONS:
            section = SECTIONS[s]
        elif is_sentence(s):
            e["examples"].append((fix(s), ""))
        elif section == "usage":
            s = s.lstrip("❶❷❸❹❺❻❼❽❾ ")
            e["usage"].append(re.sub(r"\s+", " ", s.replace("　", " ")))
            meaning = split_zh(s)[1]
            if meaning and meaning not in e["meaning"]:
                e["meaning"] += ("；" if e["meaning"] else "") + meaning
        elif section:
            e[section].append(re.sub(r"\s+", " ", s.replace("　", " ")))
    return entries


def parse_function_verbs(paragraphs, fix):
    """第 3 章: 功能动词 → [(词组, 中文, 例句)]"""
    out, last = [], None
    for bold, s in paragraphs:
        de, zh = split_zh(s)
        if bold and zh and " " in de:
            last = [de, zh, ""]
            out.append(last)
        elif last and is_sentence(s) and not last[2]:
            last[2] = fix(s)
    return out


def parse_phrases(paragraphs):
    """附录 2: 'ab und zu (=manchmal)　有时候'"""
    out = []
    for _, s in paragraphs:
        de, zh = split_zh(s)
        if zh and de and " " in de and not re.search(r"[.!?]$", de):
            out.append([de, zh, ""])
    return out


def parse_listed(paragraphs):
    """复合词 'das Krankenhaus = die Kranken + das Haus　医院'、主题词 'das Fett　脂肪' / 'heilbar　adj.　可治愈的'"""
    entries = []
    for _, s in paragraphs:
        m = re.match(r"^(?:(der|die|das) )?([A-Za-zÄÖÜäöüß]+)(?:\s*=\s*([^一-鿿]+?))?[　 ]+(?:[a-z]+\.[　 ]+)?(.*)$", s)
        if m and CJK.match(m.group(4)):
            e = new_entry("dsh", m.group(2), m.group(1) or "", meaning=clean_meaning(m.group(4)))
            e["root"] = (m.group(3) or "").strip()
            entries.append(e)
    return entries


def read_epub():
    z = zipfile.ZipFile(glob.glob(os.path.join(RAW, "德福DSH*.epub"))[0])
    with open(FREQ, encoding="utf-8") as f:
        tokens = {line.split()[0] for line in f}

    def fix(s):
        """排版断词: gegensei-tigen → gegenseitigen (合起来是真词才合, Schiller-Straße 不动)"""
        return re.sub(r"\b(\w+)-(\w+)\b", lambda m: m.group(1) + m.group(2)
                      if (m.group(1) + m.group(2)).lower() in tokens else m.group(0), s)

    verbs = parse_plain_verbs(epub_paragraphs(z, 5)[1:], fix) + parse_prefix_verbs(epub_paragraphs(z, 6), fix)
    listed = parse_listed(epub_paragraphs(z, 8)) + parse_listed(epub_paragraphs(z, 13))
    phrases = parse_function_verbs(epub_paragraphs(z, 7), fix) + parse_phrases(epub_paragraphs(z, 12))
    return verbs, listed, phrases


# ---------- 合并 ----------
def load_fixes():
    with open(FIXES, encoding="utf-8") as f:
        rows = [l.rstrip("\n").split("\t") for l in f if l.strip() and not l.startswith("#")]
    return {r[0]: r[1] for r in rows}


class Book:
    def __init__(self, words):
        self.words = words
        self.index = collections.defaultdict(list)
        for w in words:
            self.add(w)

    def add(self, w):
        w.setdefault("details", {})
        w.setdefault("books", {})
        self.index[w["german"]].append(w)

    def find(self, german, gender=""):
        hits = self.index.get(german, [])
        if gender:   # 同形词(der / das Band)只认冠词相同的
            return next((w for w in hits if w["gender"] == gender), None)
        return hits[0] if hits else None

    def add_new(self, e, level=None):
        """加新词: 名词要有冠词且大写, 其他词要小写, 不符合的(Unangenehm、übersee)说明词条有问题"""
        noun = e["pos"] == "名词"
        if not WORD.fullmatch(e["german"]) or not e["meaning"] or noun != e["german"][0].isupper() \
                or (noun and not e["gender"]):
            return None
        w = {"german": e["german"], "gender": e["gender"], "pos": e["pos"], "plural": "", "meaning": e["meaning"],
             "example": "", "forms": None, "level": level, "rank": 10 ** 9, "new": True}
        self.words.append(w)
        self.add(w)
        return w


def absorb(w, e, rank_meaning, meaning_rank):
    """把一个来源的词条并进单词书的词。rank_meaning 越小的来源越优先"""
    if e["meaning"] and rank_meaning < meaning_rank.get(id(w), 99):
        w["meaning"] = e["meaning"]
        meaning_rank[id(w)] = rank_meaning
    if e["pos"] and not w["pos"]:
        w["pos"] = e["pos"]
    d = w["details"]
    if e["ipa"]:
        d.setdefault("ipa", e["ipa"])
    if e["root"]:
        d.setdefault("root", e["root"])
    for key in ("usage", "phrases", "synonyms", "antonyms", "related", "notes"):
        for x in e[key]:
            if x not in d.setdefault(key, []) and len(d[key]) < LIMITS[key]:
                d[key].append(x)
    for de, zh in e["examples"]:
        pool = d.setdefault("_examples", [])
        if de and not any(x[0] == de for x in pool):
            pool.append((de, zh))


def finish_examples(w):
    """有人工翻译的例句当主例句, 其余放进详情"""
    d = w["details"]
    pool = d.pop("_examples", [])
    main = w["example"].split("\n")[0] if w["example"] else ""
    with_zh = next((x for x in pool if x[1]), None)
    if with_zh:
        if main and main != with_zh[0]:
            pool.append((main, w["example"].split("\n", 1)[1] if "\n" in w["example"] else ""))
        w["example"] = with_zh[0] + "\n" + with_zh[1]
    elif not main and pool:
        w["example"] = pool[0][0]
    main = w["example"].split("\n")[0]
    extras = ["\n".join(x).strip() for x in pool if x[0] != main]
    if extras:
        d["examples"] = extras[:LIMITS["examples"]]


def attach_phrases(book, phrases):
    """词组挂到里面的动词和名词上: unter Kontrolle bringen → bringen, Kontrolle"""
    attached = 0
    for de, zh, example in phrases:
        text = f"{de}　{zh}" + (f"（{example}）" if example else "")
        for token in dict.fromkeys(WORD.findall(de)):
            if token[0].isupper() or token == de.split()[-1]:
                w = book.find(token)
                if w and len(w["details"].setdefault("phrases", [])) < LIMITS["phrases"]:
                    w["details"]["phrases"].append(text)
                    attached += 1
    return attached


def apply_zh_glosses(book, meaning_rank):
    """还是机翻的词用中文维基词典的释义: 词性要对得上(同形的名词和动词不混), 冠词都有时也要相同"""
    if not os.path.exists(ZH_GLOSSES):
        log("没有 data/work/zh_glosses.json, 跳过(先运行 tools/extract_zh_glosses.py)")
        return 0
    with open(ZH_GLOSSES, encoding="utf-8") as f:
        glosses = json.load(f)
    count = 0
    for w in book.words:
        if id(w) in meaning_rank:
            continue
        hits = [g for g in glosses.get(w["german"], [])
                if (not w["pos"] or g["pos"] in w["pos"])
                and (not g["gender"] or not w["gender"] or g["gender"] == w["gender"])]
        if hits:
            w["meaning"] = clean_meaning("；".join(dict.fromkeys(g["meaning"] for g in hits)))
            meaning_rank[id(w)] = 4
            count += 1
    return count


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    with open(SRC, encoding="utf-8") as f:
        src = json.load(f)
    with open(EXCLUDE, encoding="utf-8") as f:     # 排除名单改了不用重新跑前几步(那要读几 GB 文件)
        exclude = {l.split("#")[0].strip() for l in f}
    src["words"] = [w for w in src["words"] if w["german"] not in exclude]
    book = Book(src["words"])
    frdic_a1 = read_frdic(glob.glob(os.path.join(RAW, "欧标A1单词*.csv"))[0])
    frdic_a2 = read_frdic(glob.glob(os.path.join(RAW, "欧标A2单词*.csv"))[0])
    frdic_common = read_frdic(glob.glob(os.path.join(RAW, "德语常用词汇*.csv"))[0])
    anki = read_anki()
    verbs, listed, phrases = read_epub()
    meaning_rank = {}
    stats = collections.Counter()

    # 分级词表: 新词加进这一级, 已有的词级别只降不升
    for level, entries in (("A1", anki), ("A1", frdic_a1), ("A2", frdic_a2)):
        for rank_m, e in [(1 if e["source"] == "anki" else 2, e) for e in entries]:
            w = book.find(e["german"], e["gender"])
            if w is None:
                w = book.add_new(e, level)
                stats["新词(分级词表)" if w else "跳过(词条不规范)"] += 1
            if w is None:
                continue
            if w["level"] and LEVELS.index(level) < LEVELS.index(w["level"]):
                w["level"] = level
                stats["级别调低"] += 1
            absorb(w, e, rank_m, meaning_rank)

    def collect(entries, book_id, can_add):
        for rank, e in enumerate(entries, 1):
            w = book.find(e["german"], e["gender"])
            if w is None and can_add:
                w = book.add_new(e)
                stats["新词(" + book_id + ")" if w else "跳过(词条不规范)"] += 1
            if w is None:
                stats["没匹配上(" + book_id + ")"] += 1
                continue
            # 主题词表只给这个主题下的意思(Krebs 癌症), 原来的释义(螃蟹)要留着
            if not can_add and id(w) not in meaning_rank and e["meaning"] not in w["meaning"] \
                    and w["meaning"] not in e["meaning"]:
                e["meaning"] += "；" + w["meaning"]
            absorb(w, e, 2 if e["source"] == "frdic" else 3, meaning_rank)
            w["books"].setdefault(book_id, rank)

    collect(frdic_common, "common", True)
    collect(verbs, "dsh", True)
    collect(listed, "dsh", False)
    stats["词组挂到词上"] = attach_phrases(book, phrases)

    # 德语助手导出的补充释义: 只改已有的词, 不加新词也不进专题书
    for path in glob.glob(os.path.join(RAW, "补充释义*.csv")):
        for e in read_frdic(path):
            w = book.find(e["german"], e["gender"])
            if w:
                absorb(w, e, 2, meaning_rank)
                stats["德语助手补释义"] += 1
    stats["中文维基词典补释义"] = apply_zh_glosses(book, meaning_rank)

    for german, meaning in load_fixes().items():
        w = book.find(german)
        if w:
            w["meaning"] = meaning
            meaning_rank[id(w)] = 0

    with open(REVIEWED, encoding="utf-8") as f:
        reviewed = {l.strip() for l in f if not l.startswith("#")}
    for w in book.words:
        finish_examples(w)
        if w["german"] in reviewed:
            meaning_rank.setdefault(id(w), 5)
        if id(w) not in meaning_rank:     # 没有任何人工来源的释义: 在 App 里标出来, 别让人当成可靠的
            w["details"]["machine"] = True
        if not w["details"]:
            del w["details"]
        if not w["books"]:
            del w["books"]
    # 级别变了要重新编号: 同一级里仍按原来的顺序(词频), 新词排在这一级最后
    book.words.sort(key=lambda w: (LEVELS.index(w["level"]) if w["level"] else 9, w["rank"]))
    for rank, w in enumerate(book.words, 1):
        w["rank"] = rank
        w.pop("new", None)
    src["about"] += " 释义和用法优先来自 Anki A1 牌组、德语助手生词本、《德福DSH核心词汇详解》, 没覆盖到的才是机器翻译。"
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(src, f, ensure_ascii=False, indent=0)
    google = len(book.words) - len(meaning_rank)
    log(f"完成: {len(book.words)} 个词, 人工释义 {len(meaning_rank)} 个, 仍是谷歌机翻 {google} 个 → {OUT}")
    log("各级: " + str(collections.Counter(w["level"] for w in book.words)))
    log("专题书: " + str(collections.Counter(b for w in book.words for b in w.get("books", {}))))
    log("统计: " + str(dict(stats)))
    log(f"有详情的词 {sum('details' in w for w in book.words)} 个")
    # 还没有人工释义的单词清单, 可以导进德语助手生词本, 再导出成 data/raw/补充释义.csv
    todo = [w["german"] for w in book.words if id(w) not in meaning_rank and WORD.fullmatch(w["german"])]
    with open(TODO, "w", encoding="utf-8") as f:
        f.write("\n".join(dict.fromkeys(todo)) + "\n")
    log(f"待查清单 {len(set(todo))} 个词 → {TODO}")


if __name__ == "__main__":
    main()
