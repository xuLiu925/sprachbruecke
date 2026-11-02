// 公共部分: 请求、页面切换、登录、设置
const $ = id => document.getElementById(id);
let user = null;      // 当前用户名
let isAdmin = false;  // 管理员(第一个注册的用户): “我的”页多出邀请码和成员管理
let stats = null;     // 最近一次 /api/stats 的结果

async function api(path, method = "GET", body) {
  const opt = { method, credentials: "same-origin", headers: {} };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  let data = {};
  try { data = await r.json(); } catch (e) {}
  if (r.status === 401 && user) { user = null; showLogin(); }
  if (!r.ok) { const e = new Error(data.error || "请求失败"); e.status = r.status; throw e; }
  return data;
}

async function loadStats() {
  stats = await api("/api/stats");
  return stats;
}

// 表格放进一个能左右滑动的盒子: 表格太宽时在卡片里滑, 不会把整个页面撑出边框
function scrollBox(el) {
  const d = document.createElement("div"); d.className = "tscroll"; d.appendChild(el);
  return d;
}

let toastTimer;
function toast(msg) {
  let t = document.querySelector(".toast");
  if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 1800);
}

// 设置存在本机浏览器里(只是个人偏好, 而且声音跟设备有关), 读写失败就用默认值
function needArticle() {
  try { return localStorage.getItem("sb_needArticle") !== "0"; } catch (e) { return true; }
}
const SETTING_DEFAULTS = { autoWord: true, autoExample: false, rate: 1, voice: "", gHints: false, gScope: "", pHints: false, pScope: "", spellMode: "button", recentSearch: [] };
function getSetting(k) {
  try { const v = localStorage.getItem("sb_" + k); return v === null ? SETTING_DEFAULTS[k] : JSON.parse(v); }
  catch (e) { return SETTING_DEFAULTS[k]; }
}
function setSetting(k, v) {
  try { localStorage.setItem("sb_" + k, JSON.stringify(v)); } catch (e) {}
}

const tzQuery = () => "tz=" + new Date().getTimezoneOffset();   // “今天”按设备的本地日期算

// ---------- 声音: 浏览器自带的语音合成, 用设备上装的德语语音朗读 ----------
function germanVoices() {
  if (!("speechSynthesis" in window)) return [];
  return speechSynthesis.getVoices().filter(v => v.lang.toLowerCase().replace("_", "-").startsWith("de"));
}

// 在线语音: 设备上没有德语语音(或用户选了它)时, 用服务器转来的谷歌发音 /api/tts
const ONLINE_VOICE = "online";
function useOnlineVoice() {
  return getSetting("voice") === ONLINE_VOICE || !germanVoices().length;
}
let ttsAudio = null, ttsQueue = [];
let spellRun = 0, spellOn = false, spellAudio = null;        // 拼读(spell.js); 任何朗读打断时都要停下
function stopSpeak() {
  ttsQueue = [];
  spellRun++; spellOn = false;
  if (spellAudio) spellAudio.pause();
  if (ttsAudio) { ttsAudio.onended = ttsAudio.onerror = null; ttsAudio.pause(); ttsAudio = null; }
  if ("speechSynthesis" in window) speechSynthesis.cancel();
}
function playOnline(text, rate) {
  const a = new Audio("/api/tts?q=" + encodeURIComponent(text.slice(0, 200)));
  ttsAudio = a;
  a.playbackRate = rate;
  const next = () => { if (ttsAudio !== a) return; ttsAudio = null; const n = ttsQueue.shift(); if (n) playOnline(n[0], n[1]); };
  a.onended = next;
  a.onerror = () => { if (ttsAudio === a) speakSystem(text, true, rate); next(); };   // 取不到就退回系统语音
  a.play().catch(() => {});   // 没有点击过页面时浏览器可能不让自动播放
}

function speakDe(text, queue = false, rate = null) {   // queue: 排在正在读的后面, 否则打断; rate: 临时语速
  if (!text) return;
  rate = rate || getSetting("rate");
  if (useOnlineVoice()) {
    if (!queue) stopSpeak();
    if (queue && ttsAudio) ttsQueue.push([text, rate]);
    else playOnline(text, rate);
    return;
  }
  if (!queue) stopSpeak();
  speakSystem(text, queue, rate);
}
function speakSystem(text, queue, rate, onEnd = null) {
  if (!("speechSynthesis" in window)) return onEnd && onEnd();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "de-DE";
  u.rate = rate;
  const vs = germanVoices();
  const v = vs.find(x => x.name === getSetting("voice")) || vs[0];
  if (v) u.voice = v;
  if (onEnd) u.onend = u.onerror = onEnd;
  if (!queue) speechSynthesis.cancel();
  speechSynthesis.speak(u);
  return u;
}
const wordText = w => (w.gender ? w.gender + " " : "") + w.german;   // 名词连冠词一起读

