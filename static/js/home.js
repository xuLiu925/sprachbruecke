// 首页、练习列表、我的
const MODULES = [
  { ico: "🔤", name: "词汇", sub: "复习 · 拼写", page: "practice" },
  { ico: "📐", name: "语法", sub: `${GRAMMAR_TOPICS.length} 个知识点`, page: "grammar" }, { ico: "💬", name: "句子" },
  { ico: "🎧", name: "听力" }, { ico: "📖", name: "阅读" }, { ico: "📝", name: "考试" },
];

function buildModules() {
  const box = $("modules");
  for (const m of MODULES) {
    const t = document.createElement("button");
    t.className = "tile" + (m.page ? "" : " off");
    const i = document.createElement("span"); i.className = "ico"; i.textContent = m.ico;
    const s = document.createElement("small"); s.textContent = m.sub || "即将推出";
    t.append(i, m.name, s);
    t.onclick = () => !m.page ? toast(m.name + "模块即将推出") : PAGES[m.page].tab ? switchTab(m.page) : go(m.page);
    box.appendChild(t);
  }
}
buildModules();

const BOOK_NAMES = { A1: "A1 入门", A2: "A2 基础", B1: "B1 进阶", B2: "B2 中高级", C1: "C1 高级", all: "全部单词",
                     dsh: "德福 DSH 核心词汇", common: "德语常用词汇" };

onShow.home = async () => {
  $("hello").textContent = "你好，" + user;
  const s = await loadStats();
  const newAvail = Math.min(10, s.book_total - s.book_learned);
  $("hBookName").textContent = "单词书：" + BOOK_NAMES[s.book];
  $("hBookProg").textContent = s.book_total && s.book_learned >= s.book_total
    ? "这本学完了，换一本吧" : `共 ${s.book_total} 个词，进度见下方`;
  $("hDue").textContent = s.due;
  $("hNew").textContent = newAvail;
  $("hLearned").textContent = s.learned;
  $("hMastered").textContent = s.mastered;
  $("hTotal").textContent = s.total;
  // 进度条显示当前单词书(整个词库太大, 条几乎是空的): 浅色 = 已学, 绿色 = 已掌握
  const pct = n => s.book_total ? n / s.book_total * 100 : 0;
  $("hBarTitle").textContent = BOOK_NAMES[s.book];
  $("hBarLearned").style.width = pct(s.book_learned) + "%";
  $("hBar").style.width = pct(s.book_mastered) + "%";
  $("hBarText").textContent = `已学 ${s.book_learned}（${Math.round(pct(s.book_learned))}%）· 已掌握 ${s.book_mastered} · 共 ${s.book_total} 个`;
  const nothing = s.due + newAvail === 0;
  $("hStart").disabled = nothing;
  $("hStart").textContent = nothing ? "今天的任务完成了 🎉" : "开始今日复习";
};
$("hStart").onclick = () => go("review");
$("hBook").onclick = () => go("books");

// ---------- 选择单词书 ----------
onShow.books = async () => {
  const r = await api("/api/books");
  const box = $("bookList"); box.textContent = "";
  const all = { level: "all", total: null };
  for (const b of [...r.books, ...r.themes, all]) {
    const sub = b.level === "all" ? "整个词库，包括示例词和你自己加的词"
      : b.total ? `${b.total} 个词 · 已学 ${b.learned} · 已掌握 ${b.mastered}` : "还没有导入";
    const it = listItem(b.level === "all" ? "🗃️" : "📘", BOOK_NAMES[b.level], sub, async () => {
      if (b.total === 0) return toast("这本还没有导入");
      await api("/api/books/current", "POST", { book: b.level });
      toast("已切换到 " + BOOK_NAMES[b.level]);
      $("btnBack").click();
    }, b.total === 0);
    if (b.total) {   // 进度条: 已学多少
      const bar = document.createElement("div"); bar.className = "bar";
      const fill = document.createElement("i"); fill.style.width = (b.learned / b.total * 100) + "%";
      bar.appendChild(fill);
      it.querySelector(".body").appendChild(bar);
    }
    if (b.level === r.current) {
      it.classList.add("current");
      it.querySelector(".chev").textContent = "✓";
    }
    box.appendChild(it);
  }
};

