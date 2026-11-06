"""通德 Sprachbrücke - 德语学习平台(词汇、语法、句子、情景课) - Flask + SQLite 后端

运行:  python app.py
环境变量(可选):
  PORT=8000            监听端口
  HOST=0.0.0.0         监听地址(只想本机访问用 127.0.0.1)
  DB_PATH=...          数据库文件路径
  REGISTER_MODE=...    注册方式 email / invite / open(默认: 配了发信用邮箱验证码, 否则要邀请码; 第一个用户直接注册)
  ALLOW_REGISTER=1     旧写法, 等于 REGISTER_MODE=open

代码分布:
  app.py         入口: 创建应用、注册各模块; 用 waitress 运行(没装时退回 Flask 开发服务器)
  alerts.py      给管理员发提醒邮件(接口报错、服务挂了)
  database.py    数据库连接、时间工具、建表和迁移
  helpers.py     公共小工具(错误返回、登录检查、读 JSON)
  auth.py        账号
  billing.py     会员、免费次数、付款(Stripe)
  srs.py         FSRS 复习算法(纯计算)
  vocab.py       词汇模块接口
  today.py       今日学习(每日学习量、今天出哪些词)
  word_add.py    添加单词和管理员审核; word_store.py 放进词库的规则; lexicon.py 德语词典校验
  sentences.py   句子练习(用例句出题)
  lessons.py     情景课(点词查词、加入复习、角色扮演; 课文在 content/lessons.json, 走接口)
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
  verb_quiz.py   动词填空题的接口和现在时出题(手写句子在 verb_sentences.py)
  perfekt_quiz.py 动词完成时出题, 接口在 verb_quiz.py
  verb_usage.py  动词搭配表和出题, 接口在 verb_quiz.py
  tts.py         在线德语发音(设备没有德语语音时用)
  vocab_seed.py  示例词和变格 / 变位
"""
import os
import secrets
from datetime import timedelta

from flask import Flask, got_request_exception, request, send_from_directory

import alerts
import auth
import billing
import custom_lessons
import dictionary
import explain
import feedback
import form_drills
import gender_hint
import grammar
import guide
import lessons
import noun_quiz
import article_quiz
import plural_quiz
import verb_quiz
import perfekt_quiz  # noqa: F401  导入时登记到 verb_quiz.KINDS
import verb_usage  # noqa: F401  同上
import sentences
import tts
import today
import trial
import user_profile
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


@app.route("/sw.js")
def service_worker():
    # Service Worker 要放在网站根目录才能管整个网站; 不让浏览器缓存它, 改了马上生效
    resp = send_from_directory(app.static_folder, "sw.js", mimetype="text/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/tongde.apk")
def android_apk():
    # 安卓 App 安装包(android/build-apk.bat 生成, 不进 git, 随 deploy.bat 上传); 文档 docs/features/android-app.md
    resp = send_from_directory(app.static_folder, "tongde.apk", as_attachment=True, download_name="tongde.apk",
                               mimetype="application/vnd.android.package-archive")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


app.register_blueprint(auth.bp)
app.register_blueprint(billing.bp)   # 在 auth 后面: 先核对登录, 再查免费次数
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
app.register_blueprint(trial.bp)
app.register_blueprint(feedback.bp)
app.register_blueprint(guide.bp)
app.register_blueprint(user_profile.bp)

# 安全响应头: 不许别的网站把页面嵌进 iframe(点击劫持)、只运行本站的脚本(CSP, 万一有 XSS 也跑不了外来脚本)。
# style 允许内联: index.html 里有很多 style="..."; 新加外部资源(CDN、字体、图片网址)要先改这里
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; "
       "form-action 'self'; frame-ancestors 'none'")


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp


def _on_error(sender, exception, **extra):
    """接口报错(500)时给管理员发邮件; 按路由模板分类, /api/words/1 和 /2 算同一种"""
    rule = request.url_rule.rule if request.url_rule else request.path
    alerts.report_error(request.method, rule, exception)


got_request_exception.connect(_on_error, app)

init_db()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    try:
        from waitress import serve
    except ImportError:
        print("没装 waitress, 用 Flask 自带的开发服务器", flush=True)
        app.run(host=host, port=port, debug=False)
    else:
        print(f"waitress 启动, 端口 {port}", flush=True)
        serve(app, host=host, port=port, threads=8)
