"""数据库: 连接、时间工具、建表和迁移"""
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone

from flask import g

from srs import W
from vocab_seed import SEED_WORDS, seed_forms

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE, "vocab.db"))

# 旧版 Leitner 盒子的间隔(天), 只在把旧进度换算成 FSRS 时用
LEGACY_INTERVALS = [0, 1, 2, 4, 8, 16]


# ---------- 时间(全部用 UTC 字符串, 靠字符串比较排序) ----------
TIME_FMT = "%Y-%m-%d %H:%M:%S"


def fmt_time(dt):
    return dt.strftime(TIME_FMT)


def parse_time(s):
    return datetime.strptime(s, TIME_FMT).replace(tzinfo=timezone.utc)


def now_str():
    return fmt_time(datetime.now(timezone.utc))


# ---------- 连接 ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------- 建表和迁移 ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);
-- owner_id 为空 = 公共词库(单词书、示例词); 有值 = 这个用户自己加的私有词, 只有他能看到
-- 唯一性(公共词之间 / 同一个人的私有词之间)用 migrate() 里建的两个部分索引保证
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    german TEXT NOT NULL,
    pos TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    plural TEXT NOT NULL DEFAULT '',
    meaning TEXT NOT NULL,
    example TEXT NOT NULL DEFAULT '',
    owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS progress (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    next_review TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 0,  -- 旧版 Leitner 熟练度, 已不再使用
    stability REAL,                    -- FSRS 记忆稳定性(天)
    difficulty REAL,                   -- FSRS 难度 1..10
    last_review TEXT,
    reps INTEGER NOT NULL DEFAULT 0,       -- 复习次数
    lapses INTEGER NOT NULL DEFAULT 0,     -- 学过之后又忘了的次数
    spell_ok INTEGER NOT NULL DEFAULT 0,   -- 拼写答对次数
    PRIMARY KEY (user_id, word_id)
);
CREATE INDEX IF NOT EXISTS idx_progress_due ON progress (user_id, next_review);
-- 每次复习评分记一条: 用来撤销上一次评分, 以后也能用来优化 FSRS 参数
--   prev = 评分前的 progress(JSON, 不含 user_id / word_id); NULL 表示评分前是新词。撤销 = 恢复 prev 并删掉这一条
CREATE TABLE IF NOT EXISTS review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL,
    mode TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    prev TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_log ON review_log (user_id, word_id);
-- 名词变格 / 动词变位, JSON:
--   名词 {"cases": {"sg": [一,二,三,四格], "pl": [一,二,三,四格]}}  (带冠词; 无复数时 pl 全空)
--   动词 {"praesens": [ich, du, er/sie/es, wir, ihr, sie/Sie], "past": [过去式, 完成时]}  (past 可选)
CREATE TABLE IF NOT EXISTS word_forms (
    word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
    forms TEXT NOT NULL
);
-- 单词书: 词属于哪一级(A1..C1), rank = 词频排名(越小越常用), 同一级里按它出新词
CREATE TABLE IF NOT EXISTS word_levels (
    word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
    level TEXT NOT NULL,
    rank INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_word_levels ON word_levels (level, rank);
-- 专题单词书(见 vocab.py 的 THEME_BOOKS): 一个词可以同时在几本书里, 也可以不属于任何级别
CREATE TABLE IF NOT EXISTS word_books (
    book TEXT NOT NULL,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    PRIMARY KEY (book, word_id)
);
-- 单词书的详细内容, JSON, 字段都可选: ipa, root(词根), usage, examples, phrases, synonyms, antonyms, related, notes
CREATE TABLE IF NOT EXISTS word_details (
    word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
    details TEXT NOT NULL
);
-- 每个用户自己改过的词(只对他自己生效, 词库原文 words 不动); 删掉这一行 = 恢复原来的内容
--   存的是改后的完整内容; forms 为 NULL 表示他把变格/变位删掉了
CREATE TABLE IF NOT EXISTS user_word_edits (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    german TEXT NOT NULL,
    pos TEXT NOT NULL,
    gender TEXT NOT NULL,
    plural TEXT NOT NULL,
    meaning TEXT NOT NULL,
    example TEXT NOT NULL,
    forms TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, word_id)
);
-- 每个用户「删掉」的词: 只对他自己隐藏, 复习进度保留, 删掉这一行 = 恢复
CREATE TABLE IF NOT EXISTS user_hidden_words (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    hidden_at TEXT NOT NULL,
    PRIMARY KEY (user_id, word_id)
);
-- (旧版) 被真正删掉的词: 重新导入单词书时跳过它们。现在删除改成了按用户隐藏, 这张表只留着兼容
CREATE TABLE IF NOT EXISTS deleted_words (
    german TEXT NOT NULL,
    gender TEXT NOT NULL,
    PRIMARY KEY (german, gender)
);
-- 邀请码: 管理员(第一个注册的用户)生成, 朋友凭码注册; 一次性, 过期作废。used_at 不为空 = 已用过
CREATE TABLE IF NOT EXISTS invites (
    code TEXT PRIMARY KEY,                -- 不带横线的大写字母数字, 显示时加横线
    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    used_at TEXT
);
-- 用户主动加入复习的词(情景课里点的): 还没学的排在新词最前面, 学过(progress 有记录)就不再出现
CREATE TABLE IF NOT EXISTS study_queue (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, word_id)
);
-- 用户自建的工作对话(AI 生成后确认保存的)。data = JSON: lines / glossary / cloze / task, 格式同 static/lessons.json
CREATE TABLE IF NOT EXISTS custom_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    level TEXT NOT NULL,
    title TEXT NOT NULL,
    scene TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_custom_lessons ON custom_lessons (user_id);