// ---------- 练习列表 ----------
function listItem(ico, title, sub, onclick, off) {
  const b = document.createElement("button");
  b.className = "item" + (off ? " off" : "");
  const i = document.createElement("span"); i.className = "ico"; i.textContent = ico;
  const body = document.createElement("span"); body.className = "body";
  const t = document.createElement("b"); t.textContent = title;
  const s = document.createElement("small"); s.textContent = sub;
  body.append(t, s);
  const badge = document.createElement("span"); badge.className = "badge hidden";
  const chev = document.createElement("span"); chev.className = "chev"; chev.textContent = "›";
  b.append(i, body, badge, chev);
  b.onclick = onclick;
  return b;
}

const reviewItem = listItem("🗂️", "今日复习", "认词 + 拼写，按 FSRS 安排复习", () => go("review"));
$("practiceList").append(reviewItem, listItem("🎨", "冠词练习", "der / die / das 选择题", () => go("drill")),
                        listItem("✍️", "听写", "听发音写单词，优先出学过的词", () => go("dictation")),
                        listItem("📐", "语法基础", "冠词、代词、介词、动词、语序的速查表和练习", () => go("grammar")));
for (const [ico, t, s] of [["🔢", "复数练习", "看单数写复数"], ["🧩", "变格练习", "四个格的冠词和词尾"],
                           ["🔁", "动词变位", "不同人称的现在时"]]) {
  $("soonList").appendChild(listItem(ico, t, s, () => toast("即将推出"), true));
}

onShow.practice = async () => {
  const s = await loadStats();
  const badge = reviewItem.querySelector(".badge");
  badge.textContent = s.due;
  badge.classList.toggle("hidden", !s.due);
};

// ---------- 我的 ----------
onShow.me = async () => {
  $("meName").textContent = user;
  $("avatar").textContent = (user || "?").slice(0, 1).toUpperCase();
  const s = await loadStats();
  $("meStats").textContent = `已学 ${s.learned} · 已掌握 ${s.mastered}`;
  $("adminBox").classList.toggle("hidden", !isAdmin);
  if (isAdmin) loadAdmin();
};

// 改密码
$("btnPwToggle").onclick = () => { $("pwBox").classList.toggle("hidden"); $("pwMsg").textContent = ""; };
$("btnPwSave").onclick = async () => {
  const msg = $("pwMsg"); msg.className = "msg";
  if ($("pwNew").value !== $("pwNew2").value) { msg.textContent = "两次输入的新密码不一样"; return; }
  try {
    await api("/api/password", "POST", { old: $("pwOld").value, new: $("pwNew").value });
    ["pwOld", "pwNew", "pwNew2"].forEach(id => $(id).value = "");
    $("pwBox").classList.add("hidden");
    toast("密码已修改");
  } catch (e) { msg.textContent = e.message; }
};

// ---------- 管理员: 邀请码、成员 ----------
function adminRow(box, text, cls) {
  const row = document.createElement("div"); row.className = "arow";
  const t = document.createElement("div"); t.className = "grow"; t.append(text);
  if (cls) t.classList.add(cls);
  row.appendChild(t); box.appendChild(row);
  return row;
}
function miniBtn(row, label, fn) {
  const b = document.createElement("button"); b.className = "mini"; b.textContent = label; b.onclick = fn;
  row.appendChild(b); return b;
}
async function copyText(s) {
  try { await navigator.clipboard.writeText(s); toast("已复制"); }
  catch (e) { toast("没能自动复制，请长按选中后复制"); }   // http 网址下浏览器可能不让写剪贴板
}

