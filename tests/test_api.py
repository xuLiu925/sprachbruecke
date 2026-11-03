import json, os, sqlite3, sys, tempfile, urllib.parse
d = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(d, "t.db")
os.environ["LEXICON_PATH"] = os.path.join(d, "没有词典.db")   # 不用真实词典; 校验的测试有自己的小词典
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
import billing
import database, srs
billing.ENFORCE = False   # 免费次数只在下面会员那一段测
c = A.app.test_client()
J = lambda r: r.get_json()

assert c.get("/").status_code == 200
assert c.get("/api/review/today").status_code == 401
assert c.post("/api/register", json={"username": "ab", "password": "12345678"}).status_code == 400
assert c.post("/api/register", json={"username": "alice", "password": "short"}).status_code == 400
assert c.post("/api/register", data={"username": "alice", "password": "12345678"}).status_code == 400  # 非 JSON
assert c.post("/api/register", json={"username": "alice", "password": "12345678"}).status_code == 200
assert J(c.get("/api/me"))["username"] == "alice"
c2 = A.app.test_client()
assert c2.post("/api/register", json={"username": "bob", "password": "12345678"}).status_code == 403  # 默认关闭注册
# 下面的流程测试不想被每日学习量限制: 量调大, 一轮只出 10 个。今日学习的规则在文件后面单独测
import today as T
T.NEW_PER_REQUEST = 10
assert c.post("/api/today/goal", json={"goal": 500}).status_code == 200

r = J(c.get("/api/review/today"))
print("first batch:", r["due"], r["new"], len(r["cards"]))
assert r["due"] == 0 and r["new"] == 10

assert all(x["mode"] == "recall" and x["is_new"] for x in r["cards"])  # 新词先认词

# FSRS: 新词「良好」→ 3 天后
wid = r["cards"][0]["id"]
ans = lambda rating, mode="recall": J(c.post("/api/review/answer", json={"word_id": wid, "rating": rating, "mode": mode}))
a = ans(3)
assert a["interval_days"] == 3 and a["stability"] == 3.17 and not a["mastered"], a
# 同一天又「忘了」→ 马上到期, 而且下次考拼写
a = ans(1); assert a["interval_days"] == 0 and a["stability"] < 3.17
r = J(c.get("/api/review/today")); assert r["due"] == 1, r["due"]
assert r["cards"][0]["mode"] == "spell"
a = ans(3, "spell"); assert a["interval_days"] >= 1
r = J(c.get("/api/review/today")); assert r["due"] == 0

db = sqlite3.connect(os.environ["DB_PATH"])
def travel(days):  # 假装上次复习是 days 天前, 而且现在已经到期
    db.execute("UPDATE progress SET last_review = datetime(last_review, ?), next_review = datetime('now', '-1 minute') "
               "WHERE word_id = ?", (f"-{days} days", wid)); db.commit()
row = lambda: db.execute("SELECT stability, reps, lapses, spell_ok FROM progress WHERE word_id = ?", (wid,)).fetchone()
assert row()[1:] == (3, 1, 1)  # reps 3, lapses 1, 拼写对 1 次
s0 = row()[0]
travel(2)
r = J(c.get("/api/review/today")); assert r["due"] == 1 and r["cards"][0]["mode"] == "spell"  # reps=3 奇数 → 拼写
a = ans(3, "spell"); assert a["stability"] > s0 and a["interval_days"] > 1
travel(a["interval_days"])
r = J(c.get("/api/review/today")); assert r["cards"][0]["mode"] == "recall"  # reps=4 偶数且拼写对过 → 认词
# 稳定性 >= 21 天且拼写对过 → 已掌握
db.execute("UPDATE progress SET stability = 30 WHERE word_id = ?", (wid,)); db.commit()
travel(30)
a = ans(3); assert a["mastered"] and a["interval_days"] > 30, a
s = J(c.get("/api/stats")); print("stats:", s)
assert s["learned"] == 1 and s["total"] == 15 and s["mastered"] == 1

assert c.post("/api/review/answer", json={"word_id": 9999, "rating": 3}).status_code == 404
assert c.post("/api/review/answer", json={"word_id": "x", "rating": 3}).status_code == 400
assert c.post("/api/review/answer", json={"word_id": wid, "rating": 5}).status_code == 400
assert c.post("/api/review/answer", json={"word_id": wid, "rating": True}).status_code == 400
assert c.post("/api/review/answer", json={"word_id": wid, "rating": 3, "mode": "x"}).status_code == 400
assert c.post("/api/review/answer", json={"word_id": wid, "correct": True}).status_code == 200  # 旧版前端

# 撤销评分: 只能从这个词最近的一次往回撤, 撤完进度恢复原样(新词 → 没有进度)
hid = J(c.get("/api/words?q=haus"))["words"][0]["id"]
undo = lambda log_id: c.post("/api/review/undo", json={"log_id": log_id})
a1 = J(c.post("/api/review/answer", json={"word_id": hid, "rating": 3}))
p1 = db.execute("SELECT * FROM progress WHERE word_id = ?", (hid,)).fetchone()
a2 = J(c.post("/api/review/answer", json={"word_id": hid, "rating": 1}))
assert undo(a1["log_id"]).status_code == 400
assert undo(a2["log_id"]).status_code == 200
assert db.execute("SELECT * FROM progress WHERE word_id = ?", (hid,)).fetchone() == p1
assert undo(a1["log_id"]).status_code == 200
assert db.execute("SELECT 1 FROM progress WHERE word_id = ?", (hid,)).fetchone() is None
assert undo(a1["log_id"]).status_code == 404
assert db.execute("SELECT COUNT(*) FROM review_log WHERE word_id = ?", (hid,)).fetchone()[0] == 0

# 词库列表: 带学习状态, 可搜索
ws = {w["german"]: w for w in J(c.get("/api/words"))["words"]}
assert len(ws) == 15 and ws["Tisch"]["status"] == "mastered" and ws["Lampe"]["status"] == "new"
assert ws["Tisch"]["next_review"] and ws["Lampe"]["next_review"] is None
assert [w["german"] for w in J(c.get("/api/words?q=桌"))["words"]] == ["Tisch"]
assert [w["german"] for w in J(c.get("/api/words?q=haus"))["words"]] == ["Haus"]
assert J(c.get("/api/words?q=%25"))["words"] == []  # % 不当通配符

# 冠词练习: 学过的名词不到 5 个时, 从全部名词里抽
d = J(c.get("/api/drill/articles"))["words"]
assert len(d) == 12 and all(x["gender"] in ("der", "die", "das") for x in d)
# 听写: 学过的词不到 5 个时, 按当前单词书(这里是全部)的顺序出
d = J(c.get("/api/drill/dictation"))["words"]
assert len(d) == 15 and d[0]["german"] == "Tisch" and set(d[0]) == {"id", "german", "gender", "pos", "meaning", "example"}

# 添加 / 批量导入 / 重复 / 非法性别
x = J(c.post("/api/words", json={"german": "Tür", "gender": "die", "plural": "Türen", "meaning": "门"})); assert x["added"] == 1
x = J(c.post("/api/words", json={"german": "Tür", "gender": "die", "meaning": "门"})); assert x["added"] == 0 and x["skipped"] == 1
assert c.post("/api/words", json={"german": "X", "gender": "der?", "meaning": "y"}).status_code == 400
x = J(c.post("/api/words", json=[{"german": "Fenster", "gender": "das", "meaning": "窗"}, {"german": "essen", "meaning": "吃"}])); assert x["added"] == 2

# 变格 / 变位: 示例词自带
f = json.loads(db.execute("SELECT forms FROM word_forms JOIN words ON id = word_id WHERE german = 'Tisch'").fetchone()[0])
assert f["cases"]["sg"] == ["der Tisch", "des Tisches", "dem Tisch", "den Tisch"]
assert f["cases"]["pl"] == ["die Tische", "der Tische", "den Tischen", "die Tische"]
cards = {x["german"]: x for x in J(c.get("/api/review/today"))["cards"]}
assert cards["Lampe"]["forms"]["cases"]["pl"][2] == "den Lampen"
assert cards["Lampe"]["forms"]["cases"]["sg"][1] == "der Lampe"
assert cards["Wasser"]["forms"]["cases"]["pl"] == ["", "", "", ""]
f = json.loads(db.execute("SELECT forms FROM word_forms JOIN words ON id = word_id WHERE german = 'gehen'").fetchone()[0])
assert f == {"praesens": ["gehe", "gehst", "geht", "gehen", "geht", "gehen"]}
assert db.execute("SELECT COUNT(*) FROM word_forms JOIN words ON id = word_id WHERE german = 'schnell'").fetchone()[0] == 0

# 添加时带变化形式
verb = {"praesens": ["fahre", "fährst", "fährt", "fahren", "fahrt", "fahren"]}
x = J(c.post("/api/words", json={"german": "fahren", "pos": "动词", "meaning": "开车", "forms": verb})); assert x["added"] == 1
noun = {"cases": {"sg": ["der Student", "des Studenten", "dem Studenten", "den Studenten"],
                  "pl": ["die Studenten"] * 2 + ["den Studenten", "die Studenten"]}}
x = J(c.post("/api/words", json={"german": "Student", "gender": "der", "meaning": "学生", "forms": noun})); assert x["added"] == 1
assert c.post("/api/words", json={"german": "a1", "meaning": "y", "forms": {"praesens": ["a"] * 5}}).status_code == 400
assert c.post("/api/words", json={"german": "a2", "meaning": "y", "forms": {"praesens": ["a"] * 5 + [""]}}).status_code == 400
assert c.post("/api/words", json={"german": "a3", "meaning": "y", "forms": {"cases": {"sg": ["a"] * 4, "pl": ["a", "", "", ""]}}}).status_code == 400
assert c.post("/api/words", json={"german": "a4", "meaning": "y", "forms": {"bad": 1}}).status_code == 400
assert c.post("/api/words", json={"german": "a5", "meaning": "y", "forms": "x"}).status_code == 400
x = J(c.post("/api/words", json={"german": "a6", "meaning": "y", "forms": {"cases": {"sg": ["a"] * 4}}})); assert x["added"] == 1
assert db.execute("SELECT COUNT(*) FROM word_forms").fetchone()[0] == 12 + 2 + 3
db.close()

# XSS 字符串只是被当作数据存储, 页面用 textContent 渲染
c.post("/api/words", json={"german": "<img src=x onerror=alert(1)>", "meaning": "t"})

# 登录与限速
c3 = A.app.test_client()
assert c3.post("/api/login", json={"username": "alice", "password": "wrongwrong"}).status_code == 401
assert c3.post("/api/login", json={"username": "alice", "password": "12345678"}).status_code == 200
assert J(c.get("/api/me"))["username"] is None                  # 同一账号在 c3 登录, c 下线
assert c.post("/api/login", json={"username": "alice", "password": "12345678"}).status_code == 200
for _ in range(8): c3.post("/api/login", json={"username": "carol", "password": "x"})
assert c3.post("/api/login", json={"username": "carol", "password": "x"}).status_code == 429

# 邀请码: 管理员(第一个用户)生成, 一次性, 过期 / 作废后不能用; 输入时大小写、横线空格都无所谓
assert J(c.get("/api/me"))["admin"] is True
reg = lambda name, code: A.app.test_client().post("/api/register", json={"username": name, "password": "12345678", "invite": code})
assert reg("dave", "XXXX-XXXX").status_code == 400
inv = J(c.post("/api/invites", json={}))["code"]
ci = A.app.test_client()
assert ci.post("/api/register", json={"username": "dave", "password": "12345678",
                                      "invite": inv.lower().replace("-", " ")}).status_code == 200
assert J(ci.get("/api/me")) == {"username": "dave", "admin": False, "email": None, "register": "invite"}
assert reg("erin", inv).status_code == 400                       # 用过了
assert ci.post("/api/invites", json={}).status_code == 403       # 不是管理员
assert ci.get("/api/admin/users").status_code == 403
assert J(c.get("/api/invites"))["invites"][0]["used_by"] == "dave"
dbi = sqlite3.connect(os.environ["DB_PATH"])
inv2 = J(c.post("/api/invites", json={}))["code"]
dbi.execute("UPDATE invites SET expires_at = '2000-01-01 00:00:00' WHERE code = ?", (inv2.replace("-", ""),)); dbi.commit()
assert reg("erin", inv2).status_code == 400
assert J(c.get("/api/invites"))["invites"][0]["status"] == "expired"
inv3 = J(c.post("/api/invites", json={}))["code"]
assert J(c.delete("/api/invites/" + inv3))["deleted"] == 1 and reg("erin", inv3).status_code == 400
dbi.close()
# 改密码: 要输对旧密码
assert ci.post("/api/password", json={"old": "wrongwrong", "new": "abcdefgh"}).status_code == 401
assert ci.post("/api/password", json={"old": "12345678", "new": "short"}).status_code == 400
assert ci.post("/api/password", json={"old": "12345678", "new": "abcdefgh"}).status_code == 200
login = lambda name, pw: A.app.test_client().post("/api/login", json={"username": name, "password": pw}).status_code
assert login("dave", "abcdefgh") == 200 and login("dave", "12345678") == 401
# 管理员重置别人的密码(不能重置自己的)
us = J(c.get("/api/admin/users"))["users"]
did = next(u["id"] for u in us if u["username"] == "dave")
me_id = next(u["id"] for u in us if u["me"])
assert c.post(f"/api/admin/users/{me_id}/reset_password", json={}).status_code == 400
tmp = J(c.post(f"/api/admin/users/{did}/reset_password", json={}))["password"]
assert login("dave", tmp) == 200 and login("dave", "abcdefgh") == 401
# 一个账号同时只能一个设备登录: 新设备登录后旧设备下线; 重置密码后已登录的设备下线; 退出后令牌作废
d1, d2 = A.app.test_client(), A.app.test_client()
assert d1.post("/api/login", json={"username": "dave", "password": tmp}).status_code == 200
assert J(d1.get("/api/me"))["username"] == "dave"
assert d2.post("/api/login", json={"username": "dave", "password": tmp}).status_code == 200
r = d1.get("/api/stats")
assert r.status_code == 401 and "别的设备" in J(r)["error"] and J(d1.get("/api/me"))["username"] is None
assert J(d2.get("/api/me"))["username"] == "dave" and d2.get("/api/stats").status_code == 200
tmp = J(c.post(f"/api/admin/users/{did}/reset_password", json={}))["password"]
assert d2.get("/api/stats").status_code == 401
assert d2.post("/api/login", json={"username": "dave", "password": tmp}).status_code == 200
assert d2.post("/api/logout", json={}).status_code == 200 and d2.get("/api/stats").status_code == 401
assert J(c.get("/api/me"))["username"] is not None             # 管理员没受影响
# 意见反馈和报错汇总: 谁都能写反馈; 只有管理员能看; 已处理后不再显示(报错删掉, 反馈记处理时间)
cf = A.app.test_client()
assert cf.post("/api/feedback", json={"text": "x"}).status_code == 401
assert cf.post("/api/login", json={"username": "dave", "password": tmp}).status_code == 200
assert cf.post("/api/feedback", json={"text": " "}).status_code == 400
assert cf.post("/api/feedback", json={"text": "a" * 1001}).status_code == 400
assert cf.post("/api/feedback", json={"text": "听写页打不开", "page": "dictation"}).status_code == 200
assert cf.get("/api/admin/feedback").status_code == 403
dbf = sqlite3.connect(os.environ["DB_PATH"])
dbf.execute("INSERT INTO content_reports VALUES ('noun', '1', 'Ich sehe ___ Tisch.｜冠词不对', ?, '2026-01-01 00:00:00')", (did,))
dbf.execute("INSERT INTO content_reports VALUES ('note', 'gone', '讲错了', NULL, '2026-01-02 00:00:00')")
dbf.commit()
fb = J(c.get("/api/admin/feedback"))["items"]
assert [x["kind_name"] for x in fb] == ["意见反馈", "句子讲解", "自动出的题"], fb
assert fb[0]["reason"] == "听写页打不开" and fb[0]["user"] == "dave" and fb[0]["page"] == "dictation"
assert fb[1]["target"] == "" and fb[1]["user"] is None
assert fb[2]["word_id"] == 1 and fb[2]["target"].endswith("：Ich sehe ___ Tisch.") and fb[2]["reason"] == "冠词不对"
assert cf.post("/api/admin/feedback/done", json={"type": "feedback", "id": fb[0]["id"]}).status_code == 403
assert J(c.post("/api/admin/feedback/done", json={"type": "feedback", "id": fb[0]["id"]}))["done"] == 1
assert J(c.post("/api/admin/feedback/done", json={"type": "report", "kind": "noun", "key": "1"}))["done"] == 1
assert c.post("/api/admin/feedback/done", json={"type": "x"}).status_code == 400
assert [x["kind_name"] for x in J(c.get("/api/admin/feedback"))["items"]] == ["句子讲解"]
dbf.execute("DELETE FROM content_reports"); dbf.commit(); dbf.close()

# 邮箱注册、邮箱登录、邮件找回密码、绑定邮箱(不真的发信, 把邮件收进 sent)
import re
import email_codes
sent = []
email_codes.sender = lambda to, subject, body: sent.append((to, body))
last_code = lambda: re.search(r"\d{6}", sent[-1][1]).group()
assert J(A.app.test_client().get("/api/me"))["register"] == "invite"     # 没配置发信: 默认邀请码
os.environ["REGISTER_MODE"] = "email"
ce = A.app.test_client()
assert J(ce.get("/api/me")) == {"username": None, "register": "email"}
code_req = lambda cl, name, mail: cl.post("/api/register/code", json={"username": name, "email": mail})
assert code_req(ce, "fr@nk", "f@x.de").status_code == 400                # 用户名不能有 @
assert code_req(ce, "frank", "not-an-email").status_code == 400
assert code_req(ce, "dave", "f@x.de").status_code == 409                 # 用户名已存在
assert code_req(ce, "frank", " Frank@X.de ").status_code == 200 and sent[-1][0] == "frank@x.de"
code1 = last_code()
assert code_req(ce, "frank", "frank@x.de").status_code == 429            # 60 秒内不能再发
regf = lambda code: ce.post("/api/register", json={"username": "frank", "password": "12345678",
                                                   "email": "frank@x.de", "code": code})
assert regf("000000" if code1 != "000000" else "111111").status_code == 400
assert ce.post("/api/register", json={"username": "frank", "password": "12345678", "invite": "X"}).status_code == 400
assert regf(code1).status_code == 200
assert J(ce.get("/api/me"))["email"] == "frank@x.de"
assert regf(code1).status_code in (400, 409)                              # 验证码只能用一次
assert code_req(A.app.test_client(), "frank2", "frank@x.de").status_code == 409   # 邮箱已注册
assert login("FRANK@x.de", "12345678") == 200 and login("frank@x.de", "wrongwrong") == 401
# 验证码输错 5 次作废
dbe = sqlite3.connect(os.environ["DB_PATH"])
dbe.execute("DELETE FROM mail_log"); dbe.commit()
assert code_req(A.app.test_client(), "gina", "gina@x.de").status_code == 200
good = last_code()
cg = A.app.test_client()
for _ in range(5):
    cg.post("/api/register", json={"username": "gina", "password": "12345678", "email": "gina@x.de", "code": "bad"})
assert cg.post("/api/register", json={"username": "gina", "password": "12345678", "email": "gina@x.de",
                                      "code": good}).status_code == 400