-- 句子讲解(AI 生成): 按德语原句保存, 每句只生成一次。data = JSON: words / order / point / similar
CREATE TABLE IF NOT EXISTS sentence_notes (
    sent_key TEXT PRIMARY KEY,   -- 德语原句的 sha1
    de TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
-- 情景课的整句复习进度。item_key 由「对方的话 + 参考回答」算出, 课文没改这一句, 进度就一直有效
CREATE TABLE IF NOT EXISTS sentence_progress (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    next_review TEXT NOT NULL,
    stability REAL NOT NULL,
    difficulty REAL NOT NULL,
    last_review TEXT NOT NULL,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, item_key)
);
CREATE INDEX IF NOT EXISTS idx_sentence_due ON sentence_progress (user_id, next_review);
-- 每个用户的设置, 例如 book = 当前单词书
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);
"""

PROGRESS_NEW_COLS = [
    ("stability", "REAL"), ("difficulty", "REAL"), ("last_review", "TEXT"),
    ("reps", "INTEGER NOT NULL DEFAULT 0"), ("lapses", "INTEGER NOT NULL DEFAULT 0"),
    ("spell_ok", "INTEGER NOT NULL DEFAULT 0"),
]


def rebuild_words(db):
    """老的 words 表是 UNIQUE(german, gender)(所有人共用一个词库)。加私有词以后要改成
    「公共词之间唯一 + 每个人的私有词之间唯一」, SQLite 改不了已有的约束, 只能重建表。
    编号原样保留, 所以 progress / word_forms / word_levels 等引用它的表都不受影响。重建前先备份数据库文件。"""
    db.commit()
    if os.path.exists(DB_PATH):
        backup = DB_PATH + ".bak-before-private-words"
        if not os.path.exists(backup):
            shutil.copy2(DB_PATH, backup)
    db.execute("PRAGMA foreign_keys = OFF")   # 重建期间别让外键级联删除
    db.executescript("""
        BEGIN;
        CREATE TABLE words_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            german TEXT NOT NULL,
            pos TEXT NOT NULL DEFAULT '',
            gender TEXT NOT NULL DEFAULT '',
            plural TEXT NOT NULL DEFAULT '',
            meaning TEXT NOT NULL,
            example TEXT NOT NULL DEFAULT '',
            owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        );
        INSERT INTO words_new (id, german, pos, gender, plural, meaning, example)
            SELECT id, german, pos, gender, plural, meaning, example FROM words;
        DROP TABLE words;
        ALTER TABLE words_new RENAME TO words;
        COMMIT;
    """)
    db.execute("PRAGMA foreign_keys = ON")


def migrate(db):
    """老数据库升级(不删任何数据):
    1. progress 补 FSRS 字段, 并把 Leitner 进度换算过来
    2. words 加 owner_id(私有词), 唯一约束改成按「公共 / 每个人」分别唯一"""
    if "owner_id" not in {r[1] for r in db.execute("PRAGMA table_info(words)")}:
        rebuild_words(db)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_words_public ON words (german, gender) WHERE owner_id IS NULL")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_words_private ON words (owner_id, german, gender) "
               "WHERE owner_id IS NOT NULL")
    cols = {r[1] for r in db.execute("PRAGMA table_info(progress)")}
    for name, typ in PROGRESS_NEW_COLS:
        if name not in cols:
            db.execute(f"ALTER TABLE progress ADD COLUMN {name} {typ}")
    rows = db.execute(
        "SELECT user_id, word_id, next_review, level FROM progress WHERE stability IS NULL"
    ).fetchall()
    for uid, wid, nxt, level in rows:
        days = LEGACY_INTERVALS[min(max(level, 0), len(LEGACY_INTERVALS) - 1)]
        last = parse_time(nxt) - timedelta(days=days)
        db.execute(
            "UPDATE progress SET stability = ?, difficulty = 5, last_review = ?, reps = ? "
            "WHERE user_id = ? AND word_id = ?",
            (max(days, W[0]), fmt_time(last), level, uid, wid),
        )


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    migrate(db)
    if db.execute("SELECT COUNT(*) FROM words").fetchone()[0] == 0:
        db.executemany(
            "INSERT OR IGNORE INTO words (german, pos, gender, plural, meaning, example) "
            "VALUES (?,?,?,?,?,?)",
            SEED_WORDS,
        )
    # 给示例词补上变格/变位(老数据库也会补; 已有的不覆盖)
    db.executemany(
        "INSERT OR IGNORE INTO word_forms (word_id, forms) "
        "SELECT id, ? FROM words WHERE german = ? AND gender = ? AND owner_id IS NULL",
        list(seed_forms()),
    )
    db.commit()
    db.close()
