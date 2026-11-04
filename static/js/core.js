// 公共部分: 请求、页面切换、登录、设置
const $ = id => document.getElementById(id);
// 线条图标(代码里写死, 用 innerHTML 放进按钮); 发音按钮都用这个喇叭
const ICON_SPEAK = '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>';
function iconButton(cls, label, text = "") {   // 图标按钮: text 为空时只有图标, label 给读屏软件
  const b = document.createElement("button"); b.className = cls;
  b.innerHTML = ICON_SPEAK; if (text) b.append(text);
  b.setAttribute("aria-label", label); b.title = label;
  return b;
}
let user = null;      // 当前用户名
let isAdmin = false;  // 管理员(第一个注册的用户): “我的”页多出邀请码和成员管理
let stats = null;     // 最近一次 /api/stats 的结果

async function api(path, method = "GET", body) {
  // X-TZ: 免费次数按本地日期算(billing.py)
  const opt = { method, credentials: "same-origin", headers: { "X-TZ": String(new Date().getTimezoneOffset()) } };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  let data = {};
  try { data = await r.json(); } catch (e) {}
  if (r.status === 401 && user) { user = null; showLogin(); }
  else if (r.status === 401 && method !== "GET" && !/^\/api\/(login|register|password)/.test(path))
    openLogin("reg", "注册后就能使用这个功能");   // 游客点了要账号的操作(加入学习、报错等)
  if (r.status === 402 && data.paywall) showPaywall(data.error, data.title);
  if (!r.ok) { const e = new Error(data.error || "请求失败"); e.status = r.status; throw e; }
  return data;
}

// ---------- 免费次数用完: 底部弹窗, 直接选月卡 / 年卡去付款 ----------
// 关掉(明天再来、×、点外面、Esc)时如果在二级页面就退回上一页, 免得留在没有题的空页面
const payOpen = () => !$("paysheet").classList.contains("hidden");
async function showPaywall(msg, title) {
  $("payMsg").textContent = msg;
  $("payTitle").textContent = title || "今天的免费次数用完了";
  if (payOpen()) return;
  $("paysheet").classList.remove("hidden");
  const box = $("payPlans");
  box.textContent = "";
  let b;
  try { b = await api("/api/billing"); } catch (e) { return; }
  if (!b.enabled) { box.textContent = "收款还没开通。"; return; }
  for (const p of b.plans.slice().sort((x, y) => (y.id === "year") - (x.id === "year"))) {   // 年卡在上
    const btn = document.createElement("button");
    if (p.id !== "year") btn.className = "secondary";
    btn.textContent = `开通${p.name} ¥${p.price}`;
    if (p.id === "year") {
      const note = document.createElement("span");
      note.className = "paynote";
      note.textContent = `约 ¥${(p.price / 12).toFixed(1)} / 月，一次付清，不自动续费`;
      btn.appendChild(note);
    }
    btn.onclick = async () => {
      btn.disabled = true;
      try { location.href = (await api("/api/billing/checkout", "POST", { plan: p.id })).url; }
      catch (e) { btn.disabled = false; toast(e.message); }
    };
    box.appendChild(btn);
  }
}
function closePaywall(back = true) {
  if (!payOpen()) return;
  $("paysheet").classList.add("hidden");
  if (back && current && !PAGES[current].tab) $("btnBack").click();
}
$("payClose").onclick = () => closePaywall();
$("payLater").onclick = () => closePaywall();
$("payMore").onclick = () => { closePaywall(false); switchTab("me"); };
$("paysheet").onclick = e => { if (e.target === $("paysheet")) closePaywall(); };

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
// voice 默认在线语音(谷歌, 发音统一、国产手机常没有德语语音); 自己在「我的」页选过设备语音的不变
const SETTING_DEFAULTS = { autoWord: true, autoExample: false, rate: 1, voice: "online", gHints: false, gScope: "", pHints: false, pScope: "", spellMode: "button", recentSearch: [] };
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
  const line = document.createElement("div"); line.textContent = r.reason;
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
      const m = document.createElement("div"); m.textContent = "记忆法：" + memo;
      const tip = document.createElement("div"); tip.className = "lzh"; tip.textContent = "这是记忆法，不是语法原因";
      box.append(m, tip);
    }
    if (!r.ai || !(memo ? r.can : r.gen)) return;   // 换一个只有管理员能用
    const b = document.createElement("button"); b.className = "mini";
    b.textContent = memo ? "换一个" : "AI 帮我记住这个词性";
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
  home:     { title: "今天", tab: true },
  learn:    { title: "学习", tab: true },
  practice: { title: "练习", tab: true },
  me:       { title: "我的", tab: true },
  words:    { title: "全部单词", parent: "learn" },
  review:   { title: "今日学习", parent: "home" },
  drill:    { title: "冠词练习", parent: "practice" },
  dictation: { title: "听写", parent: "practice" },
  grammar:  { title: "语法基础", parent: "learn" },
  gtopic:   { title: "语法", parent: "grammar" },      // 标题在页面里换成知识点名字
  gquiz:    { title: "语法练习", parent: "gtopic" },
  gbank:    { title: "题库", parent: "gtopic" },           // 标题在页面里换成知识点名字
  gnouns:   { title: "单词列表", parent: "gtopic" },       // 标题在页面里换成单词书名字
  lessons:  { title: "情景课", parent: "learn" },
  lesson:   { title: "情景课", parent: "lessons" },       // 标题在页面里换成课名
  lnew:     { title: "新建工作对话", parent: "lessons" },
  roleplay: { title: "角色扮演", parent: "lessons" },     // 标题在页面里换(整句复习用同一页)
  sentence: { title: "句子练习", parent: "practice" },
  squiz:    { title: "句子练习", parent: "sentence" },     // 标题在页面里换成题型名字
  plural:   { title: "复数练习", parent: "practice" },
  add:      { title: "添加单词", parent: "words" },
  view:     { title: "单词详情", parent: "words" },
  edit:     { title: "编辑单词", parent: "words", section: "add" },   // 和添加单词共用一个界面
  import:   { title: "批量导入", parent: "words" },
  books:    { title: "选择单词书", parent: "learn" },
  welcome:  { title: "通德" },
  wrong:    { title: "错题本", parent: "practice" },                             // 游客首页
};
// 没登录也能看的页面(游客的 home 换成 welcome); 其他页面要先登录。试学在 review.js
const GUEST_PAGES = ["welcome", "review", "grammar", "gtopic", "gquiz"];
const onShow = {};    // 各页面注册: 进入该页时执行
let current = null, pushed = false;

