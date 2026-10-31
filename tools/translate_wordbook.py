"""第 3 步(只在电脑上运行): 用谷歌翻译的免费接口给单词和例句加中文, 生成最终单词书

输入:  data/work/wordbook_base.jsonl    第 2 步的输出
输出:  data/work/wordbook_translated.json  机翻版单词书(下一步 merge_wordbook.py 再用人工词典改进)
缓存:  data/work/translate_cache.json   翻过的不会重复请求, 中断后重新运行会接着翻

运行:  python tools/translate_wordbook.py
说明: 用的是网页版谷歌翻译的非官方接口, 不需要账号, 但随时可能限流或失效。
      单词是机器翻译的, 可能不准(例句的翻译一般比较好), 错的可以在 App 里改。
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "work", "wordbook_base.jsonl")
CACHE = os.path.join(ROOT, "data", "work", "translate_cache.json")
OUT = os.path.join(ROOT, "data", "work", "wordbook_translated.json")

URL = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=de&tl=zh-CN&dt=t&q="
WORDS_PER_REQUEST = 40
SENTENCES_PER_REQUEST = 20
PAUSE = 0.6          # 每次请求之间停一下, 别被限流


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def request(text):
    for attempt in range(6):
        try:
            req = urllib.request.Request(URL + urllib.parse.quote(text), headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            return "".join(seg[0] for seg in data[0] if seg[0])
        except Exception as e:  # 限流(429)或网络问题: 等一会再试
            wait = 20 * (attempt + 1)
            log(f"  请求失败({e}), {wait} 秒后重试")
            time.sleep(wait)
    raise RuntimeError("连续失败, 先停下。过一会儿重新运行会接着翻")


def translate_all(texts, per_request, cache, label):
    """一次请求翻多行(用换行隔开), 行数对不上就一行一行地翻"""
    todo = [t for t in dict.fromkeys(texts) if t and t not in cache]
    log(f"{label}: 共 {len(set(texts))} 条, 还要翻 {len(todo)} 条")
    for i in range(0, len(todo), per_request):
        chunk = todo[i:i + per_request]
        lines = request("\n".join(chunk)).split("\n")
        if len(lines) == len(chunk):
            for src, zh in zip(chunk, lines):
                cache[src] = zh.strip()
        else:
            for src in chunk:
                cache[src] = request(src).strip()
                time.sleep(PAUSE)
        save_cache(cache)
        log(f"  {label} {min(i + per_request, len(todo))}/{len(todo)}")
        time.sleep(PAUSE)


def save_cache(cache):
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE)


def word_query(r):
    """名词带冠词翻得更准(der Tisch → 桌子); 反身动词带 sich"""
    if r["gender"]:
        return f'{r["gender"]} {r["german"]}'
    if "sich" in r["pos"]:
        return "sich " + r["german"]
    return r["german"]


def clean(zh, german):
    zh = zh.strip().rstrip("。.")
    if not zh or zh.lower() == german.lower():
        return "（待补充）"
    return zh


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    rows = [json.loads(l) for l in open(SRC, encoding="utf-8")]
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    translate_all([word_query(r) for r in rows], WORDS_PER_REQUEST, cache, "单词")
    translate_all([r["example"] for r in rows], SENTENCES_PER_REQUEST, cache, "例句")
    out = []
    for r in rows:
        ex = r["example"]
        if ex and cache.get(ex):
            ex = ex + "\n" + cache[ex]
        out.append({
            "german": r["german"], "gender": r["gender"], "pos": r["pos"], "plural": r["plural"],
            "meaning": clean(cache.get(word_query(r), ""), r["german"]),
            "example": ex, "forms": r["forms"], "level": r["level"], "rank": r["rank"],
        })
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "about": "通德单词书。A1-B1 主要来自歌德学院词表(整理版 github.com/ilkermeliksitki/goethe-institute-wordlist), "
                     "缺的常用词和 B2/C1 按 FrequencyWords 德语词频补充(B2/C1 不是官方等级); "
                     "冠词/复数/变格/变位/部分例句来自德语维基词典(kaikki.org); 中文是谷歌机器翻译。",
            "words": out,
        }, f, ensure_ascii=False, indent=0)
    log(f"完成: {len(out)} 个词 → {OUT}")


if __name__ == "__main__":
    main()