// 显示词性解释和同类词; 不是名词或查询失败时留空。切到下一个词后, 上一个词迟到的结果不显示
// 没有规律的词, 下面可以生成联想记忆(第二层)。meaning 给 AI 参考
async function genderReason(el, german, gender, meaning = "") {
  el.textContent = "";
  el.dataset.word = german || "";
  if (!german || !gender) return;
  let r;
  try { r = await api(`/api/gender_reason?german=${encodeURIComponent(german)}&gender=${gender}`); }
  catch (e) { return; }
  if (el.dataset.word !== german) return;
  const line = document.createElement("div"); line.textContent = "💡 " + r.reason;
  el.appendChild(line);
  if (r.examples.length) {
    const row = document.createElement("div"); row.append("同类词：");
    r.examples.forEach((w, i) => {
      if (i) row.append("、");
      const b = document.createElement("button"); b.className = "tok"; b.textContent = `${w.gender} ${w.german}`;
      b.onclick = () => openWordSheet(w.german, { de: "" });
      row.append(b, `（${w.meaning}）`);
    });
    el.appendChild(row);
  }
  if (r.no_rule) genderMemo(el, german, gender, meaning, r);
}

function genderMemo(el, german, gender, meaning, r) {
  const box = document.createElement("div"); el.appendChild(box);
  const show = memo => {
    box.textContent = "";
    if (memo) {
      const m = document.createElement("div"); m.textContent = "🧠 " + memo;
      const tip = document.createElement("div"); tip.className = "lzh"; tip.textContent = "这是记忆法，不是语法原因";
      box.append(m, tip);
    }
    if (!r.can || !r.ai) return;
    const b = document.createElement("button"); b.className = "mini";
    b.textContent = memo ? "换一个" : "✨ 帮我记住这个词性";
    b.onclick = async () => {
      b.disabled = true; b.textContent = "AI 正在想…";
      try { show((await api("/api/gender_memo", "POST", { german, gender, meaning, again: !!memo })).memo); }
      catch (e) { toast(e.message); show(memo); }
    };
    box.appendChild(b);
  };
  show(r.memo);
}
const exampleDe = ex => (ex || "").split("\n")[0];                  // 例句第一行是德语, 第二行是中文

// ---------- 页面切换 ----------
// 网址里的 #名字 决定显示哪一页; 标签页之间切换不留历史, 进入二级页面才留, 这样「返回」和手机返回键都能用
const PAGES = {
  home:     { title: "通德", tab: true },
  practice: { title: "练习", tab: true },
  words:    { title: "词库", tab: true },
  me:       { title: "我的", tab: true },
  review:   { title: "今日学习", parent: "home" },
  drill:    { title: "冠词练习", parent: "practice" },
  dictation: { title: "听写", parent: "practice" },
  grammar:  { title: "语法基础", parent: "home" },
  gtopic:   { title: "语法", parent: "grammar" },      // 标题在页面里换成知识点名字
  gquiz:    { title: "语法练习", parent: "gtopic" },
  gbank:    { title: "题库", parent: "gtopic" },           // 标题在页面里换成知识点名字
  gnouns:   { title: "单词列表", parent: "gtopic" },       // 标题在页面里换成单词书名字
  lessons:  { title: "情景课", parent: "home" },
  lesson:   { title: "情景课", parent: "lessons" },       // 标题在页面里换成课名
  lnew:     { title: "新建工作对话", parent: "lessons" },
  roleplay: { title: "角色扮演", parent: "lessons" },     // 标题在页面里换(整句复习用同一页)
  sentence: { title: "句子练习", parent: "home" },
  squiz:    { title: "句子练习", parent: "sentence" },     // 标题在页面里换成题型名字
  plural:   { title: "复数练习", parent: "practice" },
  add:      { title: "添加单词", parent: "words" },
  view:     { title: "单词详情", parent: "words" },
  edit:     { title: "编辑单词", parent: "words", section: "add" },   // 和添加单词共用一个界面
  import:   { title: "批量导入", parent: "words" },
  books:    { title: "选择单词书", parent: "home" },
};
const onShow = {};    // 各页面注册: 进入该页时执行
let current = null, pushed = false;

function go(name) { pushed = true; location.hash = name; }
function switchTab(name) { location.replace("#" + name); }

function route() {
  if (!user) return;
  let name = location.hash.slice(1);
  if (!PAGES[name]) name = "home";
  const p = PAGES[name];
  const sec = p.section || name;
  document.querySelectorAll(".page").forEach(s => s.classList.toggle("hidden", s.dataset.page !== sec));
  $("title").textContent = p.title;
  $("btnBack").classList.toggle("hidden", !!p.tab);
  $("tabbar").classList.toggle("hidden", !p.tab);
  document.body.classList.toggle("no-tabs", !p.tab);
  document.querySelectorAll("#tabbar button").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  window.scrollTo(0, 0);
  current = name;
  if (onShow[name]) onShow[name]();
}
window.addEventListener("hashchange", route);

$("btnBack").onclick = () => {
  if (pushed) history.back();
  else switchTab(PAGES[current].parent || "home");
};
document.querySelectorAll("#tabbar button").forEach(b => b.onclick = () => switchTab(b.dataset.tab));