async function loadAdmin() {
  let inv, us;
  try { [inv, us] = await Promise.all([api("/api/invites"), api("/api/admin/users")]); }
  catch (e) { return toast(e.message); }
  $("inviteDays").textContent = inv.days;
  const box = $("inviteList"); box.textContent = "";
  for (const i of inv.invites) {
    const row = adminRow(box, "");
    const t = row.firstChild;
    const code = document.createElement("div"); code.className = "code"; code.textContent = i.code;
    const st = document.createElement("div"); st.className = "meta left"; st.style.fontSize = "13px";
    st.textContent = i.status === "used" ? `已被 ${i.used_by || "（已删除的用户）"} 使用`
                   : i.status === "expired" ? "已过期" : `${localDate(i.expires_at).text}前有效`;
    t.append(code, st);
    if (i.status === "unused") {
      miniBtn(row, "复制", () => copyText(i.code));
      miniBtn(row, "作废", async () => {
        if (!confirm(`作废邀请码 ${i.code}？`)) return;
        try { await api("/api/invites/" + i.code, "DELETE"); } catch (e) { return toast(e.message); }
        loadAdmin();
      });
    }
  }
  const ul = $("userList"); ul.textContent = "";
  for (const u of us.users) {
    const row = adminRow(ul, `${u.username}${u.me ? "（我）" : ""} · 已学 ${u.learned}`);
    if (u.me) continue;
    miniBtn(row, "重置密码", async () => {
      if (!confirm(`把 ${u.username} 的密码重置成一个临时密码？他原来的密码会失效。`)) return;
      let r;
      try { r = await api(`/api/admin/users/${u.id}/reset_password`, "POST", {}); } catch (e) { return toast(e.message); }
      const p = document.createElement("div"); p.className = "msg left";
      p.textContent = `${r.username} 的临时密码：${r.password}（请转告他，登录后在“我的”里改密码）`;
      row.after(p);
    });
  }
}
$("btnInvite").onclick = async () => {
  let r;
  try { r = await api("/api/invites", "POST", {}); } catch (e) { return toast(e.message); }
  await loadAdmin();
  copyText(r.code);
};
$("optArticle").checked = needArticle();
$("optArticle").onchange = () => {
  try { localStorage.setItem("sb_needArticle", $("optArticle").checked ? "1" : "0"); } catch (e) {}
};
// 声音设置
$("optAutoWord").checked = getSetting("autoWord");
$("optAutoWord").onchange = () => setSetting("autoWord", $("optAutoWord").checked);
$("optAutoExample").checked = getSetting("autoExample");
$("optAutoExample").onchange = () => setSetting("autoExample", $("optAutoExample").checked);
$("optRate").value = String(getSetting("rate"));
$("optRate").onchange = () => setSetting("rate", parseFloat($("optRate").value));
$("optVoice").onchange = () => setSetting("voice", $("optVoice").value);
$("btnTestVoice").onclick = () => speakDe("Guten Tag! Wie geht es dir? Ich lerne Deutsch.");

function fillVoices() {
  const sel = $("optVoice"); sel.textContent = "";
  const vs = germanVoices();
  for (const v of vs) sel.add(new Option(v.name + (v.localService ? "" : "（联网）"), v.name));
  sel.add(new Option("在线语音（谷歌，需联网）", ONLINE_VOICE));
  if (!vs.length) {
    sel.value = ONLINE_VOICE;
    $("voiceHint").textContent = "设备上没有德语语音，已自动改用在线语音。";
    return;
  }
  const want = getSetting("voice");
  sel.value = want === ONLINE_VOICE || vs.some(v => v.name === want) ? want : vs[0].name;
  $("voiceHint").textContent = `找到 ${vs.length} 个设备上的德语语音，也可以选在线语音，试听后选一个。`;
}
fillVoices();
if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = fillVoices;   // 有的浏览器语音列表是后加载的

$("btnLogout").onclick = async () => {
  try { await api("/api/logout", "POST", {}); } catch (e) {}
  user = null;
  location.replace("#home");
  showLogin();
};
