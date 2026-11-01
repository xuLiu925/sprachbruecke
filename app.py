"""通德 Sprachbrücke - 德语学习平台 (目前只有「词汇」模块) - Flask + SQLite 后端

运行:  python app.py
环境变量(可选):
  PORT=8000            监听端口
  HOST=0.0.0.0         监听地址(只想本机访问用 127.0.0.1)
  DB_PATH=...          数据库文件路径
  ALLOW_REGISTER=1     允许继续注册新用户(默认: 只有第一个用户可以注册)

代码分布:
  app.py         入口: 创建应用、注册各模块
  database.py    数据库连接、时间工具、建表和迁移
  helpers.py     公共小工具(错误返回、登录检查、读 JSON)
  auth.py        账号
  srs.py         FSRS 复习算法(纯计算)
  vocab.py       词汇模块接口
  today.py       今日学习(每日学习量、今天出哪些词)
  word_add.py    添加单词和管理员审核; word_store.py 放进词库的规则; lexicon.py 德语词典校验
  sentences.py   句子练习(用例句出题)
  lessons.py     情景课(点词查词、加入复习、角色扮演; 课文在 static/lessons.json)
  custom_lessons.py  自建工作对话(AI 生成, 确认后保存)
  explain.py     句子讲解和替换练习(AI 生成, 每句保存一次)
  dictionary.py  查词(德语、变化形式、中文)
  form_drills.py 词形练习(变格、动词变位)
  plural_quiz.py 复数练习(规律判断、练习记录、错题本)
  grammar.py     语法题库(出题、AI 出草稿、管理); 初始题在 grammar_seed.py
  gender_hint.py 词性解释(规则判断, 不用 AI)
  word_parts.py  构词解释(AI 生成, 按词保存一次)
  noun_quiz.py   定冠词填空题(从词库名词自动出题、练习记录、我的词性本)
  article_quiz.py 不定冠词、否定冠词、物主冠词填空题(按格子练, 不按词排期)
  verb_quiz.py   动词现在时填空题(手写句子在 verb_sentences.py)
  tts.py         在线德语发音(设备没有德语语音时用)
  vocab_seed.py  示例词和变格 / 变位
"""
import os
import secrets
from datetime import timedelta

from flask import Flask, send_from_directory

import auth
import custom_lessons
import dictionary
import explain
import form_drills
import gender_hint
import grammar
import lessons
import noun_quiz
import article_quiz
import plural_quiz
import verb_quiz
import sentences
import tts
import today
import vocab
import word_add
import word_parts
from database import BASE, close_db, init_db

SECRET_FILE = os.path.join(BASE, ".secret_key")

app = Flask(__name__, static_folder=os.path.join(BASE, "static"), static_url_path="/static")


def _load_secret():
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "r") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(SECRET_FILE, "w") as f:
        f.write(key)
    try:
        os.chmod(SECRET_FILE, 0o600)
    except OSError:
        pass
    return key


app.secret_key = _load_secret()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=1024 * 1024,  # 请求体最大 1MB
)
app.teardown_appcontext(close_db)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


app.register_blueprint(auth.bp)
app.register_blueprint(vocab.bp)
app.register_blueprint(today.bp)
app.register_blueprint(word_add.bp)
app.register_blueprint(sentences.bp)
app.register_blueprint(lessons.bp)
app.register_blueprint(custom_lessons.bp)
app.register_blueprint(explain.bp)
app.register_blueprint(dictionary.bp)
app.register_blueprint(form_drills.bp)
app.register_blueprint(plural_quiz.bp)
app.register_blueprint(noun_quiz.bp)     # 要在 grammar 前面: /api/grammar/nouns 不能被当成知识点
app.register_blueprint(article_quiz.bp)  # 同上: /api/grammar/articles
app.register_blueprint(verb_quiz.bp)     # 同上: /api/grammar/verbs
app.register_blueprint(grammar.bp)
app.register_blueprint(gender_hint.bp)
app.register_blueprint(word_parts.bp)
app.register_blueprint(tts.bp)

init_db()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        debug=False,
    )
