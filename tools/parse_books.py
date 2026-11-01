"""第 0.5 步(只在电脑上运行): 把 ocr_books.py 的结果解析成词条, 用 data/lexicon.db 校正 OCR 错误

运行:  python tools/parse_books.py        只用标准库, 几十秒
输入:  data/work/ocr/<书>/*.json, data/lexicon.db, data/wordbook.json
输出:  data/work/book_entries.json    候选词条, 不进词库; 字段见 entry()
       status: ok = 词典里有这个词; fixed = 改了 OCR 错误后词典里有; ambiguous = 原样和改后都是真词(schon / schön),
       用单词书的释义也选不出来, 先保留原样, 要人工看
说明:  词典查不到的词直接丢掉: 解析是靠版式猜的, 这一步把例句碎片和噪音挡在外面, 代价是漏掉词典没有的词。
       例句里的词逐个校正, schon / schön 这种两边都是真词的改不了, 所以例句不能不看就用
"""
import itertools
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OCR = os.path.join(ROOT, "data", "work", "ocr")
OUT = os.path.join(ROOT, "data", "work", "book_entries.json")
FIRST_PAGE = {"exam": 9, "tem4": 10, "core": 12}     # 前面是前言和目录
COLUMN_X = 480                                       # 双栏的书: x 小于这个算左栏
SAME_LINE = 16                                       # 两个框 y 差这么多以内算同一行
MAX_FIXES = 3                                        # 一个词最多改几个字母
MAX_PART = 20                                        # 粘连的词里单个词最长多少字母
MAX_GLUED = 5                                        # 一个粘连的词最多拆成几个
# OCR 常见的认错: 丢变音, ß 认成 B / g, ü 认成 i, e 认成 c
SWAPS = {"a": "ä", "o": "ö", "u": "ü", "i": "ü", "A": "Ä", "O": "Ö", "U": "Ü", "B": "ß", "g": "ß", "c": "e"}
ZH = re.compile(r"[一-鿿]")
LETTERS = "A-Za-zÄÖÜäöüß"
SENSE = re.compile(r"^[(（]\s*\d+\s*[)）]\s*(.*)$")
MARK = re.compile(rf"^[^{LETTERS}一-鿿]*[例图]?[^{LETTERS}一-鿿]*(?=[A-ZÄÖÜ])")
POS = r"(?:V\.|Adj|Adv|Konj|Pr[aä]p|Pron|Num|Part|Interj|Pl\.)"
POS_LINE = re.compile(rf"^{POS}[.．]?\s*(?:[+A-Za-z/.．]*\s*)([一-鿿（(].*)$")
HEAD_GENDER = re.compile(rf"^([{LETTERS}/]+?)\s*([mfn])\.\s*(.*)$")
HEAD_POS = re.compile(rf"^([{LETTERS}/]+?)\s*{POS}\.?\s*(.*)$")
HEAD_ZH = re.compile(rf"^([{LETTERS}/]+)\s*([（(]?[一-鿿].*)$")
HEAD_ALONE = re.compile(rf"^([{LETTERS}/]+)\s*$")
HEAD_CORE = re.compile(rf"^([{LETTERS}/]+)\d?$")
EXAM_WORD = re.compile(rf"^(?:[mfn]\.\s*)?([{LETTERS}/]{{3,}})\s*([（(]?[一-鿿].*)?$")