function go(name) { pushed = true; location.hash = name; }
function switchTab(name) { location.replace("#" + name); }

function route() {
  let name = location.hash.slice(1);
  if (!PAGES[name]) name = "home";
  if (!user) {
    if (name === "home") name = "welcome";
    else if (!GUEST_PAGES.includes(name)) { location.replace("#welcome"); openLogin("reg", "注册后就能使用这个功能"); return; }
  } else if (name === "welcome") name = "home";
  const p = PAGES[name];
  const sec = p.section || name;
  document.querySelectorAll(".page").forEach(s => s.classList.toggle("hidden", s.dataset.page !== sec));
  $("title").textContent = p.title;
  const tabs = !!p.tab && !!user;
  $("btnBack").classList.toggle("hidden", !!p.tab || name === "welcome");
  $("tabbar").classList.toggle("hidden", !tabs);
  document.body.classList.toggle("no-tabs", !tabs);
  document.body.classList.toggle("tabpage", !!p.tab || name === "welcome");   // 标签页: 页面里有大标题, 顶栏不显示标题
  searchRefresh();   // 游客不显示搜索(search.js)
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
  if (!$("login").classList.contains("hidden") || e.isComposing || e.altKey || e.metaKey) return;   // 输入法选字时不算
  if (payOpen()) {                                               // 会员弹窗打开时只认 Esc
    if (e.key === "Escape") { e.preventDefault(); closePaywall(); }
    return;
  }
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
function showLogin() { openLogin("login"); }

// 登录 / 注册页盖在应用上面; 没登录时左上角“先随便看看”回到游客页面。why = 为什么要登录(可选)
function openLogin(view = "login", why = "") {
  stopSpeak();
  $("app").classList.add("hidden");
  $("login").classList.remove("hidden");
  $("loginWhy").textContent = why;
  authView(view);
  window.scrollTo(0, 0);
}
$("loginClose").onclick = () => {   // 回到刚才那一页, 不重新加载(试学做到一半不会从头开始)
  $("login").classList.add("hidden");
  $("app").classList.remove("hidden");
  if (!current) route();
};

function showApp() {
  $("login").classList.add("hidden");
  $("app").classList.remove("hidden");
  route();
}

// 游客首页的按钮
$("wTrial").onclick = () => go("review");
$("wGrammar").onclick = () => go("grammar");
$("wLogin").onclick = () => openLogin("login");
$("wReg").onclick = () => openLogin("reg");

// 试学的评分存在本机(review.js 的 TRIAL_KEY), 登录或注册后交给服务器记进进度
async function saveTrial() {
  let answers = null;
  try { answers = JSON.parse(localStorage.getItem(TRIAL_KEY) || "null"); } catch (e) {}
  if (!Array.isArray(answers) || !answers.length) return;
  try {
    const r = await api("/api/trial/save", "POST", { answers });
    try { localStorage.removeItem(TRIAL_KEY); } catch (e) {}
    if (r.saved) { toast(`试学的 ${r.saved} 个词已保存到你的进度`); route(); }   // 刷新首页的数字
  } catch (e) {}   // 没保存成功就留着, 下次登录再试
}

let registerMode = "invite";   // 后端的注册方式: email(邮箱验证码) / invite(邀请码) / open
let userEmail = null;
// 管理员发的邀请链接 ?invite=码: 注册页显示填好的邀请码, 不用邮箱。平时注册页看不到邀请码
let inviteLink = new URLSearchParams(location.search).get("invite") || "";
if (inviteLink) history.replaceState(null, "", location.pathname + location.hash);

async function boot() {
  try {
    const me = await api("/api/me");
    user = me.username; isAdmin = !!me.admin; userEmail = me.email || null;
    if (me.register) registerMode = me.register;
  } catch (e) { user = null; }
  showApp();   // 没登录时是游客页面(route 里换成 welcome)
  if (user) checkPaid();
  installGate();
  showInstall();   // 游客首页 / 「我的」页的安装卡片
  if (inviteLink) {
    if (user) toast("你已经登录了；要用邀请链接注册新账号，先退出");
    else openLogin("reg");
  }
}

// PWA: 注册 Service Worker(断网时还能打开页面), 记下浏览器给的“安装”机会
let installEvent = null;
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); installEvent = e; showInstall(); installGate(); });
window.addEventListener("appinstalled", () => { installEvent = null; installed = true; showInstall(); installGate(); });
let installed = false;

