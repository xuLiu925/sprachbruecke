"""生成 data/lexicon.db(只在电脑上运行, 要读几 GB 的文件, 单进程一两分钟): 校验用户加的词是不是真实的德语词

输入: data/work/de_entries.jsonl(德语维基词典, 见 extract_wiktionary.py)、data/work/zh_glosses.json(中文维基词典)
输出: data/lexicon.db, 只读, 和 vocab.db 分开, 这样备份还是小文件。手机上用 lexicon.py 查
    lemmas 原形: 德语、冠词、词性、复数、中文释义、变格 / 变位(zlib 压缩的 JSON)
    forms  变化形式 → 原形
"""
import json
import os
import sqlite3
import sys
import zlib

from build_wordbook import ENTRIES, KEEP_POS, POS_ZH, bare, gram_forms, noun_info, verb_info

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lexicon import SCHEMA  # noqa: E402

OUT = os.path.join(ROOT, "data", "lexicon.db")
ZH_GLOSSES = os.path.join(ROOT, "data", "work", "zh_glosses.json")
MAX_MEANING = 60
MAX_FORM = 40


def chinese_meaning(e, gender, pos, glosses):
    """中文维基词典的释义优先, 其次德语维基词典里的中文翻译"""
    hits = [g["meaning"] for g in glosses.get(e["word"], [])
            if (not g["pos"] or g["pos"] in pos) and (not g["gender"] or not gender or g["gender"] == gender)]
    words = hits or [t["word"] for t in e["translations"].get("zh", [])[:3]]
    return "；".join(dict.fromkeys(words))[:MAX_MEANING]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with open(ZH_GLOSSES, encoding="utf-8") as f:
        glosses = json.load(f)
    tmp = OUT + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    lemmas, forms = 0, 0
    with open(ENTRIES, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if "Grundformeintrag (Deutsch)" not in e["categories"] or e["pos"] not in KEEP_POS:
                continue
            gender, plural, table = "", "", None
            if e["pos"] == "noun":
                gender, plural, table = noun_info(e)
            elif e["pos"] == "verb":
                table = verb_info(e)
            pos = POS_ZH.get(e["pos"], e["pos"])
            blob = zlib.compress(json.dumps(table, ensure_ascii=False).encode("utf-8")) if table else None
            lemmas += db.execute(
                "INSERT OR IGNORE INTO lemmas (german, low, gender, pos, plural, meaning, forms) VALUES (?,?,?,?,?,?,?)",
                (e["word"], e["word"].lower(), gender, pos, plural, chinese_meaning(e, gender, pos, glosses), blob),
            ).rowcount
            shapes = {bare(x["form"]).lower() for x in gram_forms(e)}
            rows = [(s, e["word"]) for s in shapes if s != e["word"].lower() and " " not in s and len(s) <= MAX_FORM]
            forms += db.executemany("INSERT OR IGNORE INTO forms (form, german) VALUES (?,?)", rows).rowcount
    db.commit()
    db.execute("VACUUM")
    db.close()
    os.replace(tmp, OUT)
    print(f"原形 {lemmas} 个, 变化形式 {forms} 个, 文件 {os.path.getsize(OUT) / 1024 / 1024:.1f} MB → {OUT}")


if __name__ == "__main__":
    main()