class Lexicon:
    def __init__(self):
        db = sqlite3.connect(os.path.join(ROOT, "data", "lexicon.db"))
        self.lemmas = defaultdict(list)
        for german, low, gender, pos in db.execute("SELECT german, low, gender, pos FROM lemmas"):
            self.lemmas[low].append((german, gender, pos))
        self.form_lemmas = defaultdict(list)
        for form, german in db.execute("SELECT form, german FROM forms"):
            self.form_lemmas[form].append(german)
        self.words = set(self.lemmas) | set(self.form_lemmas)
        db.close()
        with open(os.path.join(ROOT, "data", "wordbook.json"), encoding="utf-8") as f:
            self.book = {}
            for w in json.load(f)["words"]:
                self.book.setdefault(w["german"].lower(), w)
        self.common = set(self.book)    # 粘连的词只按常用词拆, 否则 15 万词里的怪词会把好词拆碎
        for w in self.book.values():
            forms = w.get("forms") or {}
            for group in (*(forms.get("cases") or {}).values(), forms.get("praesens") or [], forms.get("past") or []):
                for form in group:
                    self.common.update(re.findall(rf"[{LETTERS}]+", form.lower()))
        self.common |= set("""der die das den dem des ein eine einen einem einer eines ich du er sie es wir ihr mir mich
            dir dich ihm ihn uns euch sich und oder aber in im an am auf aus bei mit nach von vor zu zum zur um für über
            hat ist sind war wird kann nicht man so wie als""".split())

    def variants(self, word, known, limit=MAX_FIXES):
        """把 word 的字母按 SWAPS 替换, 改得少的在前, 只留 known 里有的"""
        spots = [i for i, c in enumerate(word) if c in SWAPS]
        found = []
        for n in range(1, limit + 1):
            for chosen in itertools.combinations(spots, n):
                for letters in itertools.product(*(SWAPS[word[i]] for i in chosen)):
                    chars = list(word)
                    for i, c in zip(chosen, letters):
                        chars[i] = c
                    text = "".join(chars)
                    if text.lower() in known:
                        found.append(text)
            if found and n > 1:
                break
        return found

    def overlap(self, word, meaning):
        """释义和单词书里这个词的释义有几个相同的汉字"""
        entry = self.book.get(word.lower())
        return len(set(ZH.findall(meaning)) & set(ZH.findall(entry["meaning"]))) if entry else 0

    def fix_head(self, raw, meaning):
        """(校正后的词, status) 或 (None, None)"""
        word = raw.replace("/", "")
        others = self.variants(word, self.lemmas)
        if word.lower() in self.lemmas:
            rivals = [w for w in others if w.lower() in self.book]    # 对手是词典里的怪词时不算有歧义
            if not rivals:
                return word, "ok"
            best = max(rivals, key=lambda w: self.overlap(w, meaning))
            if self.overlap(best, meaning) > self.overlap(word, meaning):
                return best, "fixed"
            return word, "ok" if self.overlap(word, meaning) else "ambiguous"
        if not others:
            return None, None
        return max(others, key=lambda w: (self.overlap(w, meaning), w.lower() in self.book)), "fixed"

    def split_glued(self, token):
        """粘连的词: DieStiftungfordertden → Die Stiftung fördert den; 拆得越少越好, 拆不开返回 None"""
        @lru_cache(maxsize=None)
        def best(start):
            if start == len(token):
                return ()
            options = []
            for end in range(start + 2, min(len(token), start + MAX_PART) + 1):
                part = token[start:end]
                if part.lower() in self.common or (len(part) >= 6 and part.lower() in self.words):
                    word = part
                else:
                    found = self.variants(part, self.common, 2)
                    if not found:
                        continue
                    word = found[0]
                rest = best(end)
                if rest is not None:
                    options.append((word, *rest))
            return min(options, key=len) if options else None
        parts = best(0)
        return " ".join(parts) if parts and len(parts) <= MAX_GLUED else None

    def fix_token(self, token):
        low = token.lower()
        if low in self.common or len(token) < 3:
            return token
        found = self.variants(token, self.common, 2)    # 变位形式也是真词(schlagt), 所以常用词优先
        if found:
            return found[0]
        if low in self.words:
            return token
        found = self.variants(token, self.words, 2)
        return found[0] if found else self.split_glued(token) or token

    def fix_sentence(self, text):
        return re.sub(rf"[{LETTERS}]+", lambda m: self.fix_token(m.group()), text)

    def lemmas_of(self, token):
        return {g.lower() for g in self.form_lemmas.get(token.lower(), ())} | {token.lower()}

    def mentions(self, head, sentence):
        """例句里有没有这个词。版式切错时例句会挂到别的词下面, 这一步挡掉"""
        head = head.lower()
        for token in re.findall(rf"[{LETTERS}]+", sentence):
            low = token.lower()
            if low.startswith(head[:4]) or any(head.endswith(l) for l in self.lemmas_of(token) if len(l) > 2):
                return True
        return False