// 安装引导整页: 网址带 ?install 一定显示; 否则已登录、手机浏览器打开、还没装、这次没点过“先在网页里用”时显示
const IS_STANDALONE = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
let gateForced = new URLSearchParams(location.search).has("install");
function gateWanted() {
  if (IS_STANDALONE) return false;
  if (gateForced) return true;
  let skipped = false;
  try { skipped = sessionStorage.getItem("sb_gateSkip") === "1"; } catch (e) {}
  return !skipped && !!user && matchMedia("(pointer: coarse)").matches;   // 游客先试用, 登录后才自动提示安装
}
function installGate() {
  const gate = $("gate");
  if (!gateWanted()) { gate.classList.add("hidden"); return; }
  gate.classList.remove("hidden");
  const ua = navigator.userAgent;
  const inApp = /MicroMessenger|QQ\/|Weibo|DingTalk|AlipayClient/i.test(ua);
  const ios = /iPhone|iPad|iPod/.test(ua) || (ua.includes("Macintosh") && navigator.maxTouchPoints > 1);
  const iosOther = ios && /CriOS|FxiOS|EdgiOS|OPiOS/.test(ua);
  const steps = $("gateSteps");
  steps.innerHTML = "";
  const add = (title, items) => {
    const b = document.createElement("b"); b.textContent = title; steps.appendChild(b);
    if (!items) return;
    const ol = document.createElement("ol");
    for (const t of items) { const li = document.createElement("li"); li.textContent = t; ol.appendChild(li); }
    steps.appendChild(ol);
  };
  let copy = false;
  if (installed) add("已经装好了！回到手机桌面，点“通德”图标打开。");
  else if (installEvent) { /* 只显示按钮 */ }
  else if (inApp) { add("这里装不了，请换到浏览器打开：", ["点右上角“···”", "选“在浏览器打开”", "在浏览器里点“安装到桌面”"]); copy = true; }
  else if (iosOther) { add("苹果手机只能用 Safari 安装：", ["点下面“复制链接”", "打开 Safari，粘贴到地址栏打开", "点底部“分享”按钮，选“添加到主屏幕”"]); copy = true; }
  else if (ios) add("三步装到桌面：", ["点屏幕底部的“分享”按钮（方框加向上箭头）", "往下找，选“添加到主屏幕”", "点右上角“添加”"]);
  else { add("从浏览器菜单安装：", ["点右上角“⋮”或底部“≡”菜单", "选“安装应用”或“添加到主屏幕”", "找不到这一项：复制链接，用 Chrome 或 Edge 打开"]); copy = true; }
  $("gateBtn").classList.toggle("hidden", !installEvent || installed);
  $("gateCopy").classList.toggle("hidden", !copy || installed);
  $("gateArrow").classList.toggle("hidden", !inApp || installed);
}
$("gateBtn").onclick = async () => {
  if (!installEvent) return;
  installEvent.prompt();
  const { outcome } = await installEvent.userChoice;
  if (outcome === "accepted") { installEvent = null; installed = true; }
  installGate();
  showInstall();   // 装好了就藏起安装卡片
};
$("gateCopy").onclick = async () => {
  const link = location.origin + "/?install";
  try { await navigator.clipboard.writeText(link); toast("已复制链接"); }
  catch (e) { prompt("长按复制这个链接：", link); }
};
$("gateSkip").onclick = () => {
  try { sessionStorage.setItem("sb_gateSkip", "1"); } catch (e) {}
  if (gateForced) {
    gateForced = false;
    const u = new URL(location.href); u.searchParams.delete("install");
    history.replaceState(null, "", u.pathname + u.search + u.hash);
  }
  $("gate").classList.add("hidden");
};
installGate();