# 找回密码: 不存在的邮箱也返回成功但不发信; 设置后其他设备下线
n = len(sent)
assert A.app.test_client().post("/api/password/forgot", json={"email": "nobody@x.de"}).status_code == 200 and len(sent) == n
dbe.execute("DELETE FROM mail_log"); dbe.commit()
cr = A.app.test_client()
assert cr.post("/api/password/forgot", json={"email": "frank@x.de"}).status_code == 200 and len(sent) == n + 1
assert cr.post("/api/password/reset", json={"email": "frank@x.de", "code": last_code(), "new": "short"}).status_code == 400
assert cr.post("/api/password/reset", json={"email": "frank@x.de", "code": last_code(), "new": "newpass99"}).status_code == 200
assert J(cr.get("/api/me"))["username"] == "frank" and ce.get("/api/stats").status_code == 401
assert login("frank", "newpass99") == 200 and login("frank", "12345678") == 401
# 老账号绑定邮箱
cd = A.app.test_client()
assert cd.post("/api/login", json={"username": "dave", "password": tmp}).status_code == 200
assert cd.post("/api/email/code", json={"email": "frank@x.de"}).status_code == 409   # 别人的邮箱
assert cd.post("/api/email/code", json={"email": "dave@x.de"}).status_code == 200
assert cd.post("/api/email", json={"email": "dave@x.de", "code": "000000x"}).status_code == 400
assert J(cd.post("/api/email", json={"email": "dave@x.de", "code": last_code()}))["email"] == "dave@x.de"
assert next(u for u in J(c.get("/api/admin/users"))["users"] if u["username"] == "dave")["email"] == "dave@x.de"
# 全站每天的上限
dbe.execute("DELETE FROM mail_log")
dbe.executemany("INSERT INTO mail_log (email, purpose, sent_at) VALUES (?, 'register', ?)",
                [(f"z{i}@x.de", database.now_str()) for i in range(email_codes.DAILY_MAX)])
dbe.commit()
assert code_req(A.app.test_client(), "hank", "hank@x.de").status_code == 429
dbe.execute("DELETE FROM mail_log"); dbe.commit(); dbe.close()
del os.environ["REGISTER_MODE"]
email_codes.sender = None

# 会员和免费次数(billing.py): dave 是普通用户, alice 是管理员
import hashlib, hmac, time
billing.ENFORCE = True
billing.config = lambda: {"secret_key": "sk_test_x", "webhook_secret": "whsec_t"}
dave_id = next(u for u in J(c.get("/api/admin/users"))["users"] if u["username"] == "dave")["id"]
assert J(cd.get("/api/billing"))["until"] is None and J(cd.get("/api/billing"))["enabled"]
for i in range(3):
    assert cd.get("/api/drill/articles").status_code == 200
r = cd.get("/api/drill/articles")
assert r.status_code == 402 and J(r)["paywall"]
assert J(cd.get("/api/billing"))["usage"] == [{"name": "冠词练习", "used": 3, "limit": 3, "split": False}]
for i in range(4):
    assert c.get("/api/drill/articles").status_code == 200        # 管理员不限
assert cd.get("/api/sentences?mode=cloze").status_code == 200 and cd.get("/api/sentences?mode=cloze").status_code == 200
assert cd.get("/api/sentences?mode=cloze").status_code == 402 and cd.get("/api/sentences?mode=order").status_code == 200
for i in range(3):
    assert cd.get("/api/roleplay/due?count=1").status_code == 200   # 首页只看数量, 不算
assert cd.get("/api/roleplay/due").status_code == 200 and cd.get("/api/roleplay/due").status_code == 402
# 情景课: 每天 1 节新课, 开过的随时能再看
assert cd.post("/api/usage/lesson", json={"id": "a1-1"}).status_code == 200
assert cd.post("/api/usage/lesson", json={"id": "a1-1"}).status_code == 200
assert cd.get("/api/roleplay/lesson/a1-1").status_code == 200
assert cd.post("/api/usage/lesson", json={"id": "a1-2"}).status_code == 402
assert cd.get("/api/roleplay/lesson/a1-2").status_code == 402
assert cd.post("/api/usage/lesson", json={"id": "u999"}).status_code == 200   # 自建的课不算
# 第二天重新算
dbb = sqlite3.connect(os.environ["DB_PATH"])
dbb.execute("UPDATE usage_daily SET day = '2000-01-01'"); dbb.commit()
assert cd.get("/api/drill/articles").status_code == 200
assert cd.post("/api/usage/lesson", json={"id": "a1-1"}).status_code == 200
assert cd.post("/api/usage/lesson", json={"id": "a1-2"}).status_code == 200
# 付款(假的 Stripe)
calls = []
def fake_stripe(method, path, data=None):
    calls.append((method, path, data))
    if method == "POST":
        return {"id": f"cs_test_{len(calls)}", "url": "https://checkout.stripe.com/x"}
    return {"id": path.split("/")[-1], "payment_status": "paid", "amount_total": 1800, "currency": "cny"}
billing.stripe = fake_stripe
assert cd.post("/api/billing/checkout", json={"plan": "week"}).status_code == 400
r = J(cd.post("/api/billing/checkout", json={"plan": "month"}, headers={"Origin": "https://ex.workers.dev"}))
sid = calls[-1] and f"cs_test_{len(calls)}"
assert r["url"] == "https://checkout.stripe.com/x"
assert calls[-1][2]["success_url"] == "https://ex.workers.dev/?paid={CHECKOUT_SESSION_ID}#me"
assert calls[-1][2]["line_items[0][price_data][unit_amount]"] == 1800 and calls[-1][2]["customer_email"] == "dave@x.de"
assert c.get("/api/billing/confirm?session_id=" + sid).status_code == 404     # 别人的付款
assert cd.get("/api/billing/confirm?session_id=bad").status_code == 400
r = J(cd.get("/api/billing/confirm?session_id=" + sid))
assert r["paid"] and r["until"]
until1 = r["until"]
assert J(cd.get("/api/billing"))["usage"] == []
for i in range(4):
    assert cd.get("/api/drill/articles").status_code == 200       # 会员不限
# webhook: 签名不对、太旧都不收; 同一笔再来一次不重复加
def hook(obj, secret="whsec_t", t=None):
    p = json.dumps({"type": "checkout.session.completed", "data": {"object": obj}}).encode()
    t = str(int(time.time()) if t is None else t)
    s = f"t={t},v1=" + hmac.new(secret.encode(), t.encode() + b"." + p, hashlib.sha256).hexdigest()
    return A.app.test_client().post("/api/stripe/webhook", data=p, headers={"Stripe-Signature": s}).status_code
paid = {"id": sid, "payment_status": "paid", "amount_total": 1800, "currency": "cny"}
assert hook(paid, secret="whsec_wrong") == 400 and hook(paid, t=int(time.time()) - 3600) == 400
assert hook(paid) == 200 and J(cd.get("/api/billing"))["until"] == until1
cd.post("/api/billing/checkout", json={"plan": "year"})
sid2 = f"cs_test_{len(calls)}"
assert hook({**paid, "id": sid2}) == 200 and J(cd.get("/api/billing"))["until"] == until1    # 金额对不上
assert hook({**paid, "id": sid2, "amount_total": 12800}) == 200
assert J(cd.get("/api/billing"))["until"] > until1
# 管理员送会员 / 取消
assert cd.post(f"/api/admin/users/{dave_id}/membership", json={"days": 5}).status_code == 403
assert J(c.post(f"/api/admin/users/{dave_id}/membership", json={"days": 0}))["until"] is None
assert cd.get("/api/drill/articles").status_code == 200 and cd.get("/api/drill/articles").status_code == 200
assert cd.get("/api/drill/articles").status_code == 402
assert J(c.post(f"/api/admin/users/{dave_id}/membership", json={"days": 30}))["until"]
assert next(u for u in J(c.get("/api/admin/users"))["users"] if u["id"] == dave_id)["member_until"]
dbb.close()
billing.ENFORCE = False

# 单词书: 还没有分级的词时默认「全部」; 有了以后默认 A1, 新词按 rank 出
assert J(c.get("/api/books"))["current"] == "all"
db = sqlite3.connect(os.environ["DB_PATH"])
ids = {g: i for i, g in db.execute("SELECT id, german FROM words")}
db.executemany("INSERT INTO word_levels (word_id, level, rank) VALUES (?,?,?)",
               [(ids["Katze"], "A1", 2), (ids["Hund"], "A1", 1), (ids["Kind"], "A2", 3)])
db.execute("DELETE FROM study_queue")   # 前面添加的词都进了学习计划, 这里只看单词书出的新词
db.commit()
b = J(c.get("/api/books"))
assert b["current"] == "A1" and b["books"][0] == {"level": "A1", "total": 2, "learned": 0, "mastered": 0}, b
r = J(c.get("/api/review/today"))
assert [x["german"] for x in r["cards"] if x["is_new"]] == ["Hund", "Katze"], r["cards"]
assert c.post("/api/books/current", json={"book": "X9"}).status_code == 400
assert J(c.post("/api/books/current", json={"book": "A2"}))["current"] == "A2"
r = J(c.get("/api/review/today")); assert [x["german"] for x in r["cards"] if x["is_new"]] == ["Kind"]
s = J(c.get("/api/stats")); assert s["book"] == "A2" and s["book_total"] == 1 and s["book_learned"] == 0 and s["book_mastered"] == 0
assert [w["german"] for w in J(c.get("/api/words?level=A1"))["words"]] == ["Hund", "Katze"]
assert J(c.get("/api/words?level=mine"))["words"] and all(w["private"] for w in J(c.get("/api/words?level=mine"))["words"])
# 专题单词书和单词详情
db.executemany("INSERT INTO word_books (book, word_id, rank) VALUES (?,?,?)",
               [("dsh", ids["Kind"], 2), ("dsh", ids["Katze"], 1)])
db.execute("INSERT INTO word_details (word_id, details) VALUES (?, ?)", (ids["Katze"], '{"root": "x", "usage": ["y"]}'))
db.commit()
t = J(c.get("/api/books"))["themes"]
assert t == [{"level": "dsh", "total": 2, "learned": 0, "mastered": 0}], t
assert J(c.post("/api/books/current", json={"book": "dsh"}))["current"] == "dsh"
r = J(c.get("/api/review/today")); assert [x["german"] for x in r["cards"] if x["is_new"]] == ["Katze", "Kind"]
assert [w["german"] for w in J(c.get("/api/words?level=dsh"))["words"]] == ["Katze", "Kind"]
w = J(c.get(f"/api/words/{ids['Katze']}")); assert w["details"]["root"] == "x" and w["books"] == ["dsh"]
assert J(c.get(f"/api/words/{ids['Hund']}"))["details"] is None
c.post("/api/books/current", json={"book": "all"})

# 编辑 / 删除单词, 动词的过去式和完成时
wd = J(c.get(f"/api/words/{ids['Hund']}"))
assert wd["level"] == "A1" and wd["forms"]["cases"]["sg"][0] == "der Hund"
assert wd["status"] == "new" and wd["reps"] is None and wd["next_review"] is None
wt = J(c.get(f"/api/words/{ids['Tisch']}"))   # Tisch 前面复习过并且已掌握
assert wt["status"] == "mastered" and wt["reps"] >= 4 and wt["lapses"] == 1 and wt["next_review"], wt
# 第二个用户 bob(临时打开注册), 用来确认改动只对自己生效
os.environ["ALLOW_REGISTER"] = "1"
cb = A.app.test_client()
assert cb.post("/api/register", json={"username": "bob", "password": "12345678"}).status_code == 200
os.environ["ALLOW_REGISTER"] = "0"
get = lambda cl, i: J(cl.get(f"/api/words/{ids[i]}"))

# 编辑: 只改自己的版本, 原文和 bob 都不受影响
assert c.put(f"/api/words/{ids['Hund']}", json={**wd, "meaning": "狗（犬）"}).status_code == 200
h = get(c, "Hund")
assert h["meaning"] == "狗（犬）" and h["edited"] and h["original"]["meaning"] == "狗"
assert h["forms"]["cases"]["sg"][0] == "der Hund"                          # 不带 forms 就保留
assert get(cb, "Hund")["meaning"] == "狗" and not get(cb, "Hund")["edited"]
assert db.execute("SELECT meaning FROM words WHERE id = ?", (ids["Hund"],)).fetchone()[0] == "狗"
assert [w["meaning"] for w in J(c.get("/api/words?q=犬"))["words"]] == ["狗（犬）"]   # 搜索用自己的版本
assert J(cb.get("/api/words?q=犬"))["words"] == []
assert [w["edited"] for w in J(c.get("/api/words?q=Hund"))["words"]] == [True]
# 改德语拼写也只影响自己(不会和别的词冲突), 复习卡片用自己的版本
assert c.put(f"/api/words/{ids['Hund']}", json={**wd, "german": "Katze", "gender": "die"}).status_code == 200
assert get(c, "Hund")["german"] == "Katze" and get(cb, "Hund")["german"] == "Hund"
assert c.post(f"/api/words/{ids['Hund']}/revert").status_code == 200            # 恢复原来的内容
h = get(c, "Hund"); assert h["german"] == "Hund" and h["meaning"] == "狗" and not h["edited"] and h["original"] is None
# 改得和原文一模一样 = 没改
assert c.put(f"/api/words/{ids['Hund']}", json={**wd}).status_code == 200 and not get(c, "Hund")["edited"]

# 变格/变位: 也是只改自己的
past = {"praesens": ["gehe", "gehst", "geht", "gehen", "geht", "gehen"], "past": ["ging", "ist gegangen"]}
wg = get(c, "gehen")
assert c.put(f"/api/words/{ids['gehen']}", json={**wg, "forms": past}).status_code == 200
assert get(c, "gehen")["forms"]["past"] == ["ging", "ist gegangen"] and "past" not in get(cb, "gehen")["forms"]
assert c.put(f"/api/words/{ids['gehen']}", json={**wg, "forms": {"past": ["ging"]}}).status_code == 400
assert c.put(f"/api/words/{ids['gehen']}", json={**wg, "forms": None}).status_code == 200
assert get(c, "gehen")["forms"] is None and get(cb, "gehen")["forms"] is not None
assert get(c, "gehen")["original"]["forms"]["praesens"][0] == "gehe"

# 删除: 只对自己隐藏, 进度保留, 可以恢复; bob 不受影响
learned0 = J(c.get("/api/stats"))["learned"]
assert c.delete(f"/api/words/{ids['Tisch']}").status_code == 200
assert get(c, "Tisch")["hidden"] and not get(cb, "Tisch")["hidden"]
assert "Tisch" not in [w["german"] for w in J(c.get("/api/words"))["words"]]
assert [w["german"] for w in J(c.get("/api/words?level=hidden"))["words"]] == ["Tisch"]
assert "Tisch" in [w["german"] for w in J(cb.get("/api/words"))["words"]]
assert J(c.get("/api/stats"))["learned"] == learned0 - 1                       # 统计里也不算它
assert db.execute("SELECT COUNT(*) FROM progress WHERE word_id = ?", (ids["Tisch"],)).fetchone()[0] == 1
assert c.delete("/api/words/99999").status_code == 404
assert c.post(f"/api/words/{ids['Tisch']}/unhide").status_code == 200
t = get(c, "Tisch"); assert not t["hidden"] and t["status"] == "mastered"     # 恢复后进度还在
assert J(c.get("/api/stats"))["learned"] == learned0
# 删掉的词不出现在复习新词、冠词练习、听写里
newbefore = [x["german"] for x in J(c.get("/api/review/today"))["cards"] if x["is_new"]]
c.delete(f"/api/words/{ids[newbefore[0]]}")
everything = [x["german"] for x in J(c.get("/api/review/today"))["cards"]] +     [x["german"] for x in J(c.get("/api/drill/articles"))["words"]] + [x["german"] for x in J(c.get("/api/drill/dictation"))["words"]]
assert newbefore[0] not in everything and newbefore[0] in [x["german"] for x in J(cb.get("/api/review/today"))["cards"]]
c.post(f"/api/words/{ids[newbefore[0]]}/unhide")

# 词典里没有的词: 待审核, 只有加过的人看得到; 不同的人加同一个词共用一行, 释义各看各的
z = J(c.post("/api/words", json={"german": "Zebra", "gender": "das", "meaning": "斑马"})); assert z["added"] == 1 and z["pending"] == 1
zid = db.execute("SELECT id FROM words WHERE german = 'Zebra'").fetchone()[0]
zw = J(c.get(f"/api/words/{zid}")); assert zw["private"] and zw["meaning"] == "斑马"
assert [w["private"] for w in J(c.get("/api/words?q=Zebra"))["words"]] == [True]
assert J(cb.get("/api/words?q=Zebra"))["words"] == [] and J(c.get("/api/words?level=mine&q=Zebra"))["words"]
assert cb.get(f"/api/words/{zid}").status_code == 404
assert cb.post("/api/review/answer", json={"word_id": zid, "rating": 3}).status_code == 404
assert cb.delete(f"/api/words/{zid}").status_code == 404
assert cb.put(f"/api/words/{zid}", json={**zw, "meaning": "x"}).status_code == 404
assert J(cb.post("/api/words", json={"german": "Zebra", "gender": "das", "meaning": "斑马(bob)"}))["added"] == 1
assert [w["meaning"] for w in J(cb.get("/api/words?q=Zebra"))["words"]] == ["斑马(bob)"]
assert [w["meaning"] for w in J(c.get("/api/words?q=Zebra"))["words"]] == ["斑马"]
assert db.execute("SELECT COUNT(*) FROM words WHERE german = 'Zebra'").fetchone()[0] == 1
assert J(c.post("/api/words", json={"german": "Zebra", "gender": "das", "meaning": "斑马"}))["added"] == 0
# 公共词库里已经有的不重复加; 删掉过的再加 = 恢复(自己的私有词也一样)
kr = J(c.post("/api/words", json={"german": "Katze", "gender": "die"})); assert (kr["added"], kr["skipped"]) == (0, 1)
c.delete(f"/api/words/{ids['Katze']}")
kr = J(c.post("/api/words", json={"german": "Katze", "gender": "die"})); assert (kr["added"], kr["skipped"]) == (1, 0)
assert not get(c, "Katze")["hidden"] and get(c, "Katze")["meaning"] == "猫"
c.delete(f"/api/words/{zid}")
assert J(c.post("/api/words", json={"german": "Zebra", "gender": "das", "meaning": "斑马"}))["added"] == 1
assert not J(c.get(f"/api/words/{zid}"))["hidden"]
pending_of = lambda name: db.execute("SELECT COUNT(*) FROM words w JOIN user_added_words a ON a.word_id = w.id "
    "JOIN users u ON u.id = a.user_id WHERE w.status != 'public' AND u.username = ?", (name,)).fetchone()[0]
n_public = db.execute("SELECT COUNT(*) FROM words WHERE status = 'public'").fetchone()[0]
assert J(c.get("/api/stats"))["total"] == n_public + pending_of("alice") and J(cb.get("/api/stats"))["total"] == n_public + 1

# 句子练习: 没有中文翻译 / 不适合出题的例句不用; 填空要能在句子里找到目标词(含变位)
import sentences as S
assert S.parse_sentence("Wir gehen heute nach Hause.\n我们今天回家。") == ("Wir gehen heute nach Hause.", "我们今天回家。", ["Wir", "gehen", "heute", "nach", "Hause"])
assert S.parse_sentence("Ja, ich komme gern.\n好的。")[2] == ["Ja", "ich", "komme", "gern"]
for bad in ("Ich lese ein Buch.", "Gib ihr/ihm bitte das Buch.\n请给。", "Hallo!\n你好", "Ich bin. Du bist auch.\n我是。",
            "Sag \"Hallo\" zu ihm.\n说。", "Das ist z.B. gut.\n例如。", "Das ist gut\n好", ""):
    assert S.parse_sentence(bad) is None, bad