def read_lines(book):
    """一本书的所有行, 按阅读顺序: [(页, x, 这一页主体的 x, 文字), ...]"""
    result = []
    folder = os.path.join(OCR, book)
    for name in sorted(os.listdir(folder)):
        page = int(name[:4])
        if page < FIRST_PAGE[book]:
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            boxes = json.load(f)
        columns = ([b for b in boxes if b[0] < COLUMN_X], [b for b in boxes if b[0] >= COLUMN_X]) \
            if book == "tem4" else (boxes,)
        for column in columns:
            if not column:
                continue
            body = Counter(round(b[0] / 5) * 5 for b in column).most_common(1)[0][0]
            rows = []
            for b in sorted(column, key=lambda b: b[1]):
                if rows and abs(rows[-1][0][1] - b[1]) < SAME_LINE:
                    rows[-1].append(b)
                else:
                    rows.append([b])
            for row in rows:
                row.sort()
                text = " ".join(b[5] for b in row).strip()
                if not re.search(r"德语考试高频|词汇宝典|核心词汇|^\d+$|^以.*为前缀", text):
                    result.append((page, row[0][0], body, text))
    return result


def zh_ratio(text):
    return len(ZH.findall(text)) / max(len(text.replace(" ", "")), 1)


def head_tem4(line, next_text):
    _, x, body, text = line
    if abs(x - body) > 20 or MARK.sub("", text) != text:
        return None
    m = HEAD_GENDER.match(text)
    if m and (m[3] or ZH.search(next_text)):
        return m[1], m[2], m[3]
    m = HEAD_POS.match(text) or HEAD_ZH.match(text)
    if m:
        return m[1], "", m[2]
    m = HEAD_ALONE.match(text)
    if m and re.match(rf"\s*(=|{POS}|\()", next_text):
        return m[1], "", ""
    return None


def head_core(line, next_text):
    _, x, body, text = line
    m = HEAD_CORE.match(text)
    return (m[1], "", "") if m and x < body - 30 else None


def parse_flow(lines, find_head):
    """按版式切成词条, 词条里的行分成 释义 / 德语句 / 中文句"""
    start = [i for i, line in enumerate(lines)
             if find_head(line, lines[i + 1][3] if i + 1 < len(lines) else "")]
    return [parse_one(lines[a:b], find_head) for a, b in zip(start, start[1:] + [len(lines)])]


def parse_one(block, find_head):
    next_text = block[1][3] if len(block) > 1 else ""
    head = find_head(block[0], next_text)
    cur = {"page": block[0][0], "raw": head[0], "marker": head[1], "meanings": [head[2]] if head[2] else [],
           "examples": []}
    de = None
    in_note = False

    def flush(zh=""):
        nonlocal de
        if de:
            cur["examples"].append([de, zh])
        de = None

    for _, _, _, text in block[1:]:
        text = MARK.sub("", text).strip()
        pos_line = POS_LINE.match(text)
        if pos_line and not cur["meanings"]:      # V.使用
            cur["meanings"].append(pos_line[1])
            continue
        if text.startswith("【"):
            flush()
            in_note = text.startswith(("【记忆", "【用法"))
            continue
        sense = SENSE.match(text)
        if sense:
            flush()
            in_note = False
            if sense[1]:
                cur["meanings"].append(sense[1])
            continue
        if not ZH.search(text) and not text.startswith(("=", "V.", "(")) and (de or len(text.split()) >= 2):
            in_note = False
            de = (de[:-1] + text if de.endswith("-") else de + " " + text) if de else text
            continue
        if de and zh_ratio(text) > 0.3:
            flush(text)
            in_note = False
            continue
        if in_note:
            continue
        last = cur["examples"][-1] if cur["examples"] else None
        if last and last[1] and zh_ratio(text) > 0.5 and not re.search(r"[。！？]$", last[1]):
            last[1] += text
        elif re.search("[~～]", text) and ZH.search(text):     # 用法行: etw. (A) ~ 预知, 感知
            cur["meanings"].append(text)
        elif "【复】" in text:
            tail = re.sub(rf"^.*【复】[^一-鿿]*", "", text)
            cur["marker"] = {"der": "m", "die": "f", "das": "n"}.get(text[:3], cur["marker"])
            if tail:
                cur["meanings"].append(tail)
        elif not cur["meanings"] and zh_ratio(text) > 0.5:
            cur["meanings"].append(text)
    flush()
    return cur


