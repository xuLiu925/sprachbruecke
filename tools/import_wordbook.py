"""把单词书导入数据库(电脑和手机上都能运行, 只用 Python 自带的库 + 项目代码)

运行(在项目目录下):  python tools/import_wordbook.py data/wordbook.json
                    数据库默认是项目里的 vocab.db, 要导到别处就先设环境变量 DB_PATH
可以重复运行:
  - 新词: 加进词库, 带上变格/变位和级别
  - 已经有的词(德语 + 冠词相同): 释义和已有的变格/变位不动, 只补上缺的部分(如过去式); 例句换成新的;
    更新级别和排序。(用户在 App 里改的内容存在 user_word_edits, 不受影响)
  - 这次单词书里没有了的词(被规则或排除名单踢掉的): 没人学过就删掉, 有人学过就只移出单词书、保留进度
  - 在 App 里删掉过的词: 跳过, 不会加回来
导入前先备份数据库!
"""
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import database  # noqa: E402
from vocab import LEVELS, clean_forms, clean_word  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        words = json.load(f)["words"]
    database.init_db()
    db = sqlite3.connect(database.DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")
    added = updated = skipped = 0
    seen = set(db.execute("SELECT german, gender FROM deleted_words").fetchall())   # 在 App 里删掉过的词不再加回来
    kept = set()   # 这次单词书里有的词
    for d in words:
        row, e = clean_word(d)
        forms, e2 = clean_forms(d.get("forms")) if not e else (None, None)
        if e or e2 or d.get("level") not in LEVELS:
            skipped += 1
            continue
        key = (row[0], row[2])
        if key in seen:          # 单词书里同一个词出现两次, 只用第一次(级别低的)
            continue
        seen.add(key)
        cur = db.execute(
            "INSERT OR IGNORE INTO words (german, pos, gender, plural, meaning, example) VALUES (?,?,?,?,?,?)", row)
        if cur.rowcount:
            word_id = cur.lastrowid
            added += 1
        else:
            word_id = db.execute("SELECT id FROM words WHERE german = ? AND gender = ? AND owner_id IS NULL",
                                 key).fetchone()[0]
            # 例句换成新的(释义不动)。用户自己改的内容在 user_word_edits 里, 不受影响
            db.execute("UPDATE words SET example = ? WHERE id = ?", (row[5], word_id))
            updated += 1
        kept.add(word_id)
        if forms:
            old = db.execute("SELECT forms FROM word_forms WHERE word_id = ?", (word_id,)).fetchone()
            if old is None:
                db.execute("INSERT INTO word_forms (word_id, forms) VALUES (?, ?)", (word_id, forms))
            else:   # 已有的部分不动(可能改过), 只补上缺的(比如原来没有过去式)
                merged = {**json.loads(forms), **json.loads(old[0])}
                db.execute("UPDATE word_forms SET forms = ? WHERE word_id = ?",
                           (json.dumps(merged, ensure_ascii=False), word_id))
        db.execute(
            "INSERT INTO word_levels (word_id, level, rank) VALUES (?, ?, ?) "
            "ON CONFLICT(word_id) DO UPDATE SET level = excluded.level, rank = excluded.rank",
            (word_id, d["level"], int(d["rank"])),
        )
    # 被踢出单词书的词(比如 aah、50er): 没人学过就删掉; 有人学过就只从单词书里拿掉, 保留进度
    removed = unlisted = 0
    for (word_id,) in db.execute("SELECT word_id FROM word_levels").fetchall():
        if word_id in kept:
            continue
        if db.execute("SELECT 1 FROM progress WHERE word_id = ? LIMIT 1", (word_id,)).fetchone():
            db.execute("DELETE FROM word_levels WHERE word_id = ?", (word_id,))
            unlisted += 1
        else:
            db.execute("DELETE FROM words WHERE id = ?", (word_id,))
            removed += 1
    db.commit()
    counts = db.execute("SELECT level, COUNT(*) FROM word_levels GROUP BY level ORDER BY level").fetchall()
    db.close()
    print(f"新增 {added} 个, 已有的更新 {updated} 个, 格式不对跳过 {skipped} 个")
    print(f"不在单词书里了: 删除 {removed} 个(没人学过), 只移出单词书 {unlisted} 个(有人学过, 保留进度)")
    print("各级词数:", ", ".join(f"{lv} {n}" for lv, n in counts))


if __name__ == "__main__":
    main()