geh = S.word_shapes("gehen", "动词", "", json.dumps({"praesens": ["gehe", "gehst", "geht", "gehen", "geht", "gehen"], "past": ["ging", "ist gegangen"]}))
assert S.find_blank("Er ist nach Hause gegangen.", geh) == {"before": "Er ist nach Hause ", "answer": "gegangen", "after": "."}
assert S.find_blank("Ich gehe, du gehst.", geh) is None     # 出现两次
assert "stehe" in S.word_shapes("aufstehen", "动词", "", json.dumps({"praesens": ["stehe auf"]}))
assert S.find_blank("Das ist ein neues Auto.", S.word_shapes("neu", "形容词", "", None))["answer"] == "neues"
assert S.find_blank("Die Söhne spielen.", S.word_shapes("Sohn", "名词", "Söhne", None))["answer"] == "Söhne"
assert c.get("/api/sentences?mode=x").status_code == 400
assert J(c.get("/api/sentences?mode=cloze"))["questions"] == []   # 示例词的例句都没有中文
c.post("/api/words", json={"german": "lesen", "pos": "动词", "meaning": "读", "example": "Ich lese gern Bücher.\n我喜欢看书。",
                           "forms": {"praesens": ["lese", "liest", "liest", "lesen", "lest", "lesen"]}})
q = J(c.get("/api/sentences?mode=cloze"))["questions"]
assert len(q) == 1 and q[0]["blank"]["answer"] == "lese" and q[0]["tokens"] == ["Ich", "lese", "gern", "Bücher"]
assert J(cb.get("/api/sentences?mode=cloze"))["questions"] == []  # 别人的私有词不出现
c.delete(f"/api/words/{q[0]['word_id']}")
assert J(c.get("/api/sentences?mode=order"))["questions"] == []   # 删掉的词不出现

# 情景课: 词形反查原形
assert J(cb.get("/api/lookup?w=gegangen"))["word"] is None  # 示例词 gehen 只有现在时
assert J(cb.get("/api/lookup?w=gehe"))["word"]["german"] == "gehen"
assert J(c.get("/api/lookup?w=gehe"))["word"] is None       # alice 删掉了自己版本的变位, 要按她的版本
assert J(c.get("/api/lookup?w=Tische"))["word"]["german"] == "Tisch"
assert J(c.get("/api/lookup?w=Tisches"))["word"]["german"] == "Tisch"    # 变格
assert J(c.get("/api/lookup?w=Gehen"))["word"]["german"] == "gehen"      # 句首大写
assert J(c.get("/api/lookup?w=schnellen"))["word"]["german"] == "schnell"  # 形容词词尾
assert J(c.get("/api/lookup?w=nichtda"))["word"] is None
assert J(c.get("/api/lookup?w=%25"))["word"] is None and c.get("/api/lookup").status_code == 400
# 加入复习: 公共词排到新词最前面, 学过就不再出现; 课文里的词词库没有时加成私有词, 别人看不到
apfel = ids["Apfel"] if "Apfel" in ids else J(c.get("/api/words?q=Apfel"))["words"][0]["id"]
db.execute("DELETE FROM progress WHERE word_id = ? AND user_id = (SELECT id FROM users WHERE username = 'alice')", (apfel,))
db.execute("DELETE FROM study_queue"); db.commit()                       # 前面添加的词也在计划里, 这里只看这一个
assert c.post("/api/review/queue", json={"word_id": 99999}).status_code == 404
assert J(c.post("/api/review/queue", json={"word_id": apfel}))["queued"]
assert J(c.get("/api/lookup?w=Apfel"))["word"]["queued"] == 1
assert J(c.get("/api/stats"))["queued"] == 1
due0 = J(c.get("/api/review/today"))
assert due0["cards"][due0["due"]]["id"] == apfel and due0["cards"][due0["due"]]["is_new"]
assert len({x["id"] for x in due0["cards"]}) == len(due0["cards"])     # 不重复
la = J(c.post("/api/review/answer", json={"word_id": apfel, "rating": 3}))
assert J(c.get("/api/stats"))["queued"] == 0
c.post("/api/review/undo", json={"log_id": la["log_id"]})
assert J(c.get("/api/stats"))["queued"] == 1    # 撤销后回到队列
pal = {"german": "Palette", "gender": "die", "pos": "名词", "plural": "Paletten", "meaning": "托盘"}
pid = J(c.post("/api/review/queue", json=pal))["word_id"]
assert J(c.post("/api/review/queue", json=pal))["word_id"] == pid         # 不重复加
assert J(c.get(f"/api/words/{pid}"))["private"] and cb.get(f"/api/words/{pid}").status_code == 404
assert c.post("/api/review/queue", json={"german": ""}).status_code == 400

# 情景课内容: 结构完整, 填空的答案在句子里只出现一次
ld = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "lessons.json"), encoding="utf-8"))["lessons"]
assert len(ld) == 15 and len({l["id"] for l in ld}) == 15
assert {lv: sum(l["level"] == lv for l in ld) for lv in ("A1", "A2", "B1")} == {"A1": 5, "A2": 5, "B1": 5}
import re
tok = re.compile(r"[A-Za-zÄÖÜäöüß]+")
for l in ld:
    assert l["title"] and l["scene"] and len(l["lines"]) >= 6, l["id"]
    assert l["task"]["prompt"] and l["task"]["tips"] and len(l["task"]["model"]) == 3, l["id"]
    glossary = {g["german"].lower() for g in l["glossary"]}
    assert len(glossary) == len(l["glossary"]), l["id"]
    for g in l["glossary"]:
        assert g["gender"] in ("", "der", "die", "das") and g["pos"] and g["meaning"] and (g["pos"] != "名词" or g["gender"]), g
    for x in l["lines"]:
        assert x["de"] and x["zh"] and x["who"], x
        for k in x.get("map", {}):
            assert k in tok.findall(x["de"]), (l["id"], k)
    for q in l["cloze"]:
        assert tok.findall(l["lines"][q["line"]]["de"]).count(q["answer"]) == 1, (l["id"], q)
        assert q["base"] and q["meaning"], q

# 角色扮演: 每课至少 3 句; 评分后进入整句复习, 「没说出来」马上到期, 说出来了就排到以后
for l in ld:
    assert len(J(c.get("/api/roleplay/lesson/" + l["id"]))["items"]) >= 3, l["id"]
assert c.get("/api/roleplay/lesson/x").status_code == 404
items = J(c.get("/api/roleplay/lesson/a2-2"))["items"]
assert items[0]["who"] == "司机" and items[0]["answer"] == "Haben Sie die Referenznummer?"
assert all(i["answer"] != i["prompt"] for i in items)
assert J(c.get("/api/roleplay/due")) == {"count": 0, "items": []}
rp = lambda key, rating: c.post("/api/roleplay/answer", json={"key": key, "rating": rating})
k0, k1 = items[0]["key"], items[1]["key"]
assert rp("x", 3).status_code == 404 and rp(k0, 4).status_code == 400 and rp(k0, True).status_code == 400
assert J(rp(k0, 1))["interval_days"] == 0
assert J(rp(k1, 3))["interval_days"] >= 1
due = J(c.get("/api/roleplay/due"))
assert due["count"] == 1 and due["items"][0]["key"] == k0
assert J(rp(k0, 3))["interval_days"] >= 1 and J(c.get("/api/roleplay/due"))["count"] == 0
assert db.execute("SELECT reps, lapses FROM sentence_progress WHERE item_key = ?", (k0,)).fetchone() == (2, 0)
assert J(cb.get("/api/roleplay/due"))["count"] == 0                     # 进度按用户分开
# 课文改掉的旧句子不再出现, 也不报错
db.execute("INSERT INTO sentence_progress VALUES ((SELECT id FROM users WHERE username = 'alice'), 'gone', "
           "'2020-01-01 00:00:00', 1, 5, '2019-12-31 00:00:00', 1, 0)"); db.commit()
assert J(c.get("/api/roleplay/due"))["count"] == 0

# 自建工作对话: AI 的结果必须通过检查才能保存; 保存后能做角色扮演
import custom_lessons as CL
good = {"level": "A2", "title": "少了一托", "scene": "司机发现少了一托。",
        "lines": [{"who": "司机", "de": "Hier fehlt eine Palette.", "zh": "这里少了一托。"},
                  {"who": "Li", "de": "Ich prüfe den Lieferschein.", "zh": "我核对一下送货单。", "map": {"prüfe": "prüfen", "gar": "x"}, "evil": "<b>"},
                  {"who": "司机", "de": "Danke, ich warte hier.", "zh": "谢谢，我在这里等。"},
                  {"who": "Li", "de": "Ich rufe meine Chefin an.", "zh": "我给主管打电话。"}],
        "glossary": [{"german": "Lieferschein", "gender": "der", "pos": "名词", "plural": "Lieferscheine", "meaning": "送货单"},
                     {"german": "Kaputt", "gender": "xx", "pos": "形容词", "meaning": "坏"}],
        "cloze": [{"line": 0, "answer": "Palette", "base": "Palette", "gender": "die", "meaning": "托盘"},
                  {"line": 0, "answer": "NichtDa", "base": "x", "gender": "", "meaning": "y"}, {"line": 99, "answer": "x"}],
        "task": {"prompt": "写 3 句", "tips": ["Ich …"], "model": [{"de": "Ich prüfe das.", "zh": "我检查。"}]}}
ok, e = CL.clean_lesson(good)
assert e is None and len(ok["cloze"]) == 1 and len(ok["glossary"]) == 1
assert ok["lines"][1]["map"] == {"prüfe": "prüfen"} and "evil" not in ok["lines"][1]
for bad, msg in (({**good, "level": "C2"}, "级别"), ({**good, "lines": good["lines"][:2]}, "4–16"),
                 ({**good, "task": None}, "写作任务"), ({**good, "lines": [{**x, "who": "Tom"} for x in good["lines"]]}, "回答太少")):
    assert msg in CL.clean_lesson(bad)[1], msg
assert CL.extract_json("好的：\n```json\n" + json.dumps(good) + "\n```") == good and CL.extract_json("nope") is None
os.environ.pop("GEMINI_API_KEY", None)
assert J(c.get("/api/custom_lessons")) == {"lessons": [], "ai": False}
want = {"level": "A2", "request": "司机来提货发现少了一托"}
assert c.post("/api/custom_lessons/generate", json={"level": "A2", "request": "x"}).status_code == 400
assert c.post("/api/custom_lessons/generate", json=want).status_code == 503      # 没有 Key
assert cb.post("/api/custom_lessons/generate", json=want).status_code == 403     # 只有管理员能用
assert "司机来提货" in J(cb.post("/api/custom_lessons/prompt", json=want))["prompt"]
real_call = CL.call_gemini
CL.call_gemini = lambda prompt: "```json\n" + json.dumps(good) + "\n```"
draft = J(c.post("/api/custom_lessons/generate", json=want))["lesson"]
assert draft["title"] == "少了一托"
CL.call_gemini = lambda prompt: "不是 JSON"
assert c.post("/api/custom_lessons/generate", json=want).status_code == 502
def quota(prompt): raise CL.AiError("额度", 429)
CL.call_gemini = quota
assert c.post("/api/custom_lessons/generate", json=want).status_code == 429
CL.call_gemini = real_call
assert J(c.post("/api/custom_lessons/check", json={"level": "B1", "text": "结果：" + json.dumps(good)}))["lesson"]["level"] == "B1"
assert c.post("/api/custom_lessons/check", json={"text": "abc"}).status_code == 400
saved = J(c.post("/api/custom_lessons", json=draft))["lesson"]
assert saved["id"].startswith("u") and saved["custom"] and J(c.get("/api/custom_lessons"))["lessons"][0]["id"] == saved["id"]
assert J(cb.get("/api/custom_lessons"))["lessons"] == []                         # 别人看不到
ri = J(c.get("/api/roleplay/lesson/" + saved["id"]))["items"]
assert [i["answer"] for i in ri] == ["Ich prüfe den Lieferschein.", "Ich rufe meine Chefin an."]
assert cb.get("/api/roleplay/lesson/" + saved["id"]).status_code == 404
assert J(c.post("/api/roleplay/answer", json={"key": ri[0]["key"], "rating": 1}))["interval_days"] == 0
assert cb.post("/api/roleplay/answer", json={"key": ri[0]["key"], "rating": 1}).status_code == 404
assert [i["key"] for i in J(c.get("/api/roleplay/due"))["items"]] == [ri[0]["key"]]
num = saved["id"][1:]
assert cb.delete("/api/custom_lessons/" + num).status_code == 404
assert c.delete("/api/custom_lessons/" + num).status_code == 200
assert J(c.get("/api/custom_lessons"))["lessons"] == [] and J(c.get("/api/roleplay/due"))["count"] == 0   # 删课后不再复习

# 句子讲解: 每句只调用一次 AI; 讲解的词必须来自这句话; 只有管理员能生成
import explain as EX
sent = {"de": "Mit dem Hubwagen bewegen wir die Paletten.", "zh": "我们用液压车搬托盘。", "level": "A2"}
note = {"words": [{"word": "dem Hubwagen", "base": "der Hubwagen", "form": "单数第三格", "why": "mit 接第三格"},
                  {"word": "Gabelstapler", "base": "der Gabelstapler", "form": "第一格", "why": "不在句子里"}],
        "order": "动词在第二位", "point": "mit + 第三格", "evil": "x",
        "similar": [{"de": "Mit dem Scanner prüfe ich die Ware.", "zh": "我用扫描枪检查货物。"}, {"de": "没有德语", "zh": "错的"}]}
cn, e = EX.clean_note(note, sent["de"])
assert e is None and [w["word"] for w in cn["words"]] == ["dem Hubwagen"] and len(cn["similar"]) == 1 and "evil" not in cn
assert "词" in EX.clean_note({"words": [], "similar": note["similar"]}, sent["de"])[1]
assert "类似" in EX.clean_note({**note, "similar": []}, sent["de"])[1]
ask = "/api/explain?de=" + urllib.parse.quote(sent["de"])
assert J(c.get(ask)) == {"note": None, "report": None, "can": True, "ai": False} and not J(cb.get(ask))["can"]
assert c.post("/api/explain/generate", json={**sent, "level": "C2"}).status_code == 400
assert c.post("/api/explain/generate", json={**sent, "de": "中文句子"}).status_code == 400
assert c.post("/api/explain/generate", json=sent).status_code == 503                # 没有 Key
assert cb.post("/api/explain/generate", json=sent).status_code == 403
calls = []
def fake(prompt):
    calls.append(prompt); return "```json\n" + json.dumps(note) + "\n```"
EX.call_gemini = fake
assert J(c.post("/api/explain/generate", json=sent))["note"] == cn
assert J(c.post("/api/explain/generate", json=sent))["note"] == cn and len(calls) == 1   # 第二次不再调用
assert sent["de"] in calls[0]
assert J(cb.get(ask))["note"] == cn                                                 # 保存后大家都能看
EX.call_gemini = lambda prompt: "没有 JSON"
s2 = {**sent, "de": "Ich hole die Ware ab."}
assert c.post("/api/explain/generate", json=s2).status_code == 502
assert J(c.get("/api/explain?de=" + urllib.parse.quote(s2["de"])))["note"] is None   # 坏结果不保存
assert s2["de"] in J(c.post("/api/explain/prompt", json=s2))["prompt"]
n2 = {"words": [{"word": "hole", "base": "abholen", "form": "ich 的现在时", "why": "可分动词"}], "similar": note["similar"]}
assert c.post("/api/explain/check", json={**s2, "text": "abc"}).status_code == 400
assert J(c.post("/api/explain/check", json={**s2, "text": json.dumps(n2)}))["note"]["words"][0]["base"] == "abholen"
assert cb.post("/api/explain/check", json={**s2, "text": json.dumps(n2)}).status_code == 403

# 替换练习: 每句只生成一次, 和原句相同或没有中文的题去掉; 练过的题进入整句复习
dr = {"drills": [{"cue": "请司机开到二号门", "hint": "Tor zwei", "answer": "Bitte fahren Sie zu Tor zwei.", "answer_zh": "请开到二号门。"},
                 {"cue": "和原句一样", "answer": "Bitte fahren Sie an Rampe vier.", "answer_zh": "一样"},
                 {"cue": "no chinese", "answer": "Falsch.", "answer_zh": "错"},
                 {"cue": "写成中文的", "answer": "中文答案", "answer_zh": "错"},
                 {"cue": "请同事开到一号月台", "answer": "Bitte fahr an Rampe eins.", "answer_zh": "请开到一号月台。"}]}
s3 = {"de": "Bitte fahren Sie an Rampe vier.", "zh": "请开到四号月台。", "level": "A2"}
cd, e = EX.clean_drills(dr, s3["de"])
assert e is None and [d["answer"] for d in cd] == ["Bitte fahren Sie zu Tor zwei.", "Bitte fahr an Rampe eins."] and cd[1]["hint"] == ""
assert EX.clean_drills({"drills": dr["drills"][:2]}, s3["de"])[1] and EX.clean_drills(None, s3["de"])[1]
EX.call_gemini = real_call
ask3 = "/api/drills?de=" + urllib.parse.quote(s3["de"])
assert J(c.get(ask3)) == {"items": None, "report": None, "can": True, "ai": False}
assert c.post("/api/drills/generate", json=s3).status_code == 503 and cb.post("/api/drills/generate", json=s3).status_code == 403
calls = []
def fake2(prompt):
    calls.append(prompt); return json.dumps(dr)
EX.call_gemini = fake2
di1 = J(c.post("/api/drills/generate", json=s3))["items"]
di2 = J(c.post("/api/drills/generate", json=s3))["items"]
assert di1 == di2 and len(calls) == 1 and s3["de"] in calls[0]
assert di1[0]["drill"] and di1[0]["prompt"] == s3["de"] and di1[0]["prompt_zh"] == "请司机开到二号门" and di1[0]["hint"] == "Tor zwei"
assert J(cb.get(ask3))["items"] == di1                                              # 保存后大家都能看
EX.call_gemini = lambda prompt: "没有 JSON"
s4 = {**s3, "de": "Ich rufe meine Chefin an."}
assert c.post("/api/drills/generate", json=s4).status_code == 502
assert s4["de"] in J(c.post("/api/drills/prompt", json=s4))["prompt"]
assert len(J(c.post("/api/drills/check", json={**s4, "text": json.dumps(dr)}))["items"]) == 3   # 换了原句, 第二题不再和原句相同
assert c.post("/api/drills/check", json={**s4, "text": "abc"}).status_code == 400
assert J(c.post("/api/roleplay/answer", json={"key": di1[0]["key"], "rating": 1}))["interval_days"] == 0
back = J(c.get("/api/roleplay/due"))["items"]
assert [i["key"] for i in back] == [di1[0]["key"]] and back[0]["drill"]
assert J(c.post("/api/roleplay/answer", json={"key": di1[0]["key"], "rating": 3}))["interval_days"] >= 1

