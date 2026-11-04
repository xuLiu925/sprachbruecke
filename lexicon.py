"""德语词典(只读): 判断一个词是不是真实的德语词, 给出冠词、复数、变格 / 变位

data/lexicon.db 由 tools/build_lexicon.py 生成。没有这个文件时什么都查不到, 新词都走待审核。
词典不全: Hubwagen 这类行业复合词维基词典没有, 所以查不到不代表不是德语词, 要管理员审核。
"""
import json
import os
import sqlite3
import zlib
from contextlib import closing
from pathlib import Path

PATH = os.environ.get("LEXICON_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "lexicon.db"))
LINKS = ("", "s", "es", "n", "en", "e")   # 复合词的连接成分: Arbeit-s-platz
MIN_PART = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS lemmas (
    german TEXT NOT NULL,
    low TEXT NOT NULL,
    gender TEXT NOT NULL,
    pos TEXT NOT NULL,
    plural TEXT NOT NULL,
    meaning TEXT NOT NULL,
    forms BLOB,
    PRIMARY KEY (german, gender)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_lemmas_low ON lemmas (low);
CREATE TABLE IF NOT EXISTS forms (
    form TEXT NOT NULL,
    german TEXT NOT NULL,
    PRIMARY KEY (form, german)
) WITHOUT ROWID;
"""


def connect():
    if not os.path.exists(PATH):
        return None
    db = sqlite3.connect(Path(PATH).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def entry(row):
    d = dict(row)
    del d["low"]
    d["forms"] = json.loads(zlib.decompress(d["forms"])) if d["forms"] else None
    return d


def find(word, gender=""):
    """(原形词条, None) / (None, 原形): 查到的是变化形式时返回原形 / (None, None) 查不到。
    大小写写错也算对(tisch → Tisch); 同形词(der / das Band)写了冠词就按冠词选, 否则名词优先"""
    db = connect()
    if db is None:
        return None, None
    with closing(db):
        rows = db.execute("SELECT * FROM lemmas WHERE low = ?", (word.lower(),)).fetchall()
        if rows:
            rows.sort(key=lambda r: (r["german"] != word, gender != r["gender"], not r["gender"]))
            return entry(rows[0]), None
        form = db.execute("SELECT german FROM forms WHERE form = ? LIMIT 1", (word.lower(),)).fetchone()
        return None, (form["german"] if form else None)


def lemmas_of(word):
    """词形 → 词典里所有可能的原形(regnet → regnen、regen), 本身是原形的排在前面; 查不到返回 []"""
    db = connect()
    if db is None:
        return []
    with closing(db):
        low = word.lower()
        out = [r["german"] for r in db.execute("SELECT german FROM lemmas WHERE low = ?", (low,))]
        out += [r["german"] for r in db.execute("SELECT german FROM forms WHERE form = ?", (low,))]
    return list(dict.fromkeys(out))


def is_noun(db, word):
    return db.execute("SELECT 1 FROM lemmas WHERE low = ? AND gender != '' LIMIT 1", (word.lower(),)).fetchone()


def compound(word):
    """疑似复合词: Hubwagen → "Hub + Wagen"。只给管理员参考, 不自动通过(Staubecken 有两种拆法)"""
    db = connect()
    if db is None:
        return None
    with closing(db):
        for i in range(len(word) - MIN_PART, MIN_PART - 1, -1):
            tail, head = word[i:], word[:i]
            if not is_noun(db, tail):
                continue
            for link in LINKS:
                stem = head[:-len(link)] if link else head
                if head.endswith(link) and len(stem) >= MIN_PART and db.execute(
                        "SELECT 1 FROM lemmas WHERE low = ? LIMIT 1", (stem.lower(),)).fetchone():
                    return f"{stem} + {tail.capitalize()}"
    return None
