"""把外部词典补进 data/lexicon.db(只在电脑上运行, 单进程; 重新跑 build_lexicon.py 后要再跑一次, 可重复跑)

输入: data/work/app_dict/dictionary.jsonl(每行一个词条, 这份数据不公开, 在 data/ 里)
规则: 只增补, 不覆盖。
    已有的词: 只补空的释义、复数和动词变位; 冠词、已有释义、变格都不动; 冠词对不上的词条不用
    大小写不同的词条(deutsch / Deutsch)不用
    新词: 只收单个词, 名词必须有冠词; 专名、缩写、短语、词缀、别的词的变化形式不收。新名词没有变格表
    变化形式: 只加到词典里有的原形上
原文件先备份成 data/lexicon.db.bak(已有备份时不覆盖), 全部写完才替换
"""
import collections
import json
import os
import re
import shutil
import sqlite3
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEXICON = os.path.join(ROOT, "data", "lexicon.db")
SOURCE = os.path.join(ROOT, "data", "work", "app_dict", "dictionary.jsonl")
MAX_MEANING = 60
MAX_FORM = 40
WORD = re.compile(r"[A-Za-zÄÖÜäöüßẞ][A-Za-zÄÖÜäöüßẞ-]+")
CHINESE = re.compile(r"[一-鿿]")
ARTICLE = {"m.": "der", "f.": "die", "n.": "das"}
POS = {
    "noun": "名词", "verb": "动词", "verb.refl": "动词", "adj": "形容词", "adj.ptcp": "形容词", "adv": "副词",
    "adv.pron": "副词", "prep": "介词", "prep.art": "介词", "conj": "连词", "intj": "感叹词", "part": "小品词",
    "pron": "代词", "pron.indef": "代词", "pron.dem": "代词", "pron.pers": "代词", "pron.poss": "代词",
    "pron.rel": "代词", "num": "数词", "num.card": "数词", "num.ord": "数词", "num.frac": "数词",
}


def join_meanings(items):
    """多个词条合成一条释义, 超长时在分号处截断"""
    parts = dict.fromkeys(p.strip() for item in items for p in re.split(r"[；;]", item) if p.strip())
    out = ""
    for p in parts:
        text = f"{out}；{p}" if out else p
        if len(text) > MAX_MEANING:
            break
        out = text
    return out or next(iter(parts), "")[:MAX_MEANING]


def plural_of(noun):
    """Betten/Bette → Betten; 写法不规范的(s、Falle(n))不要"""
    if noun.get("nur_in_Singular"):
        return ""
    first = re.split(r"[/,]", noun.get("plural_form") or "")[0].strip()
    return first if WORD.fullmatch(first) and len(first) >= 3 else ""


def verb_forms(e):
    table = {(c["mood"], c["tense"]): c for c in e.get("conjugations", [])}
    pres = table.get(("Indikativ", "Präsens"), {})
    past = table.get(("Indikativ", "Präteritum"), {})
    perfect = table.get(("Indikativ", "Perfekt"), {})
    forms = {}
    persons = [pres.get(k) for k in ("ich", "du", "er_sie_es", "wir", "ihr", "sie")]
    if all(persons):
        forms["praesens"] = persons
    if past.get("ich") and perfect.get("er_sie_es"):
        forms["past"] = [past["ich"], perfect["er_sie_es"]]
    return forms or None


def zu_infinitive(word, words):
    """abzufüllen → abfüllen: 带 zu 的不定式不是原形; zuzahlen 开头的 zu 是前缀, 不算"""
    return any(m.start() and word[:m.start()] + word[m.end():] in words for m in re.finditer("zu", word))