# 查词: 原形、复数、变化形式、开头、中文都能查, 最相关的在最前面
dq = lambda client, q: J(client.get("/api/dict?q=" + urllib.parse.quote(q)))["words"]
assert c.get("/api/dict").status_code == 400 and c.get("/api/dict?q=" + "a" * 51).status_code == 400
assert dq(c, "tisch")[0]["german"] == "Tisch" and "form" not in dq(c, "tisch")[0]
assert (lambda w: (w["german"], w["form"]))(dq(c, "Tische")[0]) == ("Tisch", "Tische")     # 复数
assert (lambda w: (w["german"], w["form"]))(dq(c, "Tisches")[0]) == ("Tisch", "Tisches")   # 变格
assert (lambda w: (w["german"], w["form"]))(dq(cb, "gehe")[0]) == ("gehen", "gehe")        # 变位
assert (lambda w: (w["german"], w["form"]))(dq(c, "schnellen")[0]) == ("schnell", "schnellen")   # 形容词词尾
assert dq(c, "Tis")[0]["german"] == "Tisch" and dq(c, "isch")[0]["german"] == "Tisch"      # 开头 / 包含
assert dq(c, "桌子")[0]["german"] == "Tisch" and dq(c, "水")[0]["german"] == "Wasser"       # 中文, 义项完全相同的优先
assert dq(c, "%") == [] and dq(c, "完全没有这个词") == []
assert {"id", "status", "next_review", "edited", "hidden", "private", "level"} <= set(dq(c, "Tisch")[0])
assert not {"stability", "spell_ok", "reps", "rk"} & set(dq(c, "Tisch")[0])
assert dq(cb, "Fenster") == [] or dq(cb, "Fenster")[0]["private"] is False                  # 别人的私有词查不到
hw = J(c.get("/api/words?q=Hund"))["words"][0]["id"]
assert J(c.get(f"/api/words/{hw}"))["queued"] is False
c.post("/api/review/queue", json={"word_id": hw})
assert J(c.get(f"/api/words/{hw}"))["queued"] is True
# 查词也能查到情景课的仓储词; 加进词库后不重复显示
pw = dq(cb, "Palette")[0]
assert (pw["german"], pw["gender"], pw["id"], pw["glossary"], pw["status"]) == ("Palette", "die", None, True, "new")
assert (lambda w: (w["german"], w["form"]))(dq(cb, "Paletten")[0]) == ("Palette", "Paletten")
assert dq(cb, "托盘")[0]["german"] == "Palette" and dq(cb, "Liefers")[0]["german"] == "Lieferschein"
assert [w for w in dq(cb, "送货单") if w["german"] == "Lieferschein"][0]["glossary"]
alice_pal = [w for w in dq(c, "Palette") if w["german"] == "Palette"]
assert len(alice_pal) == 1 and alice_pal[0]["id"] and "glossary" not in alice_pal[0]     # alice 早就加过, 用她的词
assert J(cb.post("/api/review/queue", json={k: pw[k] for k in ("german", "gender", "pos", "plural", "meaning")}))["queued"]
bob_pal = [w for w in dq(cb, "Palette") if w["german"] == "Palette"]
assert len(bob_pal) == 1 and bob_pal[0]["id"]

# AI 查词: 点了才调用, 同样的查询只调用一次; 不是真实的词不保存; 加入复习后不重复显示
import dictionary as DI
dai = lambda client, q: client.post("/api/dict/ai", json={"q": q})
meta = J(c.get("/api/dict?q=Kommissionierer"))
assert meta["words"] == [] and meta["can"] and not meta["ai"] and not J(cb.get("/api/dict?q=x"))["can"]
assert dai(c, "Kommissionierer").status_code == 503 and dai(cb, "Kommissionierer").status_code == 403
assert dai(c, "").status_code == 400 and dai(c, "a" * 51).status_code == 400
kom = {"found": True, "german": "Kommissionierer", "gender": "der", "pos": "名词", "plural": "Kommissionierer",
       "meaning": "拣货员", "example": "Der Kommissionierer holt die Ware.\n拣货员去取货。", "evil": "x"}
calls = []
def fake3(prompt):
    calls.append(prompt); return "```json\n" + json.dumps(kom) + "\n```"
DI.call_gemini = fake3
kw = J(dai(c, "Kommissionierer"))["word"]
assert kw["german"] == "Kommissionierer" and kw["ai_word"] and kw["id"] is None and kw["example"] == kom["example"] and "evil" not in kw
assert J(dai(c, " Kommissionierer"))["word"]["german"] == "Kommissionierer" and len(calls) == 1   # 第二次不再调用
assert "Kommissionierer" in calls[0]
assert dq(cb, "Kommissionierer")[0]["ai_word"]                                       # 保存后大家都能查到
DI.call_gemini = lambda prompt: json.dumps({**kom, "german": "Kommissionierer", "gender": "der"})
assert J(dai(c, "拣货员"))["word"]["german"] == "Kommissionierer"                     # 中文也能查
assert dq(c, "拣货员")[0]["ai_word"]
for bad, status in (("没有 JSON", 502), (json.dumps({**kom, "gender": ""}), 502), (json.dumps({**kom, "meaning": "picker"}), 502),
                    (json.dumps({**kom, "german": "中文"}), 502), (json.dumps({"found": False}), 200)):
    DI.call_gemini = lambda prompt, b=bad: b
    assert dai(c, "Schmarrnwort").status_code == status, bad
assert J(dai(c, "Schmarrnwort"))["word"] is None and dq(c, "Schmarrnwort") == []      # 没有的词不保存
assert DI.clean_ai_word({**kom, "example": "没有德语行"})[0]["example"] == ""
DI.call_gemini = real_call
qk = J(c.post("/api/review/queue", json={k: kw[k] for k in ("german", "gender", "pos", "plural", "meaning", "example")}))["word_id"]
assert J(c.get(f"/api/words/{qk}"))["example"] == kom["example"]
same = [w for w in dq(c, "Kommissionierer") if w["german"] == "Kommissionierer"]
assert len(same) == 1 and same[0]["id"] == qk and "ai_word" not in same[0]
# 单词卡查词带上原句; 自建对话的词表进入查词, 只有自己查得到, 删课后就没有了
calls = []
DI.call_gemini = fake3
assert J(c.post("/api/dict/ai", json={"q": "Rollwagen", "context": "Der Rollwagen steht hier."}))["word"]
assert "Der Rollwagen steht hier." in calls[0] and "这句话" in calls[0]
assert J(c.post("/api/dict/ai", json={"q": "Rolle2"}))["word"] and "这句话" not in calls[1]
DI.call_gemini = real_call
mine = {**good, "glossary": [{"german": "Rollcontainer", "gender": "der", "pos": "名词", "plural": "Rollcontainer", "meaning": "笼车"}]}
ml = J(c.post("/api/custom_lessons", json=mine))["lesson"]
rc = dq(c, "Rollcontainer")[0]
assert rc["glossary"] and rc["id"] is None and dq(c, "笼车")[0]["german"] == "Rollcontainer"
assert dq(cb, "Rollcontainer") == [] and dq(cb, "笼车") == []
c.delete("/api/custom_lessons/" + ml["id"][1:])
assert dq(c, "Rollcontainer") == []

# 报错和重新生成: 问题会告诉 AI; 成功后替换内容并清掉报错; 失败时旧内容不动
rep = lambda client, kind, de, reason: client.post("/api/report", json={"kind": kind, "de": de, "reason": reason})
assert rep(cb, "note", sent["de"], "x").status_code == 400 and rep(cb, "x", sent["de"], "这里错了").status_code == 400
assert rep(cb, "note", "Ohne Inhalt hier.", "这里错了").status_code == 404
assert rep(cb, "note", sent["de"], "应该是第四格").status_code == 200      # 普通用户也能报错
assert J(c.get(ask))["report"] == "应该是第四格"
assert "应该是第四格" in J(c.post("/api/explain/prompt", json=sent))["prompt"]
regen = lambda path, body: c.post(path, json=body)
EX.call_gemini = real_call
assert cb.post("/api/explain/regenerate", json=sent).status_code == 403
assert regen("/api/explain/regenerate", sent).status_code == 503              # 没有 Key
EX.call_gemini = lambda prompt: "坏结果"
assert regen("/api/explain/regenerate", sent).status_code == 502
assert J(c.get(ask))["note"] == cn and J(c.get(ask))["report"] == "应该是第四格"   # 失败时都不变
calls = []
def fake4(prompt):
    calls.append(prompt)
    return json.dumps({**note, "point": "新的讲解"})
EX.call_gemini = fake4
assert J(regen("/api/explain/regenerate", sent))["note"]["point"] == "新的讲解"
assert "应该是第四格" in calls[0] and "必须改正" in calls[0]
assert J(c.get(ask))["note"]["point"] == "新的讲解" and J(c.get(ask))["report"] is None
assert rep(c, "drill", s3["de"], "第二题不自然").status_code == 200
assert J(c.get(ask3))["report"] == "第二题不自然"
EX.call_gemini = lambda prompt: "坏结果"
assert regen("/api/drills/regenerate", s3).status_code == 502
assert J(c.get(ask3))["items"] == di1
calls = []
def fake5(prompt):
    calls.append(prompt)
    return json.dumps({"drills": [dr["drills"][0], {"cue": "请开到五号门", "answer": "Bitte fahren Sie zu Tor fünf.", "answer_zh": "请开到五号门。"}]})
EX.call_gemini = fake5
new_items = J(regen("/api/drills/regenerate", s3))["items"]
assert [i["answer"] for i in new_items] == ["Bitte fahren Sie zu Tor zwei.", "Bitte fahren Sie zu Tor fünf."]
assert "第二题不自然" in calls[0] and J(c.get(ask3))["report"] is None
assert new_items[0]["key"] == di1[0]["key"]                                    # 没变的题复习进度还在
EX.call_gemini = real_call

# 单词书的例句: B2 / C1 也能讲解, 没有中文翻译也可以
assert "水平 C1" in J(c.post("/api/explain/prompt", json={"de": "Das ist ein Satz.", "zh": "", "level": "C1"}))["prompt"]

# 词形练习: 复数、变格、动词变位; 两种写法都算对, 数据有问题的词不出题
import form_drills as FD
assert c.get("/api/forms/plural").status_code == 404 and A.app.test_client().get("/api/forms/cases").status_code == 401
def fr(gender="der", german="Mann", plural="Männer", forms=None):
    return {"id": 1, "german": german, "gender": gender, "plural": plural, "meaning": "男人",
            "forms": json.dumps(forms) if forms else None}
mf = {"cases": {"sg": ["der Mann", "des Mannes / des Manns", "dem Mann", "den Mann"],
                "pl": ["die Männer", "der Männer", "den Männern", "die Männer"]}}
slots = FD.case_slots(fr(forms=mf))
assert len(slots) == 7 and ("单数", 1, ["des Mannes", "des Manns"]) in slots and not [s for s in slots if s[:2] == ("单数", 0)]
assert FD.case_slots(fr(gender="die", forms=mf)) == []                        # 冠词和变格表对不上
assert len(FD.case_slots(fr(forms={"cases": {**mf["cases"], "pl": ["", "", "", ""]}}))) == 3   # 没有复数
for _ in range(30):
    q = FD.case_question(fr(forms=mf))
    assert q["blank"]["answer"] in q["accept"] and q["de"].startswith(q["accept"][0]) and "格" in q["zh"]
fa = fr(gender="", german="fahren", plural="", forms={"praesens": ["fahre", "fährst", "fährt", "fahren", "fahrt", "fahren"]})
assert [i for i, _f in FD.verb_slots(fa)] == [0, 1, 2, 4]                     # wir / sie 和原形相同, 不考
za = fr(gender="", german="zerschmettern", forms={"praesens": ["zerschmetter", "zerschmetterst", "zerschmettert", "zerschmettern", "zerschmettert", "zerschmettern"]})
assert 0 not in [i for i, _f in FD.verb_slots(za)]
se = fr(gender="", german="sein", forms={"praesens": ["bin", "bist", "ist", "sind", "seid", "sind"]})
assert len(FD.verb_slots(se)) == 6
assert FD.verb_slots(fr(gender="", german="x", forms={"praesens": ["a", "", "c", "d", "e", "f"]})) == []
assert cb.post("/api/books/current", json={"book": "all"}).status_code == 200
for kind, n in (("cases", 10), ("verbs", 2)):
    qs = J(cb.get("/api/forms/" + kind))["questions"]
    assert len(qs) == n and len({x["word_id"] for x in qs}) == n, (kind, len(qs))
    assert all(x["blank"]["answer"] and x["accept"] and x["german"] and x["zh"] and x["de"] for x in qs)

# 复数练习: 规律判断、范围、错题本、已掌握
import plural_quiz as PQ
kind = lambda g, a, p: PQ.plural_rule(g, a, p)["kind"]
assert PQ.umlaut("Apfel") == "Äpfel" and PQ.umlaut("Haus") == "Häus" and PQ.umlaut("Tisch") == "Tisch"
for g, a, p in (("Zeitung", "die", "Zeitungen"), ("Lehrerin", "die", "Lehrerinnen"), ("Lampe", "die", "Lampen"),
                ("Regel", "die", "Regeln"), ("Mädchen", "das", "Mädchen"), ("Vater", "der", "Väter"),
                ("Lehrer", "der", "Lehrer"), ("Kollege", "der", "Kollegen"), ("Student", "der", "Studenten"),
                ("Ergebnis", "das", "Ergebnisse"), ("Museum", "das", "Museen"), ("Auto", "das", "Autos"), ("LKW", "der", "LKWs")):
    assert kind(g, a, p) == "rule", g
for g, a, p in (("Mutter", "die", "Mütter"), ("Konto", "das", "Konten"), ("Monitor", "der", "Monitore")):
    assert kind(g, a, p) == "exception", g
for g, a, p in (("Frau", "die", "Frauen"), ("Stadt", "die", "Städte"), ("Stuhl", "der", "Stühle"), ("Jahr", "das", "Jahre"),
                ("Kind", "das", "Kinder"), ("Medizin", "die", "Medizinen")):
    assert kind(g, a, p) == "tendency", g
assert kind("Thema", "das", "Themen") == "none" and kind("Mann", "der", "Männer") == "none"
assert PQ.plural_rule("Baum", "der", "Bäume")["kind"] == "tendency"      # -um 只看中性
assert kind("Tier", "das", "Tiere") == kind("Spiel", "das", "Spiele") == kind("Meer", "das", "Meere") == "tendency"   # 不是弱读词尾
assert kind("Schleier", "der", "Schleier") == "rule" and kind("Bauer", "der", "Bauern") == "exception"
pz = PQ.plural_question({"id": 1, "german": "Mutter", "gender": "die", "plural": "Mütter", "meaning": "母亲"})
assert pz["blank"]["answer"] == "Mütter" and pz["rule_kind"] == "exception" and pz["rule_hint"] == PQ.UNMARKED and "Mütter" in pz["recap"]
assert A.app.test_client().get("/api/plural").status_code == 401 and c.get("/api/plural?scope=x").status_code == 400
pb0 = J(cb.get("/api/plural/books"))
assert pb0["books"][-1]["book"] == "all" and pb0["wrong"] == 0
pq = J(cb.get("/api/plural?scope=all"))["questions"]
assert 0 < len(pq) <= PQ.ROUND_SIZE and len({x["word_id"] for x in pq}) == len(pq)
assert all(x["rule"] and x["rule_hint"] and x["blank"]["answer"] for x in pq)
pw = pq[0]["word_id"]
assert cb.post("/api/plural/result", json={"word_id": pw, "ok": "x"}).status_code == 400
assert cb.post("/api/plural/result", json={"word_id": 99999999, "ok": True}).status_code == 404
assert cb.post("/api/plural/result?tz=0", json={"word_id": pw, "ok": False}).status_code == 200
assert J(cb.get("/api/plural/books"))["wrong"] == 1
assert [x["word_id"] for x in J(cb.get("/api/plural?scope=wrong"))["questions"]] == [pw]
assert J(cb.get("/api/plural?scope=all"))["questions"][0]["word_id"] == pw     # 错过的词排最前
pl = J(cb.get("/api/plural/words?scope=wrong"))
assert pl["total"] == 1 and pl["words"][0]["wrong"] == 1 and pl["words"][0]["plural"] and not pl["words"][0]["manual"]
assert cb.get("/api/plural/words?scope=x").status_code == 400 and cb.get("/api/plural/words?scope=all&page=a").status_code == 400
for _ in range(3):
    assert cb.post("/api/plural/result?tz=0", json={"word_id": pw, "ok": True}).status_code == 200
assert J(cb.get("/api/plural/books"))["wrong"] == 0                            # 连续答对 3 次移出
assert J(cb.get("/api/plural/books"))["books"][-1]["mastered"] == 0            # 同一天只算一次, 不算已掌握
assert db.execute("SELECT 1 FROM noun_practice WHERE word_id = ?", (pw,)).fetchone() is None     # 不影响定冠词记录
assert cb.post("/api/plural/list", json={"text": "   "}).status_code == 400
pname = pq[1]["german"] if len(pq) > 1 else pq[0]["german"]
pa = J(cb.post("/api/plural/list", json={"text": f"{pname}, Gibtsnichtxyz"}))
assert pa["added"] == 1 and pa["missing"] == ["Gibtsnichtxyz"]
assert J(cb.post("/api/plural/list", json={"text": pname}))["skipped"] == 1
pm = J(cb.get("/api/plural/words?scope=wrong"))["words"][0]
assert pm["manual"] and J(cb.get("/api/plural/books"))["wrong"] == 1
assert cb.delete(f"/api/plural/list/{pm['id']}").status_code == 200
assert J(cb.get("/api/plural/books"))["wrong"] == 0

# 语法题库: 初始题启动时导入; 管理员能 AI 出草稿、保存、修改、停用; 系统检查题目格式
import grammar as GR, grammar_seed
assert len(grammar_seed.WAREHOUSE_DEF) == 34
assert A.app.test_client().get("/api/grammar/art-def/quiz").status_code == 401
assert c.get("/api/grammar/x/quiz").status_code == 404 and c.get("/api/grammar/art-def/quiz?n=a").status_code == 400
gq = J(cb.get("/api/grammar/art-def/quiz?n=10"))
assert len(gq["questions"]) == 10 and len({x["id"] for x in gq["questions"]}) == 10
q0 = gq["questions"][0]
assert q0["options"] == ["der", "die", "das", "den", "dem", "des"] and q0["fixed"] and q0["answer"] in q0["options"]
assert q0["source"] == "seed" and q0["prompt"].count("___") == 1 and q0["zh"] and not gq["can"]
assert len(J(c.get("/api/grammar/art-def/quiz?n=999"))["questions"]) == GR.MAX_ROUND
database.init_db()                                                            # 再启动不重复导入
assert db.execute("SELECT COUNT(*) FROM grammar_questions").fetchone()[0] == 34
assert cb.get("/api/grammar/art-def/questions").status_code == 403
topic_def = GR.TOPICS["art-def"]
goodq = {"prompt": "Der Karton steht vor ___ Rampe.", "answer": "der", "hint": "die Rampe · 阴性", "explain": "vor 表示位置 + 第三格", "zh": "纸箱在月台前。", "evil": 1}
assert GR.clean_question(goodq, topic_def)[1] is None and "evil" not in GR.clean_question(goodq, topic_def)[0]
for bad, msg in (({**goodq, "prompt": "Kein Platzhalter."}, "___"), ({**goodq, "prompt": "___ und ___."}, "___"), ({**goodq, "prompt": "这是 ___ 中文。"}, "德语"),
                 ({**goodq, "answer": "einer"}, "答案"), ({**goodq, "zh": "no"}, "中文"), ({**goodq, "explain": ""}, "中文")):
    assert msg in GR.clean_question(bad, topic_def)[1], bad
