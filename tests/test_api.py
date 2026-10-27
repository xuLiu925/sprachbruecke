import json, os, sqlite3, sys, tempfile
d = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(d, "t.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
import database, srs
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
for _ in range(8): c3.post("/api/login", json={"username": "carol", "password": "x"})
assert c3.post("/api/login", json={"username": "carol", "password": "x"}).status_code == 429

# 单词书: 还没有分级的词时默认「全部」; 有了以后默认 A1, 新词按 rank 出
assert J(c.get("/api/books"))["current"] == "all"
db = sqlite3.connect(os.environ["DB_PATH"])
ids = {g: i for i, g in db.execute("SELECT id, german FROM words")}
db.executemany("INSERT INTO word_levels (word_id, level, rank) VALUES (?,?,?)",
               [(ids["Katze"], "A1", 2), (ids["Hund"], "A1", 1), (ids["Kind"], "A2", 3)])
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

# 添加单词 = 私有词: 只有自己看得到; 别人访问不了; 不同的人可以各自加同一个词
z = J(c.post("/api/words", json={"german": "Zebra", "gender": "das", "meaning": "斑马"})); assert z["added"] == 1
zid = db.execute("SELECT id FROM words WHERE german = 'Zebra' AND owner_id = (SELECT id FROM users WHERE username = 'alice')").fetchone()[0]
zw = J(c.get(f"/api/words/{zid}")); assert zw["private"] and zw["meaning"] == "斑马"
assert [w["private"] for w in J(c.get("/api/words?q=Zebra"))["words"]] == [True]
assert J(cb.get("/api/words?q=Zebra"))["words"] == []
assert cb.get(f"/api/words/{zid}").status_code == 404
assert cb.post("/api/review/answer", json={"word_id": zid, "rating": 3}).status_code == 404
assert cb.delete(f"/api/words/{zid}").status_code == 404
assert cb.put(f"/api/words/{zid}", json={**zw, "meaning": "x"}).status_code == 404
assert J(cb.post("/api/words", json={"german": "Zebra", "gender": "das", "meaning": "斑马(bob)"}))["added"] == 1
assert [w["meaning"] for w in J(cb.get("/api/words?q=Zebra"))["words"]] == ["斑马(bob)"]
assert [w["meaning"] for w in J(c.get("/api/words?q=Zebra"))["words"]] == ["斑马"]
assert J(c.post("/api/words", json={"german": "Zebra", "gender": "das", "meaning": "y"}))["added"] == 0
# 公共词库里已经有的不重复加; 删掉过的再加 = 恢复(自己的私有词也一样)
assert J(c.post("/api/words", json={"german": "Katze", "gender": "die", "meaning": "y"})) == {"added": 0, "skipped": 1}
c.delete(f"/api/words/{ids['Katze']}")
assert J(c.post("/api/words", json={"german": "Katze", "gender": "die", "meaning": "y"})) == {"added": 1, "skipped": 0}
assert not get(c, "Katze")["hidden"] and get(c, "Katze")["meaning"] == "猫"
c.delete(f"/api/words/{zid}")
assert J(c.post("/api/words", json={"german": "Zebra", "gender": "das", "meaning": "y"}))["added"] == 1
assert not J(c.get(f"/api/words/{zid}"))["hidden"]
n_alice = db.execute("SELECT COUNT(*) FROM words WHERE owner_id = (SELECT id FROM users WHERE username = 'alice')").fetchone()[0]
n_public = db.execute("SELECT COUNT(*) FROM words WHERE owner_id IS NULL").fetchone()[0]
assert J(c.get("/api/stats"))["total"] == n_public + n_alice and J(cb.get("/api/stats"))["total"] == n_public + 1
db.close()

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