def blob(forms):
    return zlib.compress(json.dumps(forms, ensure_ascii=False).encode("utf-8")) if forms else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    backup = LEXICON + ".bak"
    if not os.path.exists(backup):
        shutil.copy2(LEXICON, backup)
    tmp = LEXICON + ".tmp"
    shutil.copy2(LEXICON, tmp)
    db = sqlite3.connect(tmp)
    rows = {}
    lows = collections.defaultdict(list)
    for german, gender, plural, meaning, has_forms in db.execute(
            "SELECT german, gender, plural, meaning, forms IS NOT NULL FROM lemmas"):
        rows[german, gender] = {"plural": plural, "meaning": meaning, "has_forms": has_forms}
        lows[german.lower()].append((german, gender))

    # 已知的变化形式不收成新词: lexicon.find 先查原形, 收了就挡住“这是某词的变化形式”的提示
    # 外部数据的方向有时是反的(Grammatiktabellen 列出 Grammatiktabelle), 所以原形比变化形式长的不算
    known_forms = {form for form, in db.execute("SELECT form FROM forms")}
    verbs_seen = set(lows)
    with open(SOURCE, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            word = e["word"]
            verbs_seen.add(word.lower())
            if WORD.fullmatch(word):
                known_forms.update(x.lower() for x in e.get("forms", [])
                                   if x.lower() != word.lower() and len(word) <= len(x))

    stats = collections.Counter()
    glosses = collections.defaultdict(list)    # (德语, 冠词) → 中文释义
    plurals, verbs, new, forms = {}, {}, {}, []
    with open(SOURCE, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            word, pos = e["word"], e.get("pos")
            noun = e.get("noun") or {}
            gender = ARTICLE.get(noun.get("gender_short"), "")
            gloss = e.get("gloss_zh") or ""
            gloss = gloss if CHINESE.search(gloss) else ""
            key = (word, gender)
            if word.lower() in lows or key in new:
                row = rows.get(key) or new.get(key)
                if row is None:
                    stats["跳过: 已有的词, 冠词或大小写对不上"] += 1
                    continue
                if not row["meaning"] and gloss:
                    glosses[key].append(gloss)
                if pos == "noun" and not row["plural"] and plural_of(noun):
                    plurals.setdefault(key, plural_of(noun))
                if pos in ("verb", "verb.refl") and not row["has_forms"] and verb_forms(e):
                    verbs.setdefault(key, verb_forms(e))
            else:
                kind = POS.get(pos)
                if word.lower() in known_forms or (kind == "动词" and zu_infinitive(word.lower(), verbs_seen)):
                    stats["跳过: 是别的词的变化形式"] += 1
                    continue
                if kind is None or not WORD.fullmatch(word) or len(word) > 100:
                    stats["跳过: 专名、缩写、短语等"] += 1
                    continue
                if (pos == "noun") != bool(gender) or (pos == "noun" and not word[0].isupper()):
                    stats["跳过: 名词没有冠词"] += 1
                    continue
                if not gloss:
                    stats["跳过: 新词没有中文释义"] += 1
                    continue
                new[key] = {"pos": kind, "plural": plural_of(noun), "meaning": "", "has_forms": False,
                            "forms": verb_forms(e) if pos in ("verb", "verb.refl") else None}
                glosses[key].append(gloss)
                lows[word.lower()].append(key)
            shapes = e.get("forms", []) + ([noun.get("plural_form") or "", noun.get("genitive_form") or ""]
                                           if key in new else [])
            forms += [(x.lower(), word) for x in shapes
                      if x.lower() != word.lower() and WORD.fullmatch(x) and len(x) <= MAX_FORM]

    db.executemany("INSERT INTO lemmas (german, low, gender, pos, plural, meaning, forms) VALUES (?,?,?,?,?,?,?)", [
        (g, g.lower(), a, n["pos"], n["plural"], join_meanings(glosses[g, a]), blob(n["forms"]))
        for (g, a), n in new.items()])
    db.executemany("UPDATE lemmas SET meaning = ? WHERE german = ? AND gender = ? AND meaning = ''", [
        (join_meanings(v), *k) for k, v in glosses.items() if k not in new])
    db.executemany("UPDATE lemmas SET plural = ? WHERE german = ? AND gender = ? AND plural = ''", [
        (v, *k) for k, v in plurals.items() if k not in new])
    db.executemany("UPDATE lemmas SET forms = ? WHERE german = ? AND gender = ? AND forms IS NULL", [
        (blob(v), *k) for k, v in verbs.items() if k not in new])
    before = db.execute("SELECT count(*) FROM forms").fetchone()[0]
    db.executemany("INSERT OR IGNORE INTO forms (form, german) VALUES (?,?)", forms)
    added_forms = db.execute("SELECT count(*) FROM forms").fetchone()[0] - before
    db.commit()
    db.execute("VACUUM")
    total, empty = db.execute("SELECT count(*), sum(meaning = '') FROM lemmas").fetchone()
    db.close()
    os.replace(tmp, LEXICON)

    print(f"新词 {len(new)}, 补释义 {sum(k not in new for k in glosses)}, 补复数 {sum(k not in new for k in plurals)}, "
          f"补变位 {sum(k not in new for k in verbs)}, 新变化形式 {added_forms}")
    for reason, n in stats.most_common():
        print(f"{reason}: {n}")
    print(f"词典现有 {total} 个原形, 没有释义 {empty} 个, 文件 {os.path.getsize(LEXICON) / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