assert len(GR.clean_questions({"questions": [goodq, {"prompt": "x"}]}, topic_def)[0]) == 1 and GR.clean_questions({"questions": [{}]}, topic_def)[1]
gen = {"request": "第三格 司机", "n": 5}
assert c.post("/api/grammar/art-def/generate", json={"request": "x"}).status_code == 400
assert c.post("/api/grammar/art-def/generate", json={**gen, "n": 11}).status_code == 400
assert c.post("/api/grammar/art-def/generate", json=gen).status_code == 503 and cb.post("/api/grammar/art-def/generate", json=gen).status_code == 403
calls = []
def fake6(prompt):
    calls.append(prompt); return json.dumps({"questions": [goodq]})
GR.call_gemini = fake6
draft = J(c.post("/api/grammar/art-def/generate", json=gen))["questions"]
assert draft[0]["source"] == "ai" and "第三格 司机" in calls[0] and "Hubwagen" in calls[0]
assert db.execute("SELECT COUNT(*) FROM grammar_questions").fetchone()[0] == 34       # 草稿不保存
GR.call_gemini = lambda prompt: "没有 JSON"
assert c.post("/api/grammar/art-def/generate", json=gen).status_code == 502
GR.call_gemini = real_call
assert "第三格 司机" in J(c.post("/api/grammar/art-def/prompt", json=gen))["prompt"]
assert len(J(c.post("/api/grammar/art-def/check", json={"text": json.dumps({"questions": [goodq]})}))["questions"]) == 1
assert c.post("/api/grammar/art-def/check", json={"text": "abc"}).status_code == 400
assert cb.post("/api/grammar/art-def/questions", json={"questions": draft}).status_code == 403
assert c.post("/api/grammar/art-def/questions", json={"questions": [{**draft[0], "answer": "x"}]}).status_code == 400
gs1 = J(c.post("/api/grammar/art-def/questions", json={"questions": draft}))
assert gs1["saved"] == 1 and gs1["skipped"] == 0 and gs1["missing"]                                            # 不在海外仓词汇里要提示
gs2 = J(c.post("/api/grammar/art-def/questions", json={"questions": draft}))
assert gs2["saved"] == 0 and gs2["skipped"] == 1                                                               # 重复的跳过
mine_q = [x for x in J(c.get("/api/grammar/art-def/questions"))["questions"] if x["source"] == "ai"][0]
assert cb.post(f"/api/grammar/questions/{mine_q['id']}/report", json={"reason": "x"}).status_code == 400
assert cb.post(f"/api/grammar/questions/{mine_q['id']}/report", json={"reason": "答案不对"}).status_code == 200
assert J(c.get("/api/grammar/art-def/questions"))["questions"][0]["report"] == "答案不对"     # 有报错的排最前
edited = {**mine_q, "answer": "dem", "prompt": "Der Karton steht vor ___ Tor.", "hint": "das Tor · 中性", "explain": "vor 表示位置 + 第三格；中性 → dem", "zh": "纸箱在门前。"}
assert J(c.post("/api/grammar/art-def/questions", json={"questions": [edited]}))["saved"] == 1
after = [x for x in J(c.get("/api/grammar/art-def/questions"))["questions"] if x["id"] == mine_q["id"]][0]
assert after["answer"] == "dem" and after["report"] is None and after["source"] == "ai"
assert c.post(f"/api/grammar/questions/{mine_q['id']}/status", json={"status": "x"}).status_code == 400
assert cb.post(f"/api/grammar/questions/{mine_q['id']}/status", json={"status": "hidden"}).status_code == 403
assert c.post(f"/api/grammar/questions/{mine_q['id']}/status", json={"status": "hidden"}).status_code == 200
assert mine_q["id"] not in [x["id"] for x in J(c.get("/api/grammar/art-def/quiz?n=30"))["questions"]]
assert c.post("/api/grammar/questions/99999/status", json={"status": "active"}).status_code == 404

# 词性解释: 词尾、复合词、动词名词、时间词; 对不上就说没有规律, 不编原因
gr = lambda german, gender: J(c.get(f"/api/gender_reason?german={urllib.parse.quote(german)}&gender={gender}"))["reason"]
assert A.app.test_client().get("/api/gender_reason?german=Tisch&gender=der").status_code == 401
assert c.get("/api/gender_reason?german=Tisch&gender=x").status_code == 400 and c.get("/api/gender_reason?gender=der").status_code == 400
assert "-ung" in gr("Zeitung", "die") and "-chen" in gr("Mädchen", "das") and "-ling" in gr("Lehrling", "der")
assert gr("Sprung", "der") == "这个词没有明显规律，要和冠词一起记"                # der Sprung 不是 -ung 规律
assert gr("Tisch", "der") == "这个词没有明显规律，要和冠词一起记"
assert gr("Haustisch", "der") == "复合词，词性看最后一个词：der Tisch"
assert gr("Kinderbuch", "das") == "复合词，词性看最后一个词：das Buch"           # 前半段是复数也算
assert gr("Arbeitstisch", "der") == "复合词，词性看最后一个词：der Tisch"        # 连接成分 -s
assert gr("Lernbuch", "das") == "复合词，词性看最后一个词：das Buch"             # 动词词干
assert gr("Hausbuch", "der") == "这个词没有明显规律，要和冠词一起记"             # 冠词对不上
assert gr("Xyzbuch", "das") == "这个词没有明显规律，要和冠词一起记"              # 前半段不是真词
assert "动词" in gr("Gehen", "das") and "星期" in gr("Montag", "der") and "-e" in gr("Lampe", "die")
assert gr("die Lieferung", "die").startswith("以 -ung")                           # 带冠词也能查
# 第一层补充: 新词尾、动词加 -er、情景课词表; 同类词能点
import gender_hint as GH
rw = lambda german, gender, client=c: J(client.get(f"/api/gender_reason?german={urllib.parse.quote(german)}&gender={gender}"))
assert "-ei" in gr("Bäckerei", "die") and "-ik" in gr("Musik", "die") and "-um" in gr("Zentrum", "das") and "-ie" in gr("Familie", "die")
assert "-er" in gr("Lerner", "der") and gr("Raum", "der") == GH.NO_RULE
# 动词加 -er 的同类词: Vater 只是碰巧以 -er 结尾, 不算
wdb = sqlite3.connect(os.environ["DB_PATH"]); wdb.executemany("INSERT INTO words (german, pos, gender, plural, meaning) VALUES (?,?,?,?,?)",
    [("Vater", "名词", "der", "", "父亲"), ("Geher", "名词", "der", "", "步行者")]); wdb.commit(); wdb.close()
with A.app.test_request_context():
    assert [e["german"] for e in GH.examples_of("Lerner", "der", "er", None)] == ["Geher"]
assert gr("Staplerschein", "der") == "这个词没有明显规律，要和冠词一起记" or "Schein" in gr("Staplerschein", "der")
assert gr("Staplerpalette", "die") == "复合词，词性看最后一个词：die Palette"       # 前后都只在情景课词表里
assert rw("Hausapfel", "der")["examples"][0] == {"german": "Apfel", "gender": "der", "meaning": "苹果"}   # 最后一个词排最前
assert [e["german"] for e in rw("Lampe", "die")["examples"]] != [] and all(e["german"] != "Lampe" for e in rw("Lampe", "die")["examples"])
assert rw("Hund", "der")["no_rule"] and rw("Hund", "der")["examples"] == [] and rw("Hund", "der")["can"]
assert not rw("Hund", "der", cb)["can"] and "memo" not in rw("Zeitung", "die")
# 第二层: 没有规律的词才生成, 点了才调用, 保存后不重复, 可以换一个
mm = lambda client, **b: client.post("/api/gender_memo", json={"german": "Hund", "gender": "der", "meaning": "狗", **b})
assert mm(c).status_code == 503 and mm(cb).status_code == 403
assert mm(c, gender="x").status_code == 400 and mm(c, german="Zeitung", gender="die").status_code == 400
calls = []
def fake7(prompt):
    calls.append(prompt); return json.dumps({"memo": "蓝色的 der 狗看守仓库"})
GH.call_gemini = fake7
assert J(mm(c))["memo"] == "蓝色的 der 狗看守仓库" and J(mm(c))["memo"] == "蓝色的 der 狗看守仓库" and len(calls) == 1
assert "der Hund" in calls[0] and "狗" in calls[0] and "蓝色" in calls[0]
assert rw("Hund", "der", cb)["memo"] == "蓝色的 der 狗看守仓库"                     # 保存后大家都能看
GH.call_gemini = lambda prompt: json.dumps({"memo": "新的联想：der 狗"})
assert J(mm(c, again=True))["memo"] == "新的联想：der 狗" and rw("Hund", "der")["memo"] == "新的联想：der 狗"
GH.call_gemini = lambda prompt: json.dumps({"memo": "no"})
assert mm(c, again=True).status_code == 502 and rw("Hund", "der")["memo"] == "新的联想：der 狗"   # 失败时旧的不动
GH.call_gemini = real_call

# 构词解释: 点了才调用, 保存后不重复, 拼不回原词的不保存, 失败时旧内容不动
import word_parts as WP
pp = lambda client, **b: client.post("/api/parts/generate", json={"german": "Krankenhaus", "meaning": "医院", **b})
pg = lambda german, client=c: J(client.get("/api/parts?german=" + urllib.parse.quote(german)))
wp_ok = {"split": True, "literal": "病人的房子 → 医院", "clarity": "clear", "steps": [
    {"word": "Krankenhaus", "parts": [
        {"text": "Kranken", "base": "krank", "zh": "生病的", "type": "word"},
        {"text": "Haus", "base": "Haus", "zh": "房子", "type": "word"}]},
    {"word": "Kranken", "parts": [{"text": "krank", "base": "krank", "zh": "生病的", "type": "word"},
                                  {"text": "en", "base": "en", "zh": "", "type": "link"}]},
    {"word": "Tisch", "parts": [{"text": "Ti", "base": "Ti", "zh": "无关", "type": "word"},
                                {"text": "sch", "base": "sch", "zh": "无关", "type": "word"}]}]}
assert pg("Krankenhaus") == {"parts": None, "report": None, "can": True, "ai": False}
assert pp(c).status_code == 503 and pp(cb).status_code == 403
calls = []
def fake8(prompt):
    calls.append(prompt); return json.dumps(wp_ok)
WP.call_gemini = fake8
saved = J(pp(c))["parts"]
assert len(saved["steps"]) == 2 and saved["steps"][1]["parts"][1]["zh"] == "连接成分"        # 无关的一层去掉
assert J(pp(c))["parts"] == saved and len(calls) == 1 and "Krankenhaus" in calls[0] and "医院" in calls[0]
assert pg("Krankenhaus", cb)["parts"] == saved and not pg("Krankenhaus", cb)["can"]            # 保存后大家都能看
assert pg("das Krankenhaus")["parts"] == saved                                                 # 带冠词也能查
assert cb.post("/api/parts/report", json={"german": "Krankenhaus", "reason": "x"}).status_code == 400
assert cb.post("/api/parts/report", json={"german": "Haus", "reason": "没有解释"}).status_code == 404
assert cb.post("/api/parts/report", json={"german": "Krankenhaus", "reason": "意思不对"}).status_code == 200
assert pg("Krankenhaus")["report"] == "意思不对"
WP.call_gemini = lambda prompt: json.dumps({**wp_ok, "steps": [{"word": "Krankenhaus", "parts": [
    {"text": "Krank", "base": "krank", "zh": "生病的", "type": "word"}, {"text": "Haus", "base": "Haus", "zh": "房子", "type": "word"}]}]})
assert pp(c, again=True).status_code == 502 and pg("Krankenhaus")["parts"] == saved            # 拼不回原词
assert pg("Krankenhaus")["report"] == "意思不对"                                               # 失败时报错还在
WP.call_gemini = fake8
assert pp(c, again=True).status_code == 200 and "意思不对" in calls[-1] and pg("Krankenhaus")["report"] is None
WP.call_gemini = lambda prompt: json.dumps({"split": False})
assert J(pp(c, german="Haus"))["parts"] == {"split": False}
WP.call_gemini = lambda prompt: 1 / 0                                                          # 已保存, 不再调用
assert J(pp(c, german="Haus"))["parts"] == {"split": False}
WP.call_gemini = lambda prompt: json.dumps({**wp_ok, "clarity": "x"})
assert pp(c, german="Krankenhaus", again=True).status_code == 502
assert WP.clean_parts(wp_ok, "Größe")[1] and WP.normalize("sich freuen") == "freuen"
assert WP.clean_parts({"split": True, "steps": [{"word": "Fußball", "parts": [
    {"text": "FUSS", "base": "Fuß", "zh": "脚", "type": "word"}, {"text": "ball", "base": "Ball", "zh": "球", "type": "word"}]}],
    "literal": "脚的球", "clarity": "clear"}, "Fußball")[1] is None                            # ß 和 ss 算一样
WP.call_gemini = real_call

# 定冠词自动出题: 优先用例句, 没有例句用通用句型; 答案来自变格表
import noun_quiz as NQ
nf = {"cases": {"sg": ["der Mann", "des Mannes / des Manns", "dem Mann", "den Mann"],
                "pl": ["die Männer", "der Männer", "den Männern", "die Männer"]}}
def nr(forms=nf, example="", gender="der", german="Mann", details=None):
    return {"id": 7, "german": german, "gender": gender, "meaning": "男人", "example": example,
            "forms": json.dumps(forms) if forms else None, "details": json.dumps(details) if details else None}
assert NQ.split_form("des Mannes / des Manns") == ("des", "Mannes") and NQ.split_form("kein Mann") is None
assert len(NQ.table(nr())) == 8 and NQ.table(nr(gender="die")) == []
assert NQ.table(nr(forms=None)) == [("单数", 0, "der", "Mann")]                  # 没有变格表只考第一格
eq = NQ.make_question(nr(example="Ich sehe den Mann im Lager.\n我在仓库里看见那个男人。"))
assert eq["prompt"] == "Ich sehe ___ Mann im Lager." and eq["answer"] == "den" and eq["source"] == "example"
assert eq["must"] == "单数" and "第四格" in eq["explain"] and eq["zh"] == "我在仓库里看见那个男人。"
sq = NQ.make_question(nr(example="Der Mann ist hier.\n那个男人在这里。"))
assert sq["prompt"] == "___ Mann ist hier." and sq["answer"] == "der" and sq["fill"] == "Der"       # 句首大写
pq = NQ.make_question(nr(example="Ich sehe die Männer.\n我看见那些男人。"))
assert pq["must"] == "复数" and "第一格或第四格" in pq["explain"]
assert NQ.make_question(nr(example="Der Mann sieht den Mann.\n两个男人。"))["source"] in ("example", "template")
same = {"cases": {"sg": ["der Scanner", "des Scanners", "dem Scanner", "den Scanner"], "pl": ["die Scanner", "der Scanner", "den Scannern", "die Scanner"]}}
assert NQ.example_question(nr(forms=same, german="Scanner", example="Ich sehe den Scanner.\n我看见扫描枪。"), NQ.table(nr(forms=same, german="Scanner"))) is None
assert NQ.make_question(nr(example="Der Mann ist hier."))["source"] == "template"                    # 没有中文
for _ in range(60):
    tq = NQ.template_question(nr(), NQ.table(nr()))
    assert tq["prompt"].count("___") == 1 and tq["answer"] in NQ.OPTIONS and tq["must"] in ("单数", "复数") and "男人" in tq["zh"] and tq["zh"].endswith("。")
assert NQ.make_question(nr(forms=None, german="Zwei Worte")) is None
assert c.get("/api/grammar/nouns?scope=x").status_code == 400 and c.get("/api/grammar/nouns?n=x").status_code == 400
assert A.app.test_client().get("/api/grammar/nouns").status_code == 401
na = J(cb.get("/api/grammar/nouns?scope=all&n=10"))["questions"]
assert len(na) == 10 and len({x["word_id"] for x in na}) == 10 and all(x["answer"] in x["options"] and x["fixed"] and x["must"] for x in na)
assert c.get("/api/grammar/nouns?scope=learned").status_code == 400 and c.get("/api/grammar/nouns?scope=mine").status_code == 400
assert J(c.get("/api/grammar/nouns?n=5"))["questions"] is not None                                  # 默认当前单词书
nid = [x["word_id"] for x in na if not any(w in x["hint"] for w in ("Hund", "Lampe", "Tisch", "Katze"))][0]    # 这几个词后面有专门的测试
nrep = lambda client, **b: client.post("/api/grammar/nouns/report", json={"word_id": nid, "prompt": "p ___", "reason": "这题不对", **b})
assert nrep(cb, reason="x").status_code == 400 and nrep(cb, word_id="1").status_code == 400 and nrep(cb, word_id=999999).status_code == 404
assert nrep(cb).status_code == 200 and cb.get("/api/grammar/nouns/reports").status_code == 403
assert J(c.get("/api/grammar/nouns/reports"))["reports"][0]["id"] == nid
assert c.delete(f"/api/grammar/nouns/reports/{nid}").status_code == 200 and J(c.get("/api/grammar/nouns/reports"))["reports"] == []

# 词性错还是格错: 选了别的词性在这个格的冠词 = 词性错; 复数不分词性; 不知道第几格时都算词性错
assert NQ.gender_picks("der", "单数", [3]) == ["das", "die"] and NQ.gender_picks("die", "单数", [2]) == ["dem"]
assert NQ.gender_picks("die", "单数", [0, 3]) == ["das", "den", "der"]
assert NQ.gender_picks("der", "复数", [3]) == [] and NQ.gender_picks("der", "单数", None) == NQ.OPTIONS
assert NQ.memory_rating(True, "单数", False, None) == 3 and NQ.memory_rating(False, "单数", False, "gender") == 1
assert NQ.memory_rating(False, "单数", False, None) == 1 and NQ.memory_rating(False, "单数", False, "case") is None
assert NQ.memory_rating(True, "复数", False, None) is None and NQ.memory_rating(False, "复数", False, "gender") is None
assert NQ.memory_rating(True, "单数", True, None) is None and NQ.memory_rating(False, "单数", True, "gender") is None
# 要考词性时只出单数; 只有复数形式的词也能出题
for _ in range(30):
    assert NQ.make_question(nr(example="Ich sehe die Männer.\n我看见那些男人。"), None, True)["must"] == "单数"
only_pl = {"cases": {"sg": ["", "", "", ""], "pl": ["die Leute", "der Leute", "den Leuten", "die Leute"]}}
assert NQ.make_question(nr(forms=only_pl, gender="die", german="Leute"), None, True) is None    # 第一格和词性对不上的不出
# 一组的配额: 到期最多 n - 4 个, 新词补上; 新词不够时用到期的补, 再用未到期的
ids = lambda qs: sorted(x["word_id"] for x in qs)
fake = lambda *xs: [{"word_id": x} for x in xs]
assert ids(NQ.pick_round(fake(*range(20)), fake(*range(100, 120)), [], 14)) == list(range(10)) + list(range(100, 104))
assert ids(NQ.pick_round(fake(1, 2), fake(*range(100, 120)), [], 14)) == [1, 2] + list(range(100, 112))
assert ids(NQ.pick_round(fake(*range(20)), fake(100), [], 14)) == list(range(13)) + [100]
assert ids(NQ.pick_round(fake(1), fake(100), fake(200, 201), 3)) == [1, 100, 200] and len(NQ.pick_round(fake(1, 2), [], [], 1)) == 1

