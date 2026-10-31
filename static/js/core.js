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
const SETTING_DEFAULTS = { autoWord: true, autoExample: false, rate: 1, voice: "" };
function getSetting(k) {
  try { const v = localStorage.getItem("sb_" + k); return v === null ? SETTING_DEFAULTS[k] : JSON.parse(v); }
  catch (e) { return SETTING_DEFAULTS[k]; }
}
function setSetting(k, v) {
  try { localStorage.setItem("sb_" + k, JSON.stringify(v)); } catch (e) {}
}

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
function stopSpeak() {
  ttsQueue = [];
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
function speakSystem(text, queue, rate) {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "de-DE";
  u.rate = rate;
  const vs = germanVoices();
  const v = vs.find(x => x.name === getSetting("voice")) || vs[0];
  if (v) u.voice = v;
  if (!queue) speechSynthesis.cancel();
  speechSynthesis.speak(u);
}
const wordText = w => (w.gender ? w.gender + " " : "") + w.german;   // 名词连冠词一起读
const exampleDe = ex => (ex || "").split("\n")[0];                  // 例句第一行是德语, 第二行是中文

// ---------- 页面切换 ----------
// 网址里的 #名字 决定显示哪一页; 标签页之间切换不留历史, 进入二级页面才留, 这样「返回」和手机返回键都能用
const PAGES = {
  home:     { title: "通德", tab: true },
  practice: { title: "练习", tab: true },
  words:    { title: "词库", tab: true },
  me:       { title: "我的", tab: true },
  review:   { title: "今日复习", parent: "home" },
  drill:    { title: "冠词练习", parent: "practice" },
  dictation: { title: "听写", parent: "practice" },
  grammar:  { title: "语法基础", parent: "home" },
  gtopic:   { title: "语法", parent: "grammar" },      // 标题在页面里换成知识点名字
  gquiz:    { title: "语法练习", parent: "gtopic" },
  lessons:  { title: "情景课", parent: "home" },
  lesson:   { title: "情景课", parent: "lessons" },       // 标题在页面里换成课名
  lnew:     { title: "新建工作对话", parent: "lessons" },
  roleplay: { title: "角色扮演", parent: "lessons" },     // 标题在页面里换(整句复习用同一页)
  sentence: { title: "句子练习", parent: "home" },
  squiz:    { title: "句子练习", parent: "sentence" },     // 标题在页面里换成题型名字
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
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
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
}

function showApp() {
  $("login").classList.add("hidden");
  $("app").classList.remove("hidden");
  route();
}

async function boot() {
  try {
    const me = await api("/api/me");
    user = me.username; isAdmin = !!me.admin;
  } catch (e) { user = null; }
  if (user) showApp(); else showLogin();
}

async function doAuth(kind) {
  $("authMsg").textContent = "";
  try {
    const body = { username: $("u").value, password: $("p").value };
    if (kind === "register") body.invite = $("inv").value;
    const r = await api("/api/" + kind, "POST", body);
    $("p").value = ""; $("inv").value = "";
    user = r.username; isAdmin = !!r.admin;
    showApp();
  } catch (e) { $("authMsg").textContent = e.message; }
}
$("btnLogin").onclick = () => doAuth("login");
$("btnReg").onclick = () => doAuth("register");
$("p").onkeydown = e => { if (e.key === "Enter") doAuth("login"); };
