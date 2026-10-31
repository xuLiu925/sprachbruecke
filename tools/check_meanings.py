"""检查还是谷歌机翻的释义: 和 HanDeDict(中德词典)对不上的列出来, 人工审校后写进 tools/wordbook_fixes.tsv

输入:  data/wordbook.json, data/work/wordbook_translated.json, data/raw/handedict/handedict.u8.gz
输出:  data/work/suspect_meanings.tsv     级别<Tab>德语词<Tab>词性<Tab>释义<Tab>HanDeDict 的说法, 按级别和词频排
运行:  python tools/check_meanings.py
HanDeDict 噪音大(brauchen → 得, andauern → 㝉), 不直接替换释义, 只用来找可疑的词。词典里没有这个词的不算可疑
"""
import collections
import gzip
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOK = os.path.join(ROOT, "data", "wordbook.json")
GOOGLE = os.path.join(ROOT, "data", "work", "wordbook_translated.json")
DICT = os.path.join(ROOT, "data", "raw", "handedict", "handedict.u8.gz")
OUT = os.path.join(ROOT, "data", "work", "suspect_meanings.tsv")


def read_dict():
    index = collections.defaultdict(list)
    with gzip.open(DICT, "rt", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"\S+ (\S+) \[.*?\] /(.*)/", line)
            if not m:
                continue
            for gloss in re.split(r"[/;]", m.group(2)):
                head = re.sub(r"\(.*?\)|\[.*?\]", "", gloss).strip()
                head = re.sub(r"^(der|die|das|sich) ", "", head)
                index[head].append(m.group(1))
    return index


def agrees(meaning, candidates):
    """释义和词典的说法有没有共同的部分: 整个包含, 或者有两个字相同"""
    for c in candidates:
        if c in meaning or meaning in c:
            return True
        if any(meaning[i:i + 2] in c for i in range(len(meaning) - 1)):
            return True
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with open(BOOK, encoding="utf-8") as f:
        words = json.load(f)["words"]
    with open(GOOGLE, encoding="utf-8") as f:
        google = {(w["german"], w["gender"]): w["meaning"] for w in json.load(f)["words"]}
    index = read_dict()
    left = [w for w in words if google.get((w["german"], w["gender"])) == w["meaning"]]
    known = [w for w in left if w["german"] in index]
    suspects = [w for w in known if not agrees(w["meaning"], index[w["german"]])]
    with open(OUT, "w", encoding="utf-8") as f:
        for w in suspects:
            f.write("\t".join([w["level"] or "", w["german"], w["pos"], w["meaning"],
                               "、".join(dict.fromkeys(index[w["german"]]))[:30]]) + "\n")
    print(f"还是机翻 {len(left)} 个, 词典里有 {len(known)} 个, 对不上 {len(suspects)} 个 → {OUT}")
    print(collections.Counter(w["level"] for w in suspects))


if __name__ == "__main__":
    main()