// ---------- 键盘快捷键(电脑上用) ----------
// 各页面注册 onKey.页面名 = (e, typing) => 处理了返回 true; typing = 焦点在输入框里
const onKey = {};
document.addEventListener("keydown", e => {
  if (!user || e.isComposing || e.altKey || e.metaKey) return;   // 输入法选字时不算
  if (!$("wsheet").classList.contains("hidden")) {               // 单词卡打开时, 快捷键别影响下面的页面(比如误触评分)
    if (e.key === "Escape") { e.preventDefault(); closeWordSheet(); }
    else if (e.key === "Backspace" && wsStack.length) { e.preventDefault(); wsBack(); }
    return;
  }
  if (searchIsOpen()) {                                          // 搜索层打开时同样不影响下面的页面
    if (e.key === "Escape") { e.preventDefault(); closeSearch(); }
    return;
  }
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
  if (e.key === "/" && !typing && !e.ctrlKey) { e.preventDefault(); openSearch(); return; }
  if (e.key === "Escape") {
    if (typing) e.target.blur();                                  // 输入框里按 Esc 只是退出输入
    else if (!$("btnBack").classList.contains("hidden")) { e.preventDefault(); $("btnBack").click(); }
    return;
  }
  const h = onKey[current];
  if (h && h(e, typing)) e.preventDefault();
});

// ä ö ü ß 按钮: 插到 data-for 指定的输入框的光标处
document.querySelectorAll(".umlauts button").forEach(b => b.onclick = () => {
  const i = $(b.parentElement.dataset.for), s = i.selectionStart ?? i.value.length, t = i.selectionEnd ?? s;
  i.value = i.value.slice(0, s) + b.dataset.ch + i.value.slice(t);
  i.focus(); i.setSelectionRange(s + 1, s + 1);
});

// ---------- 登录 ----------
function showLogin() {
  $("app").classList.add("hidden");
  $("login").classList.remove("hidden");
  authView("login");
}

function showApp() {
  $("login").classList.add("hidden");
  $("app").classList.remove("hidden");
  route();
}

let registerMode = "invite";   // 后端的注册方式: email(邮箱验证码) / invite(邀请码) / open
let userEmail = null;

async function boot() {
  try {
    const me = await api("/api/me");
    user = me.username; isAdmin = !!me.admin; userEmail = me.email || null;
    if (me.register) registerMode = me.register;
  } catch (e) { user = null; }
  if (user) showApp(); else showLogin();
}

// 登录页的三块: login / reg / forgot
function authView(name) {
  $("authLogin").classList.toggle("hidden", name !== "login");
  $("authReg").classList.toggle("hidden", name !== "reg");
  $("authForgot").classList.toggle("hidden", name !== "forgot");
  $("regEmail").classList.toggle("hidden", registerMode !== "email");
  $("inv").classList.toggle("hidden", registerMode !== "invite");
  $("authMsg").textContent = "";
}
document.querySelectorAll("#login [data-auth]").forEach(b => b.onclick = () => authView(b.dataset.auth));

function loggedIn(r) {
  ["p", "rp", "fp", "inv", "rc", "fc"].forEach(id => $(id).value = "");
  user = r.username; isAdmin = !!r.admin;
  boot();   // 重新取一次 me(带邮箱)
}

async function doAuth(path, body) {
  $("authMsg").textContent = "";
  try { loggedIn(await api(path, "POST", body)); } catch (e) { $("authMsg").textContent = e.message; }
}

// 发验证码的按钮: 发出后 60 秒内不能再点
async function sendCode(btn, path, body, msgBox) {
  msgBox.textContent = "";
  btn.disabled = true;
  try { await api(path, "POST", body); }
  catch (e) { msgBox.textContent = e.message; btn.disabled = false; return; }
  toast("验证码已发送，请查看邮箱");
  const label = btn.textContent;
  let left = 60;
  const tick = () => {
    if (left <= 0) { btn.disabled = false; btn.textContent = label; return; }
    btn.textContent = `${left--} 秒`; setTimeout(tick, 1000);
  };
  tick();
}

$("btnLogin").onclick = () => doAuth("/api/login", { username: $("u").value, password: $("p").value });
$("p").onkeydown = e => { if (e.key === "Enter") $("btnLogin").click(); };
$("btnRegCode").onclick = () => sendCode($("btnRegCode"), "/api/register/code",
  { username: $("ru").value, email: $("re").value }, $("authMsg"));
$("btnReg").onclick = () => doAuth("/api/register", { username: $("ru").value, password: $("rp").value,
  email: $("re").value, code: $("rc").value, invite: $("inv").value });
$("btnForgotCode").onclick = () => sendCode($("btnForgotCode"), "/api/password/forgot", { email: $("fe").value }, $("authMsg"));
$("btnForgot").onclick = () => doAuth("/api/password/reset", { email: $("fe").value, code: $("fc").value, new: $("fp").value });
