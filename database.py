"""数据库: 连接、时间工具、建表和迁移"""
import json
import os
import secrets
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone

from flask import g

import lexicon
from grammar_seed import SEED_QUESTIONS
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
-- 总词库: 每个词只有一行。status = public 所有人都能看到; pending 待审核 / rejected 已拒绝, 只有加过的人看得到
-- owner_id 是旧版私有词留下的, 已不再使用(migrate 里转成 status + user_added_words), 全部为空
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    german TEXT NOT NULL,
    pos TEXT NOT NULL DEFAULT '',
    gender TEXT NOT NULL DEFAULT '',
    plural TEXT NOT NULL DEFAULT '',
    meaning TEXT NOT NULL,
    example TEXT NOT NULL DEFAULT '',
    owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'public'
);
-- 用户加过的词: 他自己的“标签”, 待审核的词靠它才看得到
CREATE TABLE IF NOT EXISTS user_added_words (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, word_id)
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
    bonus INTEGER NOT NULL DEFAULT 0,      -- 1 = 单个加的词: 加入当天学习量 +1
    PRIMARY KEY (user_id, word_id)
);
-- 用户自建的工作对话(AI 生成后确认保存的)。data = JSON: lines / glossary / cloze / task, 格式同 content/lessons.json
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
-- 替换练习(AI 生成): 按原句保存, 每句只生成一次。data = JSON 数组: [{cue, answer, answer_zh, hint}]
CREATE TABLE IF NOT EXISTS sentence_drills (
    sent_key TEXT PRIMARY KEY,   -- 德语原句的 sha1
    de TEXT NOT NULL,
    level TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
-- AI 查词的结果: lookup_key = 去空格的小写查询词, 同一个查询只调用一次 AI。data = JSON: german / gender / pos / plural / meaning / example
CREATE TABLE IF NOT EXISTS ai_words (
    lookup_key TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
-- AI 内容的报错: kind = note(讲解) / drill(替换练习), 每句每种只留最新一条。重新生成时告诉 AI, 保存新内容后删掉
CREATE TABLE IF NOT EXISTS content_reports (
    kind TEXT NOT NULL,
    sent_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    reported_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (kind, sent_key)
);
-- 邮箱验证码(email_codes.py): purpose = register / reset / bind, 每个邮箱每种只留最新一个, 只存哈希
CREATE TABLE IF NOT EXISTS email_codes (
    email TEXT NOT NULL,
    purpose TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    tries INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (email, purpose)
);
-- 发过的邮件, 用来限制发送频率
CREATE TABLE IF NOT EXISTS mail_log (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    purpose TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_mail_log_email ON mail_log (email, sent_at);
-- 会员(billing.py): until = 到期时间(UTC), 过期的行留着不删
CREATE TABLE IF NOT EXISTS memberships (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    until TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
-- 付款记录: session_id = Stripe Checkout 会话编号; status = open / paid; amount 以分为单位
CREATE TABLE IF NOT EXISTS payments (
    session_id TEXT PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    plan TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    paid_at TEXT
);
-- 免费用户每天用了几次(billing.py 的 LIMITS); day = 用户本地日期(凌晨 4 点换日)
-- 情景课按课记: feature = lesson:课程编号, 看过的课以后随时能再看
CREATE TABLE IF NOT EXISTS usage_daily (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day TEXT NOT NULL,
    feature TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day, feature)
);
-- 意见反馈(「我的」页随便写的, 不针对某道题): page = 写反馈时在哪个页面; done_at 不为空 = 管理员处理过
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    page TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    done_at TEXT
);
-- 语法题库(手写题和 AI 题)。topic = 知识点 id; prompt 里的 ___ 是空; 选项在 grammar.py 的 TOPICS 里
--   source = seed / manual / ai; status = active / hidden(停用, 保留记录)
CREATE TABLE IF NOT EXISTS grammar_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    prompt TEXT NOT NULL,
    answer TEXT NOT NULL,
    hint TEXT NOT NULL DEFAULT '',
    explain TEXT NOT NULL DEFAULT '',
    zh TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'seed',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    UNIQUE (topic, prompt)
);
-- AI 联想记忆: 没有规律的名词, 用户点了才生成。只帮助记忆, 不是语法原因
CREATE TABLE IF NOT EXISTS gender_memos (
    german TEXT NOT NULL,
    gender TEXT NOT NULL,
    memo TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (german, gender)
);
-- AI 构词解释: 用户点了才生成, 按词保存。data 是 JSON, {"split": false} = 这个词不用拆
CREATE TABLE IF NOT EXISTS word_parts (
    german TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
-- 定冠词练习记录: 词性的记忆进度, 和 progress(词义)分开。wrong / streak 只算词性答对答错, 复数题、格错、开提示不算
--   stability / difficulty / last_review / next_review = FSRS 状态, 为空 = 老记录, 算到期
--   weak = 1 在错题本里: 词性答错时进, 稳定性到 7 天才出。good_days / last_good_day 已不用
CREATE TABLE IF NOT EXISTS noun_practice (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    seen INTEGER NOT NULL DEFAULT 0,
    wrong INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    last_at TEXT NOT NULL,
    good_days INTEGER NOT NULL DEFAULT 0,
    last_good_day TEXT NOT NULL DEFAULT '',
    stability REAL,
    difficulty REAL,
    last_review TEXT,
    next_review TEXT,
    weak INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, word_id)
);
-- 定冠词每次作答的明细, 以后统计每个格的正确率用。number = 单数 / 复数, case_no = 0–3(一到四格), 不确定时为空
-- kind = 答错的原因 gender(词性) / case(格), 答对或老记录为空; cell = ein / kein / 物主冠词的格子(如 indef:der:3), 定冠词为空
CREATE TABLE IF NOT EXISTS noun_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    number TEXT,
    case_no INTEGER,
    ok INTEGER NOT NULL,
    answered_at TEXT NOT NULL,
    kind TEXT,
    cell TEXT
);
-- 我的词性本: 用户自己挑的名词
CREATE TABLE IF NOT EXISTS noun_list (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, word_id)
);
-- 复数练习记录, 字段含义同 noun_practice(冠词和复数是两种能力, 分开记)
CREATE TABLE IF NOT EXISTS plural_practice (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    seen INTEGER NOT NULL DEFAULT 0,
    wrong INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    last_at TEXT NOT NULL,
    good_days INTEGER NOT NULL DEFAULT 0,
    last_good_day TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, word_id)
);
-- 手动加进复数错题本的词
CREATE TABLE IF NOT EXISTS plural_list (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, word_id)
);
-- 动词练习记录, 字段含义同 noun_practice, 练的是动词的变化形式。人称错、开提示不改记忆状态
CREATE TABLE IF NOT EXISTS verb_practice (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    seen INTEGER NOT NULL DEFAULT 0,
    wrong INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    last_at TEXT NOT NULL,
    stability REAL,
    difficulty REAL,
    last_review TEXT,
    next_review TEXT,
    weak INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, word_id)
);
-- 动词每次作答的明细。person = 0–5(ich du er wir ihr sie/Sie); kind = 答错的原因 stem(词形) / person(人称), 答对为空
CREATE TABLE IF NOT EXISTS verb_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    tense TEXT NOT NULL DEFAULT 'praesens',
    person INTEGER,
    ok INTEGER NOT NULL,
    kind TEXT,
    answered_at TEXT NOT NULL
);
-- 手动加进动词错题本的词
CREATE TABLE IF NOT EXISTS verb_list (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, word_id)
);
-- 听写练习记录(听发音写词), 字段含义同 noun_practice; 和词义的 progress 分开排期。见 dictation.py
CREATE TABLE IF NOT EXISTS dict_practice (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    seen INTEGER NOT NULL DEFAULT 0,
    wrong INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    last_at TEXT NOT NULL,
    stability REAL,
    difficulty REAL,
    last_review TEXT,
    next_review TEXT,
    weak INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, word_id)
);
-- 手动加进听写错题本的词
CREATE TABLE IF NOT EXISTS dict_list (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, word_id)
);
-- 完成时练习记录, 字段含义同 verb_practice。作答明细也在 verb_answers(tense = 'perfekt', kind = aux / part / person)
CREATE TABLE IF NOT EXISTS perfekt_practice (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    seen INTEGER NOT NULL DEFAULT 0,
    wrong INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    last_at TEXT NOT NULL,
    stability REAL,
    difficulty REAL,
    last_review TEXT,
    next_review TEXT,
    weak INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, word_id)
);
CREATE TABLE IF NOT EXISTS perfekt_list (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, word_id)
);
-- 动词搭配练习记录, 字段含义同 verb_practice, 按动词算。作答明细在 verb_answers(tense = 'usage', kind = prep / case)
CREATE TABLE IF NOT EXISTS usage_practice (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    seen INTEGER NOT NULL DEFAULT 0,
    wrong INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    last_at TEXT NOT NULL,
    stability REAL,
    difficulty REAL,
    last_review TEXT,
    next_review TEXT,
    weak INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, word_id)
);
CREATE TABLE IF NOT EXISTS usage_list (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    added_at TEXT NOT NULL,
    PRIMARY KEY (user_id, word_id)
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


USER_WORD_TABLES = ("progress", "review_log", "study_queue", "noun_practice", "noun_list", "plural_practice",
                    "plural_list", "verb_practice", "verb_answers", "verb_list", "perfekt_practice", "perfekt_list", "usage_practice", "usage_list",
                    "dict_practice", "dict_list",
                    "user_hidden_words", "user_word_edits")


def keep_own_content(db, owner, word_id, content, old_id):
    """他的内容和词库这一行不同(比如自己写的释义): 留成他自己的版本。content = (德语, 词性, 冠词, 复数, 释义, 例句)"""
    row = db.execute("SELECT german, pos, gender, plural, meaning, example FROM words WHERE id = ?", (word_id,)).fetchone()
    if tuple(row) == tuple(content):
        return
    forms = (db.execute("SELECT forms FROM word_forms WHERE word_id = ?", (old_id,)).fetchone()
             or db.execute("SELECT forms FROM word_forms WHERE word_id = ?", (word_id,)).fetchone())
    db.execute("INSERT OR IGNORE INTO user_word_edits (user_id, word_id, german, pos, gender, plural, meaning, example, "
               "forms, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (owner, word_id, *content, forms[0] if forms else None, now_str()))


def share_private_words(db):
    """旧版的私有词转成“词库一行 + 用户标签”: 同一个词只留一行, 进度搬过来。词典有的公开, 没有的待审核。重复运行没影响"""
    columns = "id, owner_id, german, pos, gender, plural, meaning, example"
    keys = db.execute("SELECT DISTINCT german, gender FROM words WHERE owner_id IS NOT NULL").fetchall()
    if not keys:
        return
    db.commit()
    backup = DB_PATH + ".bak-before-shared-words"
    if os.path.exists(DB_PATH) and not os.path.exists(backup):
        shutil.copy2(DB_PATH, backup)
    db.execute("PRAGMA foreign_keys = ON")
    for german, gender in keys:
        rows = db.execute(f"SELECT {columns} FROM words WHERE german = ? AND gender = ? AND owner_id IS NOT NULL "
                          "ORDER BY id", (german, gender)).fetchall()
        found = db.execute("SELECT id FROM words WHERE german = ? AND gender = ? AND owner_id IS NULL",
                           (german, gender)).fetchone()
        if found:
            keep = found[0]
        else:
            keep = rows[0][0]
            hit = lexicon.find(german, gender)[0]
            if hit and hit["german"] == german and hit["gender"] == gender:
                db.execute("UPDATE words SET owner_id = NULL, status = 'public', pos = ?, "
                           "plural = CASE WHEN ? = '' THEN plural ELSE ? END, "
                           "meaning = CASE WHEN ? = '' THEN meaning ELSE ? END WHERE id = ?",
                           (hit["pos"], hit["plural"], hit["plural"], hit["meaning"], hit["meaning"], keep))
                if hit["forms"]:
                    db.execute("INSERT OR IGNORE INTO word_forms (word_id, forms) VALUES (?, ?)",
                               (keep, json.dumps(hit["forms"], ensure_ascii=False)))
            else:
                db.execute("UPDATE words SET owner_id = NULL, status = 'pending' WHERE id = ?", (keep,))
        for old, owner, *content in rows:
            if old != keep:
                for table in USER_WORD_TABLES:
                    db.execute(f"UPDATE OR IGNORE {table} SET word_id = ? WHERE word_id = ? AND user_id = ?",
                               (keep, old, owner))
            keep_own_content(db, owner, keep, content, old)
            db.execute("INSERT OR IGNORE INTO user_added_words (user_id, word_id, added_at) VALUES (?,?,?)",
                       (owner, keep, now_str()))
            if old != keep:
                db.execute("DELETE FROM words WHERE id = ?", (old,))


def new_uid(db):
    """给用户看的通德 ID: 随机 8 位数字, 注册后不变。不用 users.id, 免得从编号看出总共有多少人"""
    while True:
        uid = str(10 ** 7 + secrets.randbelow(9 * 10 ** 7))
        if db.execute("SELECT 1 FROM users WHERE uid = ?", (uid,)).fetchone() is None:
            return uid


def migrate(db):
    """老数据库升级(不删任何数据):
    1. progress 补 FSRS 字段, 并把 Leitner 进度换算过来
    2. words 加 owner_id, 唯一约束改成按「公共 / 每个人」分别唯一
    3. words 加 status, 私有词转成“词库一行 + 用户标签”
    4. users 加 email(小写; 老账号为空, 在「我的」页绑定)
    5. users 加 uid(通德 ID, 老账号自动补)、nickname(昵称, 空 = 用用户名)、nickname_at(上次改昵称的时间)"""
    cols = {r[1] for r in db.execute("PRAGMA table_info(users)")}
    for name in ("email", "uid", "nickname", "nickname_at"):
        if name not in cols:
            db.execute(f"ALTER TABLE users ADD COLUMN {name} TEXT")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email) WHERE email IS NOT NULL")
    for (rid,) in db.execute("SELECT id FROM users WHERE uid IS NULL").fetchall():
        db.execute("UPDATE users SET uid = ? WHERE id = ?", (new_uid(db), rid))
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_uid ON users (uid) WHERE uid IS NOT NULL")
    if "ip" not in {r[1] for r in db.execute("PRAGMA table_info(mail_log)")}:   # 验证码按 IP 限次(2026-11-04)
        db.execute("ALTER TABLE mail_log ADD COLUMN ip TEXT")
    db.execute("CREATE INDEX IF NOT EXISTS idx_mail_log_ip ON mail_log (ip, sent_at)")
    if "owner_id" not in {r[1] for r in db.execute("PRAGMA table_info(words)")}:
        rebuild_words(db)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_words_public ON words (german, gender) WHERE owner_id IS NULL")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_words_private ON words (owner_id, german, gender) "
               "WHERE owner_id IS NOT NULL")
    if "status" not in {r[1] for r in db.execute("PRAGMA table_info(words)")}:
        db.execute("ALTER TABLE words ADD COLUMN status TEXT NOT NULL DEFAULT 'public'")
    share_private_words(db)
    cols = {r[1] for r in db.execute("PRAGMA table_info(noun_practice)")}
    for name, typ in (("good_days", "INTEGER NOT NULL DEFAULT 0"), ("last_good_day", "TEXT NOT NULL DEFAULT ''"),
                      ("stability", "REAL"), ("difficulty", "REAL"), ("last_review", "TEXT"), ("next_review", "TEXT"),
                      ("weak", "INTEGER NOT NULL DEFAULT 0")):
        if name not in cols:
            db.execute(f"ALTER TABLE noun_practice ADD COLUMN {name} {typ}")
    if "weak" not in cols:                     # 老错题按原来的规则留在错题本里
        db.execute("UPDATE noun_practice SET weak = 1 WHERE wrong > 0 AND streak < 3")
    cols = {r[1] for r in db.execute("PRAGMA table_info(noun_answers)")}
    for name in ("kind", "cell"):
        if name not in cols:
            db.execute(f"ALTER TABLE noun_answers ADD COLUMN {name} TEXT")
    if "bonus" not in {r[1] for r in db.execute("PRAGMA table_info(study_queue)")}:
        db.execute("ALTER TABLE study_queue ADD COLUMN bonus INTEGER NOT NULL DEFAULT 0")
    db.execute("CREATE INDEX IF NOT EXISTS idx_review_log_day ON review_log (user_id, reviewed_at)")
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
    # 语法题库的初始题: 只补没有的, 用户改过或停用的不动
    for topic, items in SEED_QUESTIONS.items():
        db.executemany(
            "INSERT OR IGNORE INTO grammar_questions (topic, prompt, answer, hint, explain, zh, source, created_at) "
            "VALUES (?,?,?,?,?,?,'seed',?)",
            [(topic, *item, now_str()) for item in items],
        )
    db.commit()
    db.close()