# 练习记录: 词性答错进错题本, 稳定性到 7 天才移出; 按用户分开
nq = lambda client, scope, n=30: J(client.get(f"/api/grammar/nouns?scope={scope}&n={n}"))["questions"]
assert nq(cb, "wrong") == []
res = lambda client, wid, ok, **b: client.post("/api/grammar/nouns/result", json={"word_id": wid, "ok": ok, **b})
def days_ago(wid, n=1):    # 假装上次作答是 n 天前, 现在到期了
    wd = sqlite3.connect(os.environ["DB_PATH"])
    wd.execute("UPDATE noun_practice SET last_review = datetime(last_review, ?), next_review = datetime(next_review, ?) WHERE word_id = ?",
               (f"-{n} days", f"-{n + 40} days", wid))
    wd.commit(); wd.close()
npr = lambda wid, user=None: db.execute("SELECT stability, next_review, weak, wrong, streak FROM noun_practice WHERE word_id = ?"
                                        + (" AND user_id = ?" if user else ""), (wid, user) if user else (wid,)).fetchone()
assert res(cb, nid, "x").status_code == 400 and res(cb, "1", True).status_code == 400 and res(cb, 999999, True).status_code == 404
assert res(cb, nid, False, kind="gender").status_code == 200
assert [x["word_id"] for x in nq(cb, "wrong")] == [nid] and nq(c, "wrong") == []
assert npr(nid)[2] == 1 and npr(nid)[1] > database.now_str()                    # 答错: 最早明天再出
assert nid not in [x["word_id"] for x in nq(cb, "all", 5)]                      # 今天不再出, 新词够用时不拿它补
res(cb, nid, True); res(cb, nid, True); res(cb, nid, True)
assert [x["word_id"] for x in nq(cb, "wrong")] == [nid]                         # 同一天答对多少次都不算数
s0 = npr(nid)[0]
days_ago(nid)
assert nid in [x["word_id"] for x in nq(cb, "all", 14)]                         # 到期了优先出
for i in range(6):
    if not npr(nid)[2]: break
    res(cb, nid, True); days_ago(nid, 5)
assert npr(nid)[0] >= 7 > s0 and npr(nid)[2] == 0 and nq(cb, "wrong") == []     # 隔天答对, 稳定性上来才移出
ps = db.execute("SELECT seen, wrong FROM noun_practice WHERE word_id = ?", (nid,)).fetchone()
assert ps[1] == 1 and ps[0] >= 5, ps
# 格错、复数题、开提示: 不改记忆状态, 不进错题本, 今天别再出
cw = db.execute("SELECT id FROM words WHERE german = 'Hund'").fetchone()[0]
for b in ({"ok": False, "kind": "case", "case": 3, "must": "单数"}, {"ok": True, "must": "复数"}, {"ok": False, "must": "复数", "kind": "gender"},
          {"ok": True, "hinted": True, "must": "单数"}):
    res(cb, cw, b.pop("ok"), **b)
ca = npr(cw)
assert ca[0] is None and ca[2] == 0 and ca[3] == 0 and ca[1] > database.now_str(), ca
assert db.execute("SELECT kind FROM noun_answers WHERE word_id = ? ORDER BY id", (cw,)).fetchall()[0] == ("case",)
# 老记录: 没有记忆状态算到期, 优先出; 第一次作答时开始算
wd = sqlite3.connect(os.environ["DB_PATH"])
wd.execute("UPDATE noun_practice SET next_review = NULL WHERE word_id = ?", (cw,)); wd.commit(); wd.close()
assert cw in [x["word_id"] for x in nq(cb, "all", 14)]
res(cb, cw, True, must="单数")
assert npr(cw)[0] > 3 and npr(cw)[2] == 0

# 错题本: 手动加的词(粘贴多个词、变化形式、情景课的词); 只出本子里的词; 按用户分开
ladd = lambda client, **b: client.post("/api/grammar/nouns/list", json=b)
wrongs = lambda client: J(client.get("/api/grammar/nouns/words?scope=wrong"))
assert ladd(cb).status_code == 400 and ladd(cb, text=" ").status_code == 400
rl = J(ladd(cb, text="Tisch, Katzen，der Hund Nichtda gehen"))
assert rl["added"] == 3 and rl["missing"] == ["Nichtda", "gehen"], rl
assert J(ladd(cb, text="Tisch"))  == {"added": 0, "skipped": 1, "missing": []}
assert {x["german"] for x in wrongs(cb)["words"]} == {"Tisch", "Katze", "Hund"} and all(x["manual"] for x in wrongs(cb)["words"])
assert wrongs(c)["words"] == [] and wrongs(c)["total"] == 0
assert {x["word_id"] for x in nq(cb, "wrong")} == {x["id"] for x in wrongs(cb)["words"]}
gl_add = J(ladd(cb, text="Gabelstapler"))                                        # 只在情景课词表里: 加成私有词
assert gl_add["added"] == 1 and db.execute("SELECT 1 FROM words WHERE german = 'Gabelstapler' AND status = 'pending'").fetchone()
fork = [x for x in nq(cb, "wrong") if "Gabelstapler" in x["hint"]][0]
assert fork["prompt"] == "Das ist ___ Gabelstapler." and fork["answer"] == "der"  # 没有变格表, 只考第一格
ltid = wrongs(cb)["words"][0]["id"]
assert ladd(cb, word_id="1").status_code == 400 and ladd(cb, word_id=999999).status_code == 404
gehen_id = db.execute("SELECT id FROM words WHERE german = 'gehen'").fetchone()[0]
assert ladd(cb, word_id=gehen_id).status_code == 400                              # 不是名词
assert cb.delete(f"/api/grammar/nouns/list/{ltid}").status_code == 200
assert ltid not in [x["id"] for x in wrongs(cb)["words"]]
# 错过的词也能手动移除, 练过几次还留着
res(cb, nid, False)
assert [x for x in wrongs(cb)["words"] if x["id"] == nid][0]["wrong"] >= 1
assert cb.delete(f"/api/grammar/nouns/list/{nid}").status_code == 200 and nid not in [x["id"] for x in wrongs(cb)["words"]]
assert db.execute("SELECT seen, wrong FROM noun_practice WHERE word_id = ?", (nid,)).fetchone() == (ps[0] + 1, 0)

# 已掌握: 稳定性到 21 天; 答错就退回。每次作答记下单复数和第几格
mw = db.execute("SELECT id FROM words WHERE german = 'Lampe'").fetchone()[0]
masters = lambda: J(c.get("/api/grammar/nouns/books"))["books"][-1]["mastered"]
m0 = masters()
res(c, mw, True); s1 = npr(mw)[0]; assert masters() == m0                         # 第一次答对约 3 天
for gap in (3, 11):
    days_ago(mw, gap); res(c, mw, True)
assert npr(mw)[0] >= 21 > s1 and masters() == m0 + 1, npr(mw)
days_ago(mw, 30); res(c, mw, False, kind="gender"); assert masters() == m0 and npr(mw)[2] == 1   # 答错退回, 进错题本
ra = c.post("/api/grammar/nouns/result", json={"word_id": mw, "ok": True, "must": "复数", "case": 2})
rb = c.post("/api/grammar/nouns/result", json={"word_id": mw, "ok": False, "must": "x", "case": 9})
assert ra.status_code == 200 and rb.status_code == 200
assert db.execute("SELECT number, case_no, ok FROM noun_answers ORDER BY id DESC LIMIT 2").fetchall() == [(None, None, 0), ("复数", 2, 1)]
# 题目带第几格: 例句能确定的、通用句型; 手写题从解释里读; 同形时不确定
assert NQ.template_question(nr(), NQ.table(nr()))["case"] in (0, 1, 2, 3)
assert NQ.make_question(nr(example="Ich gebe dem Mann Tee.\n我给那个男人茶。"))["case"] == 2
assert NQ.make_question(nr(example="Ich sehe die Männer.\n我看见那些男人。"))["case"] is None      # 第一或第四格
assert NQ.written_case("in 表示位置 + 第三格；阴性第三格 → der") == 2 and NQ.written_case("复数 → die") is None
# 练习范围: 只列有名词的书和错题本; 查看单词分页; 选书不改变首页的当前单词书
nb = J(cb.get("/api/grammar/nouns/books"))
all_nouns = db.execute("SELECT COUNT(*) FROM words WHERE gender != '' AND status = 'public'").fetchone()[0]
assert nb["books"][-1]["book"] == "all" and nb["books"][-1]["practiced"] >= 1 and nb["books"][-1]["weak"] == nb["wrong"]
assert nb["books"][-1]["nouns"] >= all_nouns and nb["wrong"] == wrongs(cb)["total"]
assert cb.get("/api/grammar/nouns/words?scope=x").status_code == 400 and cb.get("/api/grammar/nouns/words?scope=all&page=x").status_code == 400
wa = J(cb.get("/api/grammar/nouns/words?scope=all&page=1"))
assert wa["total"] == nb["books"][-1]["nouns"] and wa["pages"] >= 1 and all(x["gender"] for x in wa["words"])
assert J(cb.get("/api/grammar/nouns/words?scope=all&page=99"))["words"] == []

# 手写句子优先于例句和句型; 同一本书的词才出; 报错记到手写题, 作答记到词
Tid = db.execute("SELECT id FROM words WHERE german = 'Tisch'").fetchone()[0]
wdb = sqlite3.connect(os.environ["DB_PATH"])
wdb.execute("INSERT INTO word_books (book, word_id, rank) VALUES ('warehouse', ?, 1)", (Tid,))
wdb.execute("INSERT INTO grammar_questions (topic, prompt, answer, hint, explain, zh, source, created_at) VALUES "
            "('art-def', '___ Tisch steht hier.', 'der', 'der Tisch · 这里是第一格', '主语 → 第一格', '桌子在这里。', 'seed', 'x'), "
            "('art-def', '___ Tische stehen hier.', 'die', 'der Tisch · 这里是复数', '复数 → die', '桌子在这里。', 'seed', 'x')")
wdb.commit(); wdb.close()
wq = nq(cb, "warehouse")                                                          # 新词要考词性, 不出复数的手写题
assert len(wq) == 1 and wq[0]["prompt"] == "___ Tisch steht hier." and wq[0]["word_id"] == Tid and wq[0]["id"]
assert wq[0]["fill"] == "Der" and wq[0]["must"] == "单数" and wq[0]["source"] == "seed" and wq[0]["zh"] == "桌子在这里。"
assert wq[0]["case"] == 0 and wq[0]["gender_picks"] == ["das", "die"]
res(cb, Tid, False)                                                               # 练错一次: 已练 1, 待巩固 1
assert J(cb.get("/api/grammar/nouns/books"))["books"][-2:][0] == {"book": "warehouse", "nouns": 1, "practiced": 1, "weak": 1, "mastered": 0}
assert [x["id"] for x in J(cb.get("/api/grammar/nouns/words?scope=warehouse"))["words"]] == [Tid]
assert J(c.get("/api/books"))["themes"][-1]["level"] == "warehouse"

# 不定冠词、否定冠词、物主冠词: 按格子练, 词性答错才算进词性记忆
import article_quiz as AQ
assert [AQ.form("euer", "die", 0), AQ.form("euer", "der", 0), AQ.form("unser", "der", 3)] == ["eure", "euer", "unseren"]
assert [AQ.form("ein", "das", 3), AQ.form("kein", "pl", 2), AQ.form("Ihr", "die", 2), AQ.form("ein", "der", 1)] == ["ein", "keinen", "Ihrer", "eines"]
assert AQ.gender_picks("ein", "der", 0) == ["eine"] and AQ.gender_picks("ein", "der", 3) == ["ein", "eine"]   # 第一格 ein 阳性中性都对
assert AQ.gender_picks("kein", "die", 2) == ["keinem"]
assert len(AQ.all_cells("indef")) == 12 and len(AQ.all_cells("kein")) == 12 and len(AQ.all_cells("poss")) == 16
assert not [x for x in AQ.all_cells("indef") if ":pl:" in x] and not [x for x in AQ.all_cells("kein") if x.endswith(":1")]
w1 = AQ.weights_from([("a", 0), ("a", 0), ("b", 1)], ["a", "b", "c"])
assert w1 == {"a": 4, "b": 1, "c": AQ.UNSEEN_WEIGHT}
assert AQ.weights_from([("a", 1)] * 10 + [("a", 0)] * 5, ["a"])["a"] == 1          # 只看最近 10 次
same = {x: 1 for x in "abcde"}
assert len(AQ.deal_cells(list("ab"), {"a": 1, "b": 1}, 5)) == 5 and set(AQ.deal_cells(list("ab"), {"a": 1, "b": 1}, 5)) == {"a", "b"}
assert len(set(AQ.deal_cells(list("abcde"), same, 3))) == 3
nowasser = {"cases": {"sg": ["das Wasser", "des Wassers", "dem Wasser", "das Wasser"], "pl": ["", "", "", ""]}}
assert AQ.noun_table("indef", nr(forms=nowasser, gender="das", german="Wasser")) == {} and AQ.noun_table("kein", nr(forms=nowasser, gender="das", german="Wasser"))
mq = AQ.make_question(nr(), "indef:der:3", "Mann")
assert mq["prompt"] == "Wir suchen ___ Mann." and mq["answer"] == "einen" and mq["must"] == "单数" and mq["case"] == 3
assert mq["gender_picks"] == ["ein", "eine"] and mq["cell_name"] == "第四格阳性" and "男人" in mq["zh"] and "einen" in mq["options"]
pq2 = AQ.make_question(nr(), "kein:pl:2", "Männern")
assert pq2["prompt"] == "Das hat mit ___ Männern zu tun." and pq2["answer"] == "keinen" and pq2["gender_picks"] == [] and pq2["must"] == "复数"
for _ in range(30):
    oq = AQ.make_question(nr(), "poss:die:3", "Frau")
    assert oq["answer"] in oq["options"] and len(oq["options"]) == 6 and "的" in oq["zh"]
assert c.get("/api/grammar/articles?type=x").status_code == 400 and c.get("/api/grammar/articles?type=kein&scope=x").status_code == 400
assert c.get("/api/grammar/articles?type=kein&n=x").status_code == 400 and A.app.test_client().get("/api/grammar/articles?type=kein").status_code == 401
for kind in ("indef", "kein", "poss"):
    aq = J(cb.get(f"/api/grammar/articles?type={kind}&scope=all&n=8"))["questions"]
    assert 0 < len(aq) <= 8 and len({x["word_id"] for x in aq}) == len(aq), aq
    assert all(x["article"] == kind and x["answer"] in x["options"] and x["prompt"].count("___") == 1 and x["cell"].startswith(kind) for x in aq)
    assert all(x["answer"].startswith(x["answer_lemma"][:2]) and x["answer_lemma"] in x["answer_note"] for x in aq), aq
assert AQ.answer_note("poss", "sein", "他的", "en") == "物主冠词：他的（sein + 词尾 -en）"
assert AQ.answer_note("poss", "euer", "你们的", "em") == "物主冠词：你们的（euer + 词尾 -em，去掉中间的 e）"
assert AQ.answer_note("indef", "ein", "", "") == "不定冠词：ein，没有词尾"
assert J(cb.get("/api/grammar/articles?type=kein&scope=warehouse"))["questions"][0]["word_id"] == Tid
pcount = lambda: db.execute("SELECT COUNT(*) FROM noun_practice").fetchone()[0]
acell = lambda: db.execute("SELECT cell, kind FROM noun_answers ORDER BY id DESC LIMIT 1").fetchone()
ppc = pcount()
fresh = db.execute("SELECT id FROM words WHERE gender != '' AND status = 'public' AND id NOT IN (SELECT word_id FROM noun_practice) LIMIT 1").fetchone()[0]
assert res(cb, fresh, True, must="单数", cell="indef:der:3").status_code == 200 and pcount() == ppc and acell() == ("indef:der:3", None)   # 答对不算练过
res(cb, fresh, False, must="单数", kind="case", cell="indef:der:3")
assert pcount() == ppc and acell() == ("indef:der:3", "case")
res(cb, fresh, False, must="单数", kind="gender", cell="bad:cell")
assert pcount() == ppc + 1 and acell() == (None, "gender")

# 动词练习: 用 FSRS 选词, 只有词形错才算忘了, 人称错不改记忆状态
import verb_quiz as vq
from verb_sentences import WRITTEN
vdb = sqlite3.connect(os.environ["DB_PATH"])
def add_verb(german, praesens, past=None, example=""):
    wid = vdb.execute("INSERT INTO words (german, pos, meaning, example) VALUES (?,'动词','测试',?)", (german, example)).lastrowid
    vdb.execute("INSERT INTO word_forms (word_id, forms) VALUES (?,?)", (wid, json.dumps({"praesens": praesens, "past": past or []}, ensure_ascii=False)))
    return wid
vfa = add_verb("zzfahren", ["fahre", "fährst", "fährt", "fahren", "fahrt", "fahren"], ["fuhr", "ist gefahren"])
vho = add_verb("zzabholen", ["hole ab", "holst ab", "holt ab", "holen ab", "holt ab", "holen ab"])
vbad = add_verb("zzkaputt", ["a", "b"])
vdb.commit()
vrow = lambda **k: {"id": 1, "german": "fahren", "meaning": "行驶", "example": "", "details": None,
                    "forms": json.dumps({"praesens": ["fahre", "fährst", "fährt", "fahren", "fahrt", "fahren"], "past": ["fuhr", "ist gefahren"]}), **k}
vinfo = vq.verb_info(vrow())
assert vinfo["changes"] and vq.stem_picks(vinfo, 1) == ["fahrst"] and vq.stem_picks(vinfo, 2) == ["fahrt"] and vq.stem_picks(vinfo, 3) == []
assert vq.verb_info(vrow(forms=json.dumps({"praesens": ["x"]}))) is None
kann = vq.verb_info(vrow(german="können", forms=json.dumps({"praesens": ["kann", "kannst", "kann", "können", "könnt", "können"]})))
assert kann["irregular"] and not kann["changes"] and set(vq.stem_picks(kann, 2)) == {"kannst", "können", "könnt"}
assert vq.regular_du("lest") == "lest" and vq.regular_du("haltet") == "haltest"
assert [vq.full_ich(a, b) for a, b in (("mein", "meinen"), ("feier", "feiern"), ("sammel", "sammeln"), ("kann", "können"), ("tue", "tun"), ("bin", "sind"))] \
    == ["meine", "feiere", "sammle", "kann", "tue", "bin"]
assert vq.verb_info(vrow(german="sollen", forms=json.dumps({"praesens": ["soll", "sollst", "soll", "sollen", "sollt", "sollen"]})))["heads"][0] == "soll"
assert vq.verb_info(vrow(german="wohnen", forms=json.dumps({"praesens": ["wohn", "wohnst", "wohnt", "wohnen", "wohnt", "wohnen"]})))["heads"][0] == "wohne"
vex = lambda text: vq.example_sentences(vrow(example=text), vinfo)
assert vex("Der Zug fährt nach Berlin.\n火车开往柏林。")[0][:2] == (2, "Der Zug ___ nach Berlin.")
assert vex("Wohin fährst du heute?\n你今天去哪里？")[0][:2] == (1, "Wohin ___ du heute?")
assert vex("Wann fahren Sie nach Hause?\n您什么时候回家？")[0][0] == 5
for bad in ("Sie fährt nach Berlin.\n她去柏林。", "Fahrt nach Berlin!\n去柏林！", "Wir wollen morgen fahren.\n我们明天想走。",
            "Fahrt schnell nach Hause.\n快回家。", "Er fährt die Kinder hin.\n他开车送孩子去。",
            "Am Montag können wir fahren.\n星期一我们可以走。"):
    assert vex(bad) == [], bad