def parse_exam(lines_by_page):
    """这本书主要是表格: 德语词在一个框里, 释义在同一框或右边的框"""
    entries = []
    for page, rows in lines_by_page:
        for row in rows:
            for i, box in enumerate(row):
                m = EXAM_WORD.match(box[5].strip())
                if not m:
                    continue
                meaning = m[2] or ""
                if not meaning and i + 1 < len(row) and zh_ratio(row[i + 1][5]) > 0.5:
                    meaning = row[i + 1][5]
                if meaning:
                    entries.append({"page": page, "raw": m[1], "marker": "", "meanings": [meaning], "examples": []})
    return entries


def exam_rows():
    folder = os.path.join(OCR, "exam")
    for name in sorted(os.listdir(folder)):
        page = int(name[:4])
        if page < FIRST_PAGE["exam"]:
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            boxes = json.load(f)
        rows = []
        for b in sorted(boxes, key=lambda b: b[1]):
            if rows and abs(rows[-1][0][1] - b[1]) < SAME_LINE:
                rows[-1].append(b)
            else:
                rows.append([b])
        for row in rows:
            row.sort()
        yield page, rows


def clean_meaning(text):
    """去掉 tem4 词头后面留下的 t. / refl. 和复数词尾, 还有开头的半个括号"""
    text = re.sub(r"^.*[~～]", "", text)
    text = re.sub(r"^(?:[-–=]?[A-Za-z̈]{0,3}\.?/?V?\.?(?:refl\.|imp\.|[ti]\.)?[,，/\s]*)+(?=[一-鿿（(]|$)", "", text.strip())
    return text.lstrip("）)，,；;、。 ").strip()


def clean_zh(text):
    """译文末尾常粘着水印的几个字: 很客气。多茶壁"""
    return re.sub(r"([。！？])[^。！？]{1,5}$", r"", text.strip())


def entry(lex, book, e):
    meaning = "；".join(filter(None, map(clean_meaning, e["meanings"])))
    german, status = lex.fix_head(e["raw"], meaning)
    if not german:
        return None
    rows = lex.lemmas[german.lower()]
    gender = {"m": "der", "f": "die", "n": "das"}.get(e["marker"], "")
    row = next((r for r in rows if r[0] == german and r[1] == gender), None)         or next((r for r in rows if r[0] == german), rows[0])
    if e["raw"][0].islower() and row[0][0].isupper():    # che → Ehe、naher → Näher: 书上小写的不是名词, 是碎片或变化形式
        return None
    if len(e["raw"].replace("/", "")) < 3:
        return None
    in_book = lex.book.get(german.lower())
    examples = [[lex.fix_sentence(de), clean_zh(zh)] for de, zh in e["examples"] if zh]
    kept = [x for x in examples if lex.mentions(row[0], x[0])]
    lex.dropped += len(examples) - len(kept)
    return {
        "book": book, "page": e["page"], "raw": e["raw"], "german": row[0], "gender": row[1],
        "pos": row[2], "status": status, "meaning": meaning,
        "examples": kept,
        "level": in_book.get("level") if in_book else None, "in_wordbook": bool(in_book),
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    lex = Lexicon()
    lex.dropped = 0
    parsed = {
        "core": parse_flow(read_lines("core"), head_core),
        "tem4": parse_flow(read_lines("tem4"), head_tem4),
        "exam": parse_exam(exam_rows()),
    }
    result = []
    for book, items in parsed.items():
        good = [r for r in (entry(lex, book, e) for e in items) if r]
        result += good
        words = {r["german"].lower() for r in good}
        print(f"{book}: 切出 {len(items)} 条, 词典里有 {len(good)} 条, 不重复 {len(words)} 词, "
              f"其中单词书没有 {len({r['german'].lower() for r in good if not r['in_wordbook']})} 词, "
              f"例句 {sum(len(r['examples']) for r in good)}, 状态 {dict(Counter(r['status'] for r in good))}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=0)
    words = {r["german"].lower(): r for r in result}
    print(f"合计不重复 {len(words)} 词, 单词书没有 {sum(not r['in_wordbook'] for r in words.values())} 词, "
          f"已有的级别 {dict(Counter(r['level'] for r in words.values() if r['level']))}")
    print(f"挂错词条丢掉的例句 {lex.dropped}")
    print(f"写入 {OUT}")


if __name__ == "__main__":
    main()