// 游客首页的“装到手机桌面”卡片: 浏览器给了安装许可就直接安装, 否则打开安装引导整页看步骤
$("wInstall").onclick = async () => {
  if (installEvent) {
    installEvent.prompt();
    const { outcome } = await installEvent.userChoice;
    if (outcome === "accepted") { installEvent = null; installed = true; toast("已添加到桌面"); }
    return showInstall();
  }
  gateForced = true;
  installGate();
};

function showInstall() {
  const box = $("installBox");
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  $("wInstallBox").classList.toggle("hidden", !!standalone || installed);
  $("wInstall").textContent = installEvent ? "安装到桌面" : "看看怎么装";
  const ua = navigator.userAgent;
  const ios = /iPhone|iPad|iPod/.test(ua) || (ua.includes("Macintosh") && navigator.maxTouchPoints > 1);
  box.classList.toggle("hidden", !!standalone || !matchMedia("(pointer: coarse)").matches && !installEvent);
  $("btnInstall").classList.toggle("hidden", !installEvent);
  $("installTip").textContent =
    installEvent ? "装好后桌面上有“通德”图标，点开全屏使用，和普通 App 一样。"
    : /MicroMessenger|QQ\//.test(ua) ? "微信、QQ 里打不开安装：点右上角“…”，选“在浏览器打开”，再到这里安装。"
    : ios ? "用 Safari 打开本页，点底部的“分享”按钮，再选“添加到主屏幕”。"
    : "点浏览器菜单（右上角“⋮”或底部“≡”），选“添加到主屏幕”或“安装应用”。";
}
$("btnInstall").onclick = async () => {
  if (!installEvent) return;
  installEvent.prompt();
  const { outcome } = await installEvent.userChoice;
  if (outcome === "accepted") { installEvent = null; toast("已添加到桌面"); }
  showInstall();
};

// 登录页的三块: login / reg / forgot
function authView(name) {
  $("authLogin").classList.toggle("hidden", name !== "login");
  $("authReg").classList.toggle("hidden", name !== "reg");
  $("authForgot").classList.toggle("hidden", name !== "forgot");
  const byInvite = registerMode === "invite" || (registerMode === "email" && !!inviteLink);
  $("regEmail").classList.toggle("hidden", registerMode !== "email" || byInvite);
  $("inv").classList.toggle("hidden", !byInvite);
  if (inviteLink && !$("inv").value) $("inv").value = inviteLink;
  $("authMsg").textContent = "";
}
document.querySelectorAll("#login [data-auth]").forEach(b => b.onclick = () => authView(b.dataset.auth));

function loggedIn(r) {
  ["p", "rp", "fp", "inv", "rc", "fc"].forEach(id => $(id).value = "");
  inviteLink = "";
  user = r.username; isAdmin = !!r.admin;
  if (!location.hash || location.hash === "#welcome" || location.hash === "#review") location.replace("#home");
  boot().then(saveTrial);   // 重新取一次 me(带邮箱); 有试学记录就存进进度
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