vsep = vq.verb_info(vrow(german="abholen", forms=json.dumps({"praesens": ["hole ab", "holst ab", "holt ab", "holen ab", "holt ab", "holen ab"]})))
assert vq.example_sentences(vrow(german="abholen", example="Ich hole dich ab.\n我去接你。"), vsep)[0][:2] == (0, "Ich ___ dich ab.")
vq_short = vq.make_question(vrow(german="zzfahren"), {p: 1 for p in range(6)})
assert vq_short["short"] and vq_short["prompt"].endswith("___") and vq_short["answer"] in vq_short["options"] and len(vq_short["options"]) == 4
vtb = lambda scope="all", n=30: J(cb.get(f"/api/grammar/verbs?scope={scope}&n={n}"))["questions"]
vqs = vtb()
assert vqs and all(x["verb"] and x["answer"] in x["options"] and x["prompt"].count("___") == 1 for x in vqs)
assert vbad not in {x["word_id"] for x in vqs} and len({x["word_id"] for x in vqs}) == len(vqs)
assert next(x for x in vqs if x["word_id"] == vfa)["german"] == "zzfahren"       # 答完打开单词卡用
assert any(x["word_id"] == vho and x["prompt"].endswith(" ab") for x in vqs)
assert cb.get("/api/grammar/verbs?scope=x").status_code == 400 and cb.get("/api/grammar/verbs?n=x").status_code == 400
assert A.app.test_client().get("/api/grammar/verbs").status_code == 401
vres = lambda wid, ok, **b: cb.post("/api/grammar/verbs/result", json={"word_id": wid, "ok": ok, **b})
vst = lambda wid: db.execute("SELECT stability, weak, wrong FROM verb_practice WHERE word_id = ?", (wid,)).fetchone()
assert vres(vfa, False, person=1, kind="person").status_code == 200 and vst(vfa) == (None, 0, 0)   # 人称错不算忘
assert vres(vfa, True, person=1, hinted=True).status_code == 200 and vst(vfa) == (None, 0, 0)
assert vres(vfa, False, person=2, kind="stem").status_code == 200
assert vst(vfa)[0] is not None and vst(vfa)[1:] == (1, 1)
assert db.execute("SELECT person, ok, kind FROM verb_answers ORDER BY id DESC LIMIT 1").fetchone() == (2, 0, "stem")
assert vres(True, True).status_code == 400 and vres(10**7, True).status_code == 404
assert vfa in {x["word_id"] for x in vtb("wrong")}
vb = J(cb.get("/api/grammar/verbs/books"))
assert vb["wrong"] == 1 and all("nouns" in x for x in vb["books"])
vw = J(cb.get("/api/grammar/verbs/words?scope=wrong"))
assert vw["total"] == 1 and vw["words"][0]["id"] == vfa and vw["words"][0]["wrong"] == 1
assert cb.delete(f"/api/grammar/verbs/list/{vfa}").status_code == 200 and J(cb.get("/api/grammar/verbs/books"))["wrong"] == 0
vl = J(cb.post("/api/grammar/verbs/list", json={"text": "zzfahren, Tisch"}))
assert vl["added"] == 1 and "Tisch" in vl["missing"], vl
assert J(cb.post("/api/grammar/verbs/list", json={"text": "zzfahren"}))["skipped"] == 1
assert cb.post("/api/grammar/verbs/list", json={"text": " "}).status_code == 400
assert J(cb.get("/api/grammar/verbs/books"))["wrong"] == 1
# 完成时: 两个空, 和现在时分开记录; 两种助动词都标了的词没有句子时不出题
import perfekt_quiz as pq
from verb_sentences import PERFEKT
vperf = lambda german, part, particle="", aux="hat", pr=None: pq.perf_info(vrow(german=german, forms=json.dumps(
    {"praesens": pr or ["mache", "machst", "macht", "machen", "macht", "machen"], "past": ["x", f"{aux} {part}"]})))
for german, part, pr, wrong in (("machen", "gemacht", None, "gemachen"), ("trinken", "getrunken", None, "getrinkt"),
                                ("bringen", "gebracht", None, "gebringt"), ("arbeiten", "gearbeitet", None, "gearbeiten"),
                                ("besuchen", "besucht", None, "gebesucht"), ("studieren", "studiert", None, "gestudiert"),
                                ("gewinnen", "gewonnen", None, "gegewonnen"), ("gehen", "gegangen", None, "gegeht"),
                                ("abholen", "abgeholt", ["hole ab", "holst ab", "holt ab", "holen ab", "holt ab", "holen ab"], "geabholt"),
                                ("aufstehen", "aufgestanden", ["stehe auf", "stehst auf", "steht auf", "stehen auf", "steht auf", "stehen auf"], "geaufstanden")):
    assert pq.wrong_participle(german, vperf(german, part, pr=pr)) == wrong, german
assert pq.wrong_participle("gefallen", vperf("gefallen", "gefallen")) == "gegefallen" and pq.wrong_participle("geben", vperf("geben", "gegeben")) == "gegebt"
assert [pq.participle_note(g, vperf(g, p)) for g, p in (("machen", "gemacht"), ("bringen", "gebracht"), ("trinken", "getrunken"), ("besuchen", "besucht"), ("studieren", "studiert"))] \
    == ["规则变化 ge-…-t", "混合变化，要单独记", "不规则，过去分词要单独记", "不可分前缀的动词不加 ge-", "-ieren 结尾的动词不加 ge-"]
assert vperf("gehen", "gegangen", aux="ist")["aux"] == "sein" and vperf("fahren", "gefahren", aux="ist/hat")["aux"] is None
pv = vperf("gehen", "gegangen", aux="ist")
pex = lambda text, v=pv: pq.example_sentences(vrow(german="gehen", example=text), v)
assert pex("Er ist nach Hause gegangen.\n他回家了。")[0][:4] == (2, "Er ___ nach Hause ___.", "他回家了。", "sein")
assert pex("Wann bist du gegangen?\n你什么时候走的？")[0][0] == 1
pv2 = vperf("verbieten", "verboten")
for bad in ("Hier ist Rauchen verboten.\n这里禁止吸烟。", "Sie haben das verboten.\n他们禁止了。", "Er hatte das verboten.\n他禁止过。",
            "Das stimmt. Er hat es verboten.\n对。他禁止了。"):
    assert pex(bad, pv2) == [], bad
assert pq.make_question(vrow(german="zzdual", forms=json.dumps({"praesens": ["mache", "machst", "macht", "machen", "macht", "machen"],
                                                                 "past": ["x", "ist/hat gemacht"]})), {p: 1 for p in range(6)}) is None
pq1 = pq.make_question(vrow(german="zzgehen", forms=json.dumps({"praesens": ["gehe", "gehst", "geht", "gehen", "geht", "gehen"],
                                                                  "past": ["ging", "ist gegangen"]})), {p: 1 for p in range(6)})
assert pq1["short"] and pq1["prompt"].count("___") == 2 and pq1["answer"] in pq1["options"] and len(set(pq1["options"])) == 4
assert set(pq1["kinds"].values()) <= {"aux", "part", "person"} and "aux" in pq1["kinds"].values() and pq1["answer"] not in pq1["kinds"]
ptb = lambda scope="all": J(cb.get(f"/api/grammar/perfekt?scope={scope}&n=30"))["questions"]
pqs = ptb()
assert pqs and all(x["verb"] and x["answer"] in x["options"] and x["prompt"].count("___") == 2 for x in pqs), pqs
assert next(x for x in pqs if x["word_id"] == vfa)["german"] == "zzfahren"
pres = lambda wid, ok, **b: cb.post("/api/grammar/perfekt/result", json={"word_id": wid, "ok": ok, **b})
pst = lambda wid: db.execute("SELECT stability, weak, wrong FROM perfekt_practice WHERE word_id = ?", (wid,)).fetchone()
vbefore = vst(vfa)
assert pres(vfa, False, person=1, kind="person").status_code == 200 and pst(vfa) == (None, 0, 0)
assert pres(vfa, False, person=1, kind="aux").status_code == 200 and pst(vfa)[1:] == (1, 1) and vst(vfa) == vbefore
assert db.execute("SELECT tense, kind FROM verb_answers ORDER BY id DESC LIMIT 1").fetchone() == ("perfekt", "aux")
assert pres(vfa, False, person=1, kind="stem").status_code == 200       # 现在时的错因在这里无效, 不记
assert db.execute("SELECT kind FROM verb_answers ORDER BY id DESC LIMIT 1").fetchone() == (None,)
assert J(cb.get("/api/grammar/perfekt/books"))["wrong"] == 1 and vfa in {x["word_id"] for x in ptb("wrong")}
assert J(cb.post("/api/grammar/perfekt/list", json={"text": "zzabholen"}))["added"] == 1
assert J(cb.get("/api/grammar/perfekt/words?scope=wrong"))["total"] == 2
assert cb.delete(f"/api/grammar/perfekt/list/{vho}").status_code == 200 and J(cb.get("/api/grammar/perfekt/books"))["wrong"] == 1
assert cb.get("/api/grammar/nope").status_code == 404 and cb.get("/api/grammar/perfekt?scope=x").status_code == 400
for german, items in PERFEKT.items():
    assert len(items) >= 2 and len({x[1] for x in items}) == len(items), german
    for item in items:
        assert item[0] in range(6) and item[1].count("___") == 2 and not vq.CHINESE.search(item[1]) and vq.CHINESE.search(item[2]), item
        assert len(item) == 3 or item[3] in pq.AUX, item
# 动词搭配: 只练搭配表里的动词, 介词错和格错都算忘了
import verb_usage as vu
for german, usages in vu.USAGES.items():
    for prep, case_no, zh_word, wrong_preps, items in usages:
        assert case_no in (2, 3) and vq.CHINESE.search(zh_word) and items, german
        assert (len(wrong_preps) == 2 and prep not in wrong_preps) if prep else wrong_preps == (), german
        for prompt, right, wrong, zh in items:
            assert prompt.count("___") == (2 if prep else 1) and vq.CHINESE.search(zh) and not vq.CHINESE.search(prompt), prompt
            assert (isinstance(wrong, str) and right != wrong) if prep else (isinstance(wrong, tuple) and wrong and right not in wrong), prompt
            assert not (prep in ("von", "zu", "bei", "an", "in") and right == "dem"), prompt     # 这些要缩写
            q = vu.question({"id": 1, "german": german, "meaning": "x"}, (prep, case_no, zh_word, wrong_preps, items), (prompt, right, wrong, zh))
            assert q["answer"] in q["options"] and len(set(q["options"])) == len(q["options"]) >= 2 and q["answer"] not in q["kinds"], prompt
            assert set(q["kinds"].values()) <= {"prep", "case"}, prompt
vu1 = lambda g, m: vdb.execute("INSERT INTO words (german, pos, meaning) VALUES (?,'动词',?)", (g, m)).lastrowid
vwa, vhe = vu1("warten", "等"), vu1("helfen", "帮助")
vdb.commit()
uqs = J(cb.get("/api/grammar/usage?scope=all&n=30"))["questions"]
assert {x["word_id"] for x in uqs} >= {vwa, vhe} and vfa not in {x["word_id"] for x in uqs}, uqs
uq = next(x for x in uqs if x["word_id"] == vwa)
assert uq["must"] == "（warten）" and uq["answer"].startswith("auf … ") and uq["prompt"].count("___") == 2 and uq["skip_kind"] == "case"
assert vu.label("freuen") == "sich freuen" and vu.label("warten") == "warten"
ures = lambda wid, ok, **b: cb.post("/api/grammar/usage/result", json={"word_id": wid, "ok": ok, **b})
ust = lambda wid: db.execute("SELECT stability, weak, wrong FROM usage_practice WHERE word_id = ?", (wid,)).fetchone()
assert ures(vwa, False, kind="prep").status_code == 200 and ust(vwa)[1:] == (1, 1)
assert db.execute("SELECT tense, kind, person FROM verb_answers ORDER BY id DESC LIMIT 1").fetchone() == ("usage", "prep", None)
assert ures(vhe, True).status_code == 200 and ust(vhe)[1:] == (0, 0)
ub = J(cb.get("/api/grammar/usage/books"))
assert ub["wrong"] == 1 and {"book": "all"}.items() <= [x for x in ub["books"] if x["book"] == "all"][0].items()
assert [x for x in ub["books"] if x["book"] == "all"][0]["nouns"] >= 2
assert J(cb.get("/api/grammar/usage/words?scope=wrong"))["words"][0]["id"] == vwa
assert vwa in {x["word_id"] for x in J(cb.get("/api/grammar/usage?scope=wrong"))["questions"]}
ul = J(cb.post("/api/grammar/usage/list", json={"text": "helfen, zzfahren"}))
assert ul["added"] == 1 and ul["missing"] == ["zzfahren"], ul        # 不在搭配表里的动词加不进来
assert cb.delete(f"/api/grammar/usage/list/{vhe}").status_code == 200 and cb.delete(f"/api/grammar/usage/list/{vwa}").status_code == 200
assert J(cb.get("/api/grammar/usage/books"))["wrong"] == 0
# 手写句子: 每句一个空, 德语不混中文, 第一位不用 sie / Sie
for german, items in WRITTEN.items():
    assert len(items) >= 2 and len({x[1] for x in items}) == len(items), german
    for person, de, zh in items:
        assert person in range(6) and de.count("___") == 1 and not vq.CHINESE.search(de) and vq.CHINESE.search(zh), de
        assert not de.startswith(("Sie ", "sie ")), de
res(cb, fresh, False, must="单数", kind="gender", cell="kein:der:3")
assert npr(fresh)[2] == 1 and acell() == ("kein:der:3", "gender")                 # 词性答错进错题本, 和定冠词共用
assert NQ.memory_rating(True, "单数", False, None, True) is None and NQ.memory_rating(False, "单数", False, "gender", True) == 1

db.close()

# 今日学习: 新词 = 学习量 + 加量 − 已学 − 还没复习的到期词; 换日按本地时间凌晨 4 点
from datetime import datetime, timedelta, timezone
T.NEW_PER_REQUEST = 50
assert srs.day_gap(datetime(2026, 1, 1, 21, tzinfo=timezone.utc), datetime(2026, 1, 2, 8, tzinfo=timezone.utc)) == 1   # 昨晚 → 今早
assert srs.day_gap(datetime(2026, 1, 1, 21, tzinfo=timezone.utc), datetime(2026, 1, 2, 3, tzinfo=timezone.utc)) == 0   # 半夜还算同一天
with A.app.test_request_context():
    d0, s0_, e0 = T.local_day(-60)
    assert datetime.strptime(e0, "%Y-%m-%d %H:%M:%S") - datetime.strptime(s0_, "%Y-%m-%d %H:%M:%S") == timedelta(days=1)
    assert s0_.endswith("03:00:00")                                               # 德国冬令时凌晨 4 点 = UTC 3 点
tdb = sqlite3.connect(os.environ["DB_PATH"])
tcode = J(c.post("/api/invites", json={}))["code"]
ct = A.app.test_client()
assert ct.post("/api/register", json={"username": "carol", "password": "12345678", "invite": tcode}).status_code == 200
carol = tdb.execute("SELECT id FROM users WHERE username = 'carol'").fetchone()[0]
for i in range(60):
    tdb.execute("INSERT INTO words (german, pos, gender, plural, meaning, example) VALUES (?,'名词','der','','测试','')", (f"Testwort{i}",))
tdb.commit()
tt = lambda: J(ct.get("/api/today"))
assert ct.post("/api/today/goal", json={"goal": 5}).status_code == 400 and ct.post("/api/today/goal", json={"goal": True}).status_code == 400
assert ct.post("/api/today/goal", json={"goal": 20}).status_code == 200 and tt()["goal"] == 20
ct.post("/api/books/current", json={"book": "all"})
assert tt()["new"] == 20 and tt()["due"] == 0 and tt()["target"] == 20
assert J(c.get("/api/today"))["goal"] == 500                                      # 各管各的
# 8 个到期词: 新词变少
some = [x[0] for x in tdb.execute("SELECT id FROM words WHERE status = 'public' ORDER BY id LIMIT 30").fetchall()]
for w in some[:8]:
    tdb.execute("INSERT INTO progress (user_id, word_id, next_review, stability, difficulty, last_review, reps) "
                "VALUES (?,?,datetime('now','-1 hour'),3,5,datetime('now','-3 days'),1)", (carol, w))
tdb.commit()
assert tt()["due"] == 8 and tt()["new"] == 12
# 今晚才到期的词今早也算到期(到今天结束前)
late = datetime.strptime(T.local_day(0)[2], "%Y-%m-%d %H:%M:%S") - timedelta(minutes=1)
tdb.execute("UPDATE progress SET next_review = ? WHERE user_id = ? AND word_id = ?",
            (late.strftime("%Y-%m-%d %H:%M:%S"), carol, some[0]))
tdb.commit()
assert tt()["due"] == 8
tdb.execute("UPDATE progress SET next_review = ? WHERE user_id = ? AND word_id = ?",
            (T.local_day(0)[2], carol, some[0]))
tdb.commit()
assert tt()["due"] == 7                                                            # 明天才到期
tdb.execute("UPDATE progress SET next_review = datetime('now','-1 hour') WHERE user_id = ? AND word_id = ?", (carol, some[0]))
tdb.commit()
# 学完一个到期词: 不再算到期, 算已学, 新词数不变
rc = J(ct.get("/api/review/today"))
assert rc["due"] == 8 and rc["new"] == 12 and all(not x["is_new"] for x in rc["cards"][:8])    # 先复习再新词
ansc = lambda wid, rating=3: ct.post("/api/review/answer", json={"word_id": wid, "rating": rating, "mode": "recall"})
assert J(ansc(rc["cards"][0]["id"]))["log_id"]
assert tt()["done"] == 1 and tt()["due"] == 7 and tt()["new"] == 12
# 忘了: 今天还要再练, 但只算一个词
fw = rc["cards"][1]["id"]
ansc(fw, 1)
assert tt()["done"] == 2 and tt()["due"] == 7 and tt()["new"] == 12
ansc(fw, 3)
assert tt()["done"] == 2 and tt()["due"] == 6
# 到期词比学习量多: 全部要复习, 没有新词
for w in some[8:30]:
    tdb.execute("INSERT INTO progress (user_id, word_id, next_review, stability, difficulty, last_review, reps) "
                "VALUES (?,?,datetime('now','-1 hour'),3,5,datetime('now','-3 days'),1)", (carol, w))
