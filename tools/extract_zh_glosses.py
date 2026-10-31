"""第 3.5 步(只在电脑上运行, 几秒钟, 只有原始数据变了才要重跑): 从中文维基词典抽德语词的中文释义, 转成简体

依赖(只在这一步要, 不进 requirements.txt):  pip install opencc-python-reimplemented
输入:  data/raw/zh-de.jsonl         kaikki.org 整理的中文维基词典德语词条
输出:  data/work/zh_glosses.json    {德语词: [{"pos": "名词", "gender": "der", "meaning": "……"}, ...]}, merge_wordbook.py 用
运行:  python tools/extract_zh_glosses.py
"""
import json
import os
import re
import sys

from opencc import OpenCC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "raw", "zh-de.jsonl")
OUT = os.path.join(ROOT, "data", "work", "zh_glosses.json")

POS = {"noun": "名词", "verb": "动词", "adj": "形容词", "adv": "副词", "pron": "代词", "prep": "介词",
       "conj": "连词", "num": "数词", "particle": "小品词", "det": "冠词"}
GENDER = {"masculine": "der", "feminine": "die", "neuter": "das"}
SKIP_TAGS = {"form-of", "alt-of", "archaic", "obsolete", "dated", "dialectal", "rare", "historical",
             "derogatory", "vulgar", "offensive", "slang"}
FORM_WORDS = re.compile(r"过去分词|现在分词|第.人称|复数形式|变位|变格|属格|与格|宾格|主格|比较级|最高级|的另一种|的异体|拼写")
SENSES = 3        # 最多留几个义项


def clean_gloss(s):
    s = re.sub(r"（[^（）]{7,}）", "", s)       # 太长的括号是解释, 留短的(（常作比喻义）)
    s = s.split("；具体用途")[0]
    return s.strip(" ：:；;，,。")


def senses_of(entry, convert):
    out = []
    for sense in entry.get("senses", []):
        if SKIP_TAGS & set(sense.get("tags", [])) or "form_of" in sense or "alt_of" in sense:
            continue
        for gloss in sense.get("glosses", [])[:1]:
            gloss = clean_gloss(convert(gloss))
            if re.search(r"[一-鿿]", gloss) and not FORM_WORDS.search(gloss) and gloss not in out:
                out.append(gloss)
    return out[:SENSES]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    convert = OpenCC("t2s").convert
    words = {}
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            senses = senses_of(e, convert) if e.get("pos") in POS else []
            if senses:
                gender = next((GENDER[t] for t in e.get("tags") or [] if t in GENDER), "")
                words.setdefault(e["word"], []).append(
                    {"pos": POS[e["pos"]], "gender": gender, "meaning": "；".join(senses)})
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False)
    print(f"完成: {len(words)} 个词 → {OUT}")


if __name__ == "__main__":
    main()
