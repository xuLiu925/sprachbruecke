"""第 1 步(只在电脑上运行): 从德语维基词典的 wiktextract 数据里抽出德语词条的有用字段

输入:  data/raw/de-extract.jsonl.gz   (https://kaikki.org/dictionary/rawdata.html, 德语版维基词典)
输出:  data/work/de_entries.jsonl      (每行一个德语词条, 只留做单词书要用的字段)

运行:  python tools/extract_wiktionary.py
数据授权: 维基词典内容为 CC BY-SA, 用的时候要注明来源
"""
import gzip
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "raw", "de-extract.jsonl.gz")
OUT = os.path.join(ROOT, "data", "work", "de_entries.jsonl")


def short_examples(sense):
    """自编的短例句(没有出处 ref 的), 最多 2 个"""
    out = []
    for ex in sense.get("examples", []):
        t = ex.get("text", "").strip()
        if t and not ex.get("ref") and len(t) <= 120:
            out.append(t)
        if len(out) >= 2:
            break
    return out


def slim(e):
    senses = []
    for s in e.get("senses", [])[:6]:
        senses.append({
            "gloss": " ".join(s.get("glosses", []))[:200],
            "tags": s.get("tags", []) + s.get("raw_tags", []),
            "examples": short_examples(s),
        })
    tr = {}
    for t in e.get("translations", []):
        lc = t.get("lang_code")
        if lc in ("zh", "en") and t.get("word"):
            tr.setdefault(lc, []).append({"word": t["word"], "sense_index": t.get("sense_index", ""),
                                          "lang": t.get("lang", "")})
    return {
        "word": e["word"],
        "pos": e.get("pos", ""),
        "pos_title": e.get("pos_title", ""),
        "tags": e.get("tags", []),
        "forms": [{k: f[k] for k in ("form", "tags", "pronouns", "article", "raw_tags", "source") if k in f}
                  for f in e.get("forms", [])],
        "senses": senses,
        "translations": tr,
        "categories": [c for c in e.get("categories", []) if "(Deutsch)" in c][:20],
    }


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    n = kept = 0
    with gzip.open(SRC, "rt", encoding="utf-8") as f, open(OUT, "w", encoding="utf-8") as out:
        for line in f:
            n += 1
            if '"lang_code": "de"' not in line:   # 先粗筛, 省得每行都解析 JSON
                continue
            e = json.loads(line)
            if e.get("lang_code") != "de" or not e.get("word"):
                continue
            out.write(json.dumps(slim(e), ensure_ascii=False) + "\n")
            kept += 1
            if kept % 50000 == 0:
                print(f"  已读 {n} 行, 留下 {kept} 个德语词条", file=sys.stderr)
    print(f"完成: 共 {n} 行, 德语词条 {kept} 个 → {OUT}")


if __name__ == "__main__":
    main()