tdb.commit()
assert tt()["due"] == 28 and tt()["new"] == 0
# 单个添加: 学习量 +1, 到期词再多今天也能学到; 批量导入只排队, 不加量
xw = J(ct.post("/api/words", json={"german": "Testeinzel", "gender": "der", "pos": "名词", "meaning": "单个"}))
q3 = lambda x: (x["added"], x["skipped"], x["queued"])
assert q3(xw) == (1, 0, 1) and tt()["target"] == 21 and tt()["new"] == 1
xc = J(ct.get("/api/review/today"))["cards"][-1]
assert xc["german"] == "Testeinzel" and xc["is_new"]
pub = J(ct.post("/api/words", json={"german": "Testwort50", "gender": "der", "meaning": "x"}))   # 词库已有: 只进计划
assert q3(pub) == (0, 1, 1) and tt()["target"] == 22 and tt()["new"] == 2
bulk = J(ct.post("/api/words", json=[{"german": "Testbatch", "gender": "der", "pos": "名词", "meaning": "批量"}]))
assert q3(bulk) == (1, 0, 1) and tt()["target"] == 22 and tt()["new"] == 2     # 排队, 现在没有名额
assert J(ct.post("/api/review/queue", json={"word_id": some[0]}))["learned"]                              # 学过的不加
ids_new = [x["id"] for x in J(ct.get("/api/review/today"))["cards"] if x["is_new"]]
assert len(ids_new) == 2
ansc(ids_new[0]); assert tt()["target"] == 22 and tt()["new"] == 1                                         # 加的词学完, 量不变
# 再学 10 个: 只加今天, 第二次累加
J(ct.post("/api/today/more", json={})); assert tt()["extra"] == 10
J(ct.post("/api/today/more", json={})); assert tt()["extra"] == 20 and tt()["target"] == 42
tdb.execute("UPDATE user_settings SET value = '2000-01-01' WHERE user_id = ? AND key = 'extra_day'", (carol,)); tdb.commit()
assert tt()["extra"] == 0
tdb.close()

# 词典校验加词: 词库有 → 共用; 词典有 → 公开; 变化形式 → 原形; 词典没有 → 待审核
import zlib
import lexicon as LX, word_add as WA
td = os.path.dirname(os.environ["DB_PATH"])
lp = os.path.join(td, "lex.db")
ldb = sqlite3.connect(lp); ldb.executescript(LX.SCHEMA)
rt_forms = {"cases": {"sg": ["das Rolltor", "des Rolltors", "dem Rolltor", "das Rolltor"], "pl": ["die Rolltore", "der Rolltore", "den Rolltoren", "die Rolltore"]}}
ldb.executemany("INSERT INTO lemmas (german, low, gender, pos, plural, meaning, forms) VALUES (?,?,?,?,?,?,?)", [
    ("Rolltor", "rolltor", "das", "名词", "Rolltore", "卷帘门", zlib.compress(json.dumps(rt_forms).encode())),
    ("Greifer", "greifer", "der", "名词", "Greifer", "", None), ("Hub", "hub", "der", "名词", "Hube", "升程", None),
    ("Wagen", "wagen", "der", "名词", "Wagen", "车", None), ("Band", "band", "das", "名词", "Bänder", "带子", None),
    ("Band", "band", "die", "名词", "Bands", "乐队", None), ("Sackkarre", "sackkarre", "die", "名词", "Sackkarren", "手推车", None)])
ldb.execute("INSERT INTO forms (form, german) VALUES ('rolltore', 'Rolltor')"); ldb.commit(); ldb.close()
LX.PATH = lp
add = lambda client, **b: client.post("/api/words", json=b)
assert LX.find("rolltor")[0]["german"] == "Rolltor" and LX.find("Rolltore") == (None, "Rolltor") and LX.find("asdf") == (None, None)
assert LX.find("Band", "die")[0]["gender"] == "die" and LX.compound("Hubwagen") == "Hub + Wagen" and LX.compound("Asdfgh") is None
# 只写德语词: 冠词、复数、变格来自词典, 所有人都能看到
ra = J(add(ct, german="rolltor"))
assert ra["added"] == 1 and ra["queued"] == 1 and ra["pending"] == 0
rw_ = J(cb.get("/api/words?q=Rolltor"))["words"][0]
assert (rw_["german"], rw_["gender"], rw_["plural"], rw_["meaning"], rw_["private"]) == ("Rolltor", "das", "Rolltore", "卷帘门", False)
assert J(cb.get(f"/api/words/{rw_['id']}"))["forms"] == rt_forms
assert J(ct.get("/api/words?level=mine&q=Rolltor"))["words"] and not J(cb.get("/api/words?level=mine&q=Rolltor"))["words"]
# 第二个人加同一个词: 不重复; 他写的释义只对他显示, 公共内容不变; 写的冠词不算数
rb = J(add(cb, german="Rolltor", gender="der", meaning="我自己的释义"))
assert rb["skipped"] == 1 and rb["queued"] == 1
assert J(cb.get(f"/api/words/{rw_['id']}"))["meaning"] == "我自己的释义" and J(ct.get(f"/api/words/{rw_['id']}"))["meaning"] == "卷帘门"
# 带冠词写也行; 变化形式: 单个要确认, 批量自动用原形
assert J(add(c, german="die Sackkarre"))["added"] == 1
assert J(add(c, german="Rolltore")) == {"added": 0, "skipped": 0, "queued": 0, "pending": 0, "lemma": 0, "invalid": [], "form_of": "Rolltor"}
bk = J(c.post("/api/words", json=[{"german": "Rolltore"}, {"german": "<b>"}, {"german": "Keinwort"}, {"german": "Testneu", "meaning": "新"}]))
assert (bk["skipped"], bk["lemma"], bk["pending"], bk["added"], bk["invalid_count"]) == (1, 1, 1, 1, 2) and bk["invalid"] == ["<b>", "Keinwort"]
assert add(c, german="<script>").status_code == 400 and add(c, german="Asdfgh").status_code == 400     # 词典没有又没写释义
# 词库还没有、词典有的词也查得到, 加入学习时才放进词库; 词典没有释义时要写上
dg = dq(c, "Greifer")[0]
assert dg["glossary"] and dg["id"] is None and dg["needs_meaning"] and dg["meaning"] == "暂无释义，写上释义后可以加入学习"
assert not dq(c, "Hub")[0].get("needs_meaning")
assert add(cb, german="Greifer").status_code == 400                               # 没有可靠释义, 不放进背不了的卡片
assert J(add(cb, german="Greifer", meaning="抓斗"))["added"] == 1
gid = J(cb.get("/api/words?q=Greifer"))["words"][0]["id"]
assert J(cb.get(f"/api/words/{gid}"))["meaning"] == "抓斗" and J(c.get(f"/api/words/{gid}"))["meaning"] == "释义待补充"
assert add(c, german="Greifer").status_code == 400 and J(add(cb, german="Greifer"))["skipped"] == 1   # 他自己写过的不用再写
# 管理员补公共释义: AI 只出草稿, 确认后才写入; 用户自己写的不变
pending_list = lambda: {x["german"]: x for x in J(c.get("/api/admin/pending"))["words"]}
assert pending_list()["Greifer"]["kind"] == "no_meaning" and pending_list()["Greifer"]["users"] == 1
assert cb.post(f"/api/admin/words/{gid}/draft", json={}).status_code == 403
WA.call_gemini = lambda prompt: json.dumps({"found": True, "german": "Greifer", "gender": "der", "pos": "名词", "plural": "Greifer", "meaning": "抓手", "example": ""})
assert J(c.post(f"/api/admin/words/{gid}/draft", json={}))["meaning"] == "抓手"
assert J(c.get(f"/api/words/{gid}"))["meaning"] == "释义待补充"                    # 草稿没写入
assert c.post(f"/api/admin/words/{gid}/meaning", json={"meaning": "abc"}).status_code == 400
assert c.post(f"/api/admin/words/{gid}/meaning", json={"meaning": "抓手", "ai": True}).status_code == 200
assert J(c.get(f"/api/words/{gid}"))["meaning"] == "抓手" and J(c.get(f"/api/words/{gid}"))["details"] == {"machine": True}
assert J(cb.get(f"/api/words/{gid}"))["meaning"] == "抓斗" and "Greifer" not in pending_list()
assert c.post(f"/api/admin/words/{gid}/meaning", json={"meaning": "再改"}).status_code == 404
assert c.post(f"/api/admin/words/{gid}/draft", json={}).status_code == 404
assert J(add(c, german="Greifer"))["skipped"] == 1                                 # 有公共释义后直接能加
WA.call_gemini = real_call
# 审核: 待审核的词只有加过的人看得到, 通过后所有人都有, 编号和进度不变
assert J(add(ct, german="Hubwagen", gender="der", pos="名词", meaning="手动叉车"))["pending"] == 1
assert J(add(cb, german="Hubwagen", gender="der", meaning="液压车"))["skipped"] == 0
assert cb.get("/api/admin/pending").status_code == 403
pl = {x["german"]: x for x in J(c.get("/api/admin/pending"))["words"]}
assert pl["Hubwagen"]["users"] == 2 and pl["Hubwagen"]["compound"] == "Hub + Wagen"
assert J(c.get("/api/words?q=Hubwagen"))["words"] == []                           # 管理员没加过, 词库里也看不到
hid = pl["Hubwagen"]["id"]
assert c.post(f"/api/admin/pending/{hid}", json={"status": "x"}).status_code == 400 and cb.post(f"/api/admin/pending/{hid}", json={"status": "public"}).status_code == 403
assert c.post(f"/api/admin/pending/{hid}", json={"status": "public"}).status_code == 200
assert c.post(f"/api/admin/pending/{hid}", json={"status": "public"}).status_code == 404   # 已经审过
hw_ = J(c.get("/api/words?q=Hubwagen"))["words"][0]; assert hw_["id"] == hid and hw_["meaning"] == "手动叉车" and not hw_["private"]
assert J(cb.get("/api/words?q=Hubwagen"))["words"][0]["meaning"] == "液压车"
# 拒绝: 不公开, 但还留在加过的人那里
wz = [x for x in J(c.get("/api/admin/pending"))["words"] if x["german"] == "Testneu"][0]
assert c.post(f"/api/admin/pending/{wz['id']}", json={"status": "rejected"}).status_code == 200
assert J(cb.get("/api/words?q=Testneu"))["words"] == [] and J(c.get("/api/words?q=Testneu"))["words"][0]["private"]
assert "Testneu" not in [x["german"] for x in J(c.get("/api/admin/pending"))["words"]]
# 待审核的词进了单词书: 就是这一行, 变成公开
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import import_wordbook as IW
zpid = zid
wb = os.path.join(td, "wb.json")
keep_words = [{"german": r0, "gender": r1, "pos": "", "plural": "", "meaning": r2, "example": "", "books": {"dsh": 1}}
              for r0, r1, r2 in [("Zebra", "das", "斑马（单词书）")]]
json.dump({"words": keep_words}, open(wb, "w", encoding="utf-8"), ensure_ascii=False)
argv0 = sys.argv; sys.argv = ["x", wb]; IW.main(); sys.argv = argv0
assert J(ct.get(f"/api/words/{zpid}"))["meaning"] == "斑马（单词书）" and not J(ct.get(f"/api/words/{zpid}"))["private"]
# 复数修正: 改复数、重写变格表、改冠词(编号不变)、去掉重复的词条
import merge_wordbook as MW
sg = ["der Keks", "des Kekses", "dem Keks", "den Keks"]
mw = lambda g, a, p, f=None: {"german": g, "gender": a, "plural": p, "forms": f}
fixb = MW.Book([mw("Keks", "der", "Keks", {"cases": {"sg": sg, "pl": ["die Keks"] * 4}}), mw("Eigentum", "das", "Eigentume", {"cases": {"sg": sg, "pl": ["x"] * 4}}),
                mw("Eltern", "die", "Eltern", {"cases": {"sg": ["", "", "", ""], "pl": ["die Eltern"] * 4}}),
                mw("Kilo", "der", "Kilo"), mw("Schülerin", "die", "Schülerinnen"), mw("Schülerin", "der", "Schülerinnen")])
assert MW.apply_plural_fixes(fixb, [("der", "Keks", "Kekse", ""), ("das", "Eigentum", "-", ""), ("die", "Eltern", "-", ""),
                                    ("der", "Kilo", "=", "das"), ("der", "Schülerin", "=", "die"), ("der", "Weg", "x", "")]) == ["der Weg"]
fw = {(w["german"], w["gender"]): w for w in fixb.words}
assert fw["Keks", "der"]["forms"]["cases"]["pl"] == ["die Kekse", "der Kekse", "den Keksen", "die Kekse"] and fw["Keks", "der"]["forms_fixed"]
assert fw["Eigentum", "das"]["plural"] == "" and fw["Eigentum", "das"]["forms"]["cases"]["pl"] == [""] * 4
assert fw["Eltern", "die"]["plural"] == "" and fw["Eltern", "die"]["forms"]["cases"]["pl"][0] == "die Eltern" and "forms_fixed" not in fw["Eltern", "die"]
assert fw["Kilo", "das"]["old_gender"] == "der" and fw["Kilo", "das"]["plural"] == "Kilo"
assert len(fixb.words) == 5 and ("Schülerin", "der") not in fw
assert MW.plural_cases("Autos")[2] == "den Autos" and MW.plural_cases("Boni")[2] == "den Boni" and MW.plural_cases("Leitern")[2] == "den Leitern"
assert MW.plural_cases("Kekse")[2] == "den Keksen" and MW.plural_cases("Kaufleute")[2] == "den Kaufleuten"
idb = sqlite3.connect(os.environ["DB_PATH"])
kid = idb.execute("INSERT INTO words (german, pos, gender, plural, meaning, example) VALUES ('Testkeks','名词','der','Testkeks','饼干','')").lastrowid
oldc = json.dumps({"cases": {"sg": ["der Testkeks", "des Testkekses", "dem Testkeks", "den Testkeks"], "pl": ["die Testkeks"] * 4}, "past": ["a", "b"]})
idb.execute("INSERT INTO word_forms (word_id, forms) VALUES (?,?)", (kid, oldc)); idb.commit()
newc = {"sg": ["der Testkeks", "des Testkekses", "dem Testkeks", "den Testkeks"], "pl": ["die Testkekse", "der Testkekse", "den Testkeksen", "die Testkekse"]}
for fixed, first in ((False, "die Testkeks"), (True, "die Testkekse")):
    item = {"german": "Testkeks", "gender": "der", "pos": "名词", "plural": "Testkekse", "meaning": "饼干", "example": "", "level": "A1", "rank": 1,
            "forms": {"cases": newc}}
    if fixed:
        item["forms_fixed"] = True
    json.dump({"words": keep_words + [item]}, open(wb, "w", encoding="utf-8"), ensure_ascii=False)
    argv0 = sys.argv; sys.argv = ["x", wb]; IW.main(); sys.argv = argv0
    assert json.loads(idb.execute("SELECT forms FROM word_forms WHERE word_id = ?", (kid,)).fetchone()[0])["cases"]["pl"][0] == first
assert idb.execute("SELECT plural FROM words WHERE id = ?", (kid,)).fetchone()[0] == "Testkekse"
idb.close()
# 迁移旧版私有词: 同一个词合并成一行, 进度搬过来, 自己写的内容留着, 词典有的公开
mdb = sqlite3.connect(os.environ["DB_PATH"]); mdb.execute("PRAGMA foreign_keys = ON")
ua, ub = [mdb.execute("SELECT id FROM users WHERE username = ?", (n,)).fetchone()[0] for n in ("alice", "carol")]
ins = "INSERT INTO words (german, pos, gender, plural, meaning, example, owner_id, status) VALUES (?,'名词',?,'',?,'',?,'public')"
m1 = mdb.execute(ins, ("Altwort", "der", "旧释义一", ua)).lastrowid
m2 = mdb.execute(ins, ("Altwort", "der", "旧释义二", ub)).lastrowid
m3 = mdb.execute(ins, ("Band", "das", "我的带子", ub)).lastrowid
mdb.execute("INSERT INTO progress (user_id, word_id, next_review, stability, reps) VALUES (?,?,'2030-01-01 00:00:00',9,3)", (ub, m2))
mdb.execute("INSERT INTO noun_list (user_id, word_id, added_at) VALUES (?,?,'x')", (ub, m2))
database.share_private_words(mdb); mdb.commit()
assert mdb.execute("SELECT COUNT(*) FROM words WHERE owner_id IS NOT NULL").fetchone()[0] == 0
assert mdb.execute("SELECT id, status FROM words WHERE german = 'Altwort'").fetchall() == [(m1, "pending")]
assert mdb.execute("SELECT stability, reps FROM progress WHERE user_id = ? AND word_id = ?", (ub, m1)).fetchone() == (9, 3)
assert mdb.execute("SELECT 1 FROM noun_list WHERE user_id = ? AND word_id = ?", (ub, m1)).fetchone()
assert mdb.execute("SELECT COUNT(*) FROM user_added_words WHERE word_id = ?", (m1,)).fetchone()[0] == 2
assert mdb.execute("SELECT meaning FROM user_word_edits WHERE user_id = ? AND word_id = ?", (ub, m1)).fetchone() == ("旧释义二",)
assert mdb.execute("SELECT 1 FROM user_word_edits WHERE user_id = ? AND word_id = ?", (ua, m1)).fetchone() is None
assert mdb.execute("SELECT status, meaning FROM words WHERE id = ?", (m3,)).fetchone() == ("public", "带子")
assert mdb.execute("SELECT meaning FROM user_word_edits WHERE user_id = ? AND word_id = ?", (ub, m3)).fetchone() == ("我的带子",)
database.share_private_words(mdb); mdb.close()                                    # 再跑一次没影响
LX.PATH = "没有这个文件"
assert LX.find("Rolltor") == (None, None) and LX.compound("Hubwagen") is None

c.post("/api/logout", json={})
assert c.get("/api/review/today").status_code == 401

# 迁移: 旧版数据库(progress 只有 level) 启动后补字段, Leitner 进度换算成 FSRS, 原数据不丢
old = os.path.join(os.path.dirname(os.environ["DB_PATH"]), "old.db")
o = sqlite3.connect(old)
o.executescript("""
CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL);
CREATE TABLE words (id INTEGER PRIMARY KEY AUTOINCREMENT, german TEXT NOT NULL, pos TEXT NOT NULL DEFAULT '',
  gender TEXT NOT NULL DEFAULT '', plural TEXT NOT NULL DEFAULT '', meaning TEXT NOT NULL, example TEXT NOT NULL DEFAULT '',
  UNIQUE (german, gender));
CREATE TABLE progress (user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE, next_review TEXT NOT NULL,
  level INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (user_id, word_id));
INSERT INTO users VALUES (1, 'old', 'x');
INSERT INTO words (german, gender, meaning) VALUES ('Tisch', 'der', '桌子'), ('Haus', 'das', '房子');
INSERT INTO progress VALUES (1, 1, '2026-01-10 08:00:00', 3), (1, 2, '2026-01-01 08:00:00', 0);
""")
o.commit(); o.close()
database.DB_PATH = old
database.init_db(); database.init_db()  # 运行两次也不出问题
o = sqlite3.connect(old)
rows = o.execute("SELECT word_id, next_review, level, stability, difficulty, last_review, reps, spell_ok FROM progress ORDER BY word_id").fetchall()
assert rows[0] == (1, "2026-01-10 08:00:00", 3, 4.0, 5.0, "2026-01-06 08:00:00", 3, 0), rows[0]
assert rows[1][3] == srs.W[0] and rows[1][6] == 0, rows[1]
assert o.execute("SELECT COUNT(*) FROM words").fetchone()[0] == 2
assert o.execute("SELECT COUNT(*) FROM word_forms").fetchone()[0] == 2  # 示例词也补上了变格
# 迁移: words 重建成带 owner_id 的新表(编号不变, 外键完好, 重建前自动备份)
assert "owner_id" in {r[1] for r in o.execute("PRAGMA table_info(words)")}
assert o.execute("SELECT id, german, owner_id FROM words ORDER BY id").fetchall() == [(1, "Tisch", None), (2, "Haus", None)]
assert o.execute("PRAGMA foreign_key_check").fetchall() == []
assert {"idx_words_public", "idx_words_private"} <= {r[1] for r in o.execute("PRAGMA index_list(words)")}
assert os.path.exists(old + ".bak-before-private-words")
o.close()
print("ALL OK")
