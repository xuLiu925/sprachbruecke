// 今天(首页)、学习、练习、我的
const BOOK_NAMES = { A1: "A1 入门", A2: "A2 基础", B1: "B1 进阶", B2: "B2 中高级", C1: "C1 高级", all: "全部单词",
                     dsh: "德福 DSH 核心词汇", common: "德语常用词汇", warehouse: "海外仓词汇" };
const BOOK_COVERS = { dsh: "DSH", common: "常用", warehouse: "仓", all: "全部" };
const CHEV_SVG = '<svg class="chev" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>';
const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];

// 列表的一行: 左边图标块(文字或 SVG), 标题和说明, 右边可选的橙色标记和箭头
// tile = {text, cls} 或 {svg, cls}; 旧页面传字符串(emoji)也行
function listItem(tile, title, sub, onclick, off) {
  const b = document.createElement("button");
  b.className = "item" + (off ? " off" : "");
  const i = document.createElement("span");
  if (typeof tile === "string") { i.className = "ico"; i.textContent = tile; }
  else {
    i.className = "tile44 " + (tile.cls || "");
    if (tile.svg) i.innerHTML = tile.svg;   // 只用代码里写死的图标, 不放用户内容
    else i.textContent = tile.text;
  }
  const body = document.createElement("span"); body.className = "body";
  const t = document.createElement("b"); t.textContent = title;
  const s = document.createElement("small"); s.textContent = sub;
  body.append(t, s);
  const badge = document.createElement("span"); badge.className = "badge hidden";
  const chev = document.createElement("span"); chev.className = "chev"; chev.innerHTML = CHEV_SVG;
  b.append(i, body, badge, chev);
  b.onclick = onclick;
  return b;
}
function setBadge(item, text) {
  const b = item.querySelector(".badge");
  b.textContent = text || "";
  b.classList.toggle("hidden", !text);
}

// 打开语法知识点(语法基础里的专项练习也从这里进)
function openTopic(id) {
  gTopic = GRAMMAR_TOPICS.find(t => t.id === id);
  go("gtopic");
}
function openForms(kind, name) {   // 变格 / 变位练习用句子填空的答题页, 题目来自词库
  sPreset = { mode: "cloze", name, url: "/api/forms/" + kind, empty: "词库里还没有这类词的数据。" };
  go("squiz");
}

// 情景课页的“整句复习”按钮: 有到期的句子才显示; 查询失败时不打扰, 保持隐藏(lessons.js 用)
async function showSentenceDue(btn) {
  btn.classList.add("hidden");
  try {
    const { count } = await api("/api/roleplay/due?count=1");
    btn.textContent = `整句复习（${count} 句）`;
    btn.classList.toggle("hidden", !count);
  } catch (e) {}
}

// ---------- 今天 ----------
onShow.home = async () => {
  const now = new Date();
  $("hDate").textContent = `${now.getMonth() + 1} 月 ${now.getDate()} 日 · 周${WEEKDAYS[now.getDay()]}`;
  showMemberWarn();
  const [s, t] = await Promise.all([loadStats(), api("/api/today?" + tzQuery())]);
  $("hStreakN").textContent = t.streak;
  $("hStreak").classList.toggle("off", !t.streak);
  const pct = t.target ? Math.min(t.done / t.target, 1) : 0;
  $("hRingFg").setAttribute("stroke-dasharray", `${(pct * 213.6).toFixed(1)} 214`);
  $("hDone").textContent = t.done;
  $("hTarget").textContent = "/ " + t.target;
  $("hRing").setAttribute("aria-label", `今日进度 ${t.done} / ${t.target}`);
  const left = t.due + t.new;
  $("hPlan").textContent = left ? `还要复习 ${t.due} 个 · 新词 ${t.new} 个` : "今天的任务完成了";
  $("hBook").textContent = "单词书：" + BOOK_NAMES[s.book];
  $("hStart").textContent = !left ? "再学 10 个" : t.done ? "继续今天的学习" : "开始今天的学习";
  $("hStart").onclick = async () => {
    if (!left) { try { await api("/api/today/more?" + tzQuery(), "POST", {}); } catch (e) { return toast(e.message); } }
    go("review");
  };
  showWeek(t.week || []);
  showRecommend();
  showResume();
};

// 接着上次: 最近打开的情景课; 那一课学完了就换成同一组里下一节没学的; 没打开过或整组学完了就不显示
async function showResume() {
  const box = $("hResumeBox");
  let all;
  try { all = await loadLessons(); } catch (e) { return box.classList.add("hidden"); }
  const { last, done } = lessonState;
  let l = all.find(x => x.id === last);
  if (!l) return box.classList.add("hidden");
  const group = all.filter(x => !!x.custom === !!l.custom && (l.custom || x.level === l.level));
  if (done.includes(l.id)) {
    const i = group.indexOf(l);
    l = [...group.slice(i + 1), ...group.slice(0, i)].find(x => !done.includes(x.id));
    if (!l) return box.classList.add("hidden");
  }
  const finished = group.filter(x => done.includes(x.id)).length;
  $("hResumeTag").textContent = l.custom ? "我的情景对话" : "情景课 · " + l.level;
  $("hResumePos").textContent = `第 ${group.indexOf(l) + 1} / ${group.length} 课`;
  $("hResumeTitle").textContent = l.title;
  $("hResumeBar").style.width = (finished / group.length * 100) + "%";
  $("hResume").onclick = () => openLesson(l);
  box.classList.remove("hidden");
}

// 这一周: 7 根柱子, 今天深色
function showWeek(week) {
  const box = $("hWeek"), days = $("hWeekDays");
  box.textContent = ""; days.textContent = "";
  const max = Math.max(...week, 1);
  const today = new Date().getDay();
  week.forEach((n, i) => {
    const bar = document.createElement("i");
    bar.style.height = Math.max(n / max * 100, n ? 8 : 3) + "%";
    if (i === 6) bar.className = "now";
    bar.title = n + " 个词";
    box.appendChild(bar);
    const d = document.createElement("span");
    d.textContent = i === 6 ? "今天" : WEEKDAYS[(today - 6 + i + 7) % 7];
    if (i === 6) d.className = "now";
    days.appendChild(d);
  });
  $("hWeekSum").textContent = week.reduce((a, b) => a + b, 0);
}

// 推荐练习: 有错题或到期的句子才出现; 查询失败就不显示那一项
async function showRecommend() {
  const box = $("hRec");
  const get = url => api(url).catch(() => null);
  const [noun, plural, verb, rp] = await Promise.all([get("/api/grammar/nouns/books"), get("/api/plural/books"),
                                                     get("/api/grammar/verbs/books"), get("/api/roleplay/due?count=1")]);
  box.textContent = "";
  const add = (n, tile, title, sub, fn) => { if (n) box.appendChild(listItem(tile, title, sub, fn)); };
  add(noun && noun.wrong, { text: "die", cls: "die" }, "冠词错题", `${noun && noun.wrong} 个词容易记错冠词，练一组巩固一下`, () => openTopic("art-def"));
  add(plural && plural.wrong, { text: "-en", cls: "das" }, "复数错题", `${plural && plural.wrong} 个词的复数还没记住`, () => go("plural"));
  add(verb && verb.wrong, { text: "-st" }, "动词变位错题", `${verb && verb.wrong} 个动词容易变错`, () => openTopic("verb-praes"));
  add(rp && rp.count, { text: "说" }, "整句复习", `${rp && rp.count} 句情景对话到了复习时间`, () => rpOpen(null));
  $("hRecBox").classList.toggle("hidden", !box.children.length);
}

// ---------- 学习 ----------
onShow.learn = async () => {
  tipOnce("tip_search", "右上角的放大镜随时能查德语或中文，查到的词能直接加进学习（电脑上按 /）。");
  buildGrammarGrid();
  const s = await loadStats();
  $("lBookCover").textContent = BOOK_COVERS[s.book] || s.book;
  $("lBookName").textContent = BOOK_NAMES[s.book];
  $("lBookSub").textContent = s.book_total ? `共 ${s.book_total} 个词` : "";
  const pct = n => s.book_total ? n / s.book_total * 100 : 0;
  $("lBarM").style.width = pct(s.book_mastered) + "%";
  $("lBarL").style.width = pct(Math.max(s.book_learned - s.book_mastered, 0)) + "%";
  const st = $("lBookStats"); st.textContent = "";
  for (const [n, label] of [[s.book_mastered, "已掌握"], [s.book_learned - s.book_mastered, "学习中"],
                            [s.book_total - s.book_learned, "没学"]]) {
    const span = document.createElement("span");
    const b = document.createElement("b"); b.textContent = Math.max(n, 0);
    span.append(b, " " + label);
    st.appendChild(span);
  }
};
// ---------- 选择单词书(学习 → 换一本) ----------
onShow.books = async () => {
  const r = await api("/api/books");
  const box = $("bookList"); box.textContent = "";
  const all = { level: "all", total: null };
  for (const b of [...r.books, ...r.themes, all]) {
    const sub = b.level === "all" ? "整个词库，包括示例词和你自己加的词"
      : b.total ? `${b.total} 个词 · 已学 ${b.learned} · 已掌握 ${b.mastered}` : "还没有导入";
    const it = listItem({ text: BOOK_COVERS[b.level] || b.level }, BOOK_NAMES[b.level], sub, async () => {
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

$("lSearch").onclick = () => openSearch();
$("lBookSwitch").onclick = () => go("books");
$("lWords").onclick = () => go("words");
$("lAdd").onclick = () => go("add");
$("lLessons").onclick = () => go("lessons");
$("lNewLesson").onclick = () => go("lnew");

// 语法知识点按大类显示, 点了进语法基础并跳到那一类
let gJumpGroup = null;
function buildGrammarGrid() {
  const box = $("lGrammar");
  if (box.children.length) return;
  const groups = [];
  for (const t of GRAMMAR_TOPICS) {
    let g = groups.find(x => x.name === t.group);
    if (!g) groups.push(g = { name: t.group, topics: [] });
    g.topics.push(t);
  }
  for (const g of groups) {
    const b = document.createElement("button"); b.className = "gcell";
    const ex = document.createElement("span"); ex.className = "gex"; ex.textContent = GROUP_EXAMPLES[g.name] || "";
    const n = document.createElement("b"); n.textContent = g.name;
    const c = document.createElement("small"); c.textContent = g.topics.length + " 个知识点";
    b.append(ex, n, c);
    b.onclick = () => { gJumpGroup = g.name; go("grammar"); };
    box.appendChild(b);
  }
}
// 每类语法的德语小例子, 当作图标
const GROUP_EXAMPLES = { "冠词": "der die das", "代词": "ich · mich · mir", "介词": "mit · für · in", "动词": "sein · haben",
  "语序": "weil … ist", "问句": "wer · wo · wann", "形容词词尾": "ein guter Tag", "比较级": "gut · besser", "完成时": "hat gemacht",
  "可分动词": "an|rufen", "否定": "nicht · kein", "数字和时间": "halb drei" };

// ---------- 练习 ----------
// 按能力分组; to = 点了做什么, wrong / due = 有错题或到期时显示橙色标记的 key;
// admin = 只有管理员看得到(和别的练习重复, 先不给用户看, 以后决定合并还是去掉)
const PRACTICE_GROUPS = [
  { title: "名词", sub: "冠词 · 复数 · 变格", items: [
    { tile: { text: "die", cls: "die" }, name: "定冠词", sub: "der / die / das 和四个格", to: () => openTopic("art-def"), wrong: "noun" },
    { tile: { text: "ein", cls: "der" }, name: "不定冠词 ein", sub: "ein / eine 的四个格", to: () => openTopic("art-indef") },
    { tile: { text: "kein", cls: "der" }, name: "否定冠词 kein", sub: "kein / keine 的四个格", to: () => openTopic("art-kein") },
    { tile: { text: "mein", cls: "der" }, name: "物主冠词", sub: "mein / dein / sein …", to: () => openTopic("art-poss") },
    { tile: { text: "-en", cls: "das" }, name: "复数", sub: "看规律写复数", to: () => go("plural"), wrong: "plural" },
    { tile: { text: "Akk" }, name: "变格", sub: "四个格的冠词和词尾", to: () => openForms("cases", "变格练习"), admin: true },
    { tile: { text: "?" }, name: "冠词快速选择", sub: "der / die / das 三选一", to: () => go("drill"), admin: true },
  ] },
  { title: "动词", sub: "变位 · 时态 · 搭配", items: [
    { tile: { text: "-st" }, name: "现在时变位", sub: "du kommst, er arbeitet", to: () => openTopic("verb-praes"), wrong: "verb" },
    { tile: { text: "hat" }, name: "完成时", sub: "haben 还是 sein，过去分词", to: () => openTopic("perf-bank"), wrong: "perf" },
    { tile: { text: "auf" }, name: "动词搭配", sub: "warten auf + 第四格", to: () => openTopic("verb-usage"), wrong: "usage" },
    { tile: { text: "ich" }, name: "变位表练习", sub: "不同人称的现在时", to: () => openForms("verbs", "动词变位"), admin: true },
  ] },
  { title: "句子", sub: "用学过的词造句", items: [
    { tile: { text: "__" }, name: "句子练习", sub: "填空、连词成句、中译德、听音填空", to: () => go("sentence"), wrong: "sent" },
  ] },
  { title: "听说", sub: "耳朵和嘴巴", items: [
    { tile: { text: "听" }, name: "听写", sub: "听发音写单词", to: () => go("dictation"), wrong: "dict" },
    // 句子练习的听音填空题型: 直接选好题型进句子练习入口页
    { tile: { text: "句" }, name: "句子听力", sub: "听整句，写出空里的词", to: () => { setSetting("sMode", "listen"); go("sentence"); } },
    { tile: { text: "说" }, name: "整句复习", sub: "情景对话里的句子，限时开口说", to: () => rpOpen(null), due: "rp" },
  ] },
];
const practiceItems = {}, adminRows = [];
(function buildPractice() {
  const box = $("pGroups");
  for (const g of PRACTICE_GROUPS) {
    const head = document.createElement("div"); head.className = "shead";
    const h = document.createElement("h2"); h.textContent = g.title;
    const sub = document.createElement("span"); sub.className = "meta"; sub.textContent = g.sub;
    head.append(h, sub);
    const list = document.createElement("div"); list.className = "list";
    for (const it of g.items) {
      const row = listItem(it.tile, it.name, it.admin ? it.sub + " · 仅管理员可见" : it.sub, it.to);
      if (it.wrong) practiceItems[it.wrong] = row;
      if (it.due) practiceItems[it.due] = row;
      if (it.admin) { row.classList.add("adminonly", "hidden"); adminRows.push(row); }
      list.appendChild(row);
    }
    box.append(head, list);
  }
})();

onShow.practice = async () => {
  adminRows.forEach(r => r.classList.toggle("hidden", !isAdmin));
  const get = url => api(url).catch(() => null);
  const [noun, plural, verb, perf, usage, rp, dict, ...sent] = await Promise.all([
    get("/api/grammar/nouns/books"), get("/api/plural/books"), get("/api/grammar/verbs/books"),
    get("/api/grammar/perfekt/books"), get("/api/grammar/usage/books"), get("/api/roleplay/due?count=1"),
    get("/api/dictation/books"), ...Object.keys(S_MODES).map(m => get(`/api/sentences/${m}/books`))]);
  const w = b => b ? b.wrong : 0;
  const n = { noun: w(noun), plural: w(plural), verb: w(verb) };
  for (const k of ["noun", "plural", "verb"]) setBadge(practiceItems[k], n[k] ? "错题 " + n[k] : "");
  setBadge(practiceItems.perf, w(perf) ? "错题 " + w(perf) : "");
  setBadge(practiceItems.usage, w(usage) ? "错题 " + w(usage) : "");
  setBadge(practiceItems.rp, rp && rp.count ? "到期 " + rp.count : "");
  n.verbAll = n.verb + w(perf) + w(usage);   // 错题本卡片上的“动词” = 现在时 + 完成时 + 搭配
  n.dict = w(dict);
  n.sent = sent.reduce((t, b) => t + w(b), 0);    // 句子练习四种题型加起来
  setBadge(practiceItems.dict, n.dict ? "错题 " + n.dict : "");
  setBadge(practiceItems.sent, n.sent ? "错题 " + n.sent : "");
  n.other = n.dict + n.sent;                      // 错题本卡片上的“其他” = 听写 + 句子
  $("pWrongSum").textContent = n.noun + n.plural + n.verbAll + n.other;
  const box = $("pWrong"); box.textContent = "";
  for (const [k, label] of [["noun", "冠词"], ["plural", "复数"], ["verbAll", "动词"], ["other", "听写·句子"]]) {
    const b = document.createElement("button");
    const num = document.createElement("b"); num.textContent = n[k];
    const t = document.createElement("small"); t.textContent = label;
    b.append(num, t);
    b.onclick = e => { e.stopPropagation(); go("wrong"); };
    box.appendChild(b);
  }
};
$("pWrongCard").onclick = () => go("wrong");

// ---------- 我的 ----------
onShow.me = async () => {
  showProfile();
  showEmail();
  showMember();
  showInstall();
  const s = await loadStats();
  $("meStats").textContent = `已学 ${s.learned} · 已掌握 ${s.mastered}`;
  try { $("optGoal").value = String((await api("/api/today?" + tzQuery())).goal); } catch (e) {}
  $("adminBox").classList.toggle("hidden", !isAdmin);
  if (isAdmin) showAdminEntry();   // admin.js
};

const MEMBER_SOON = 7;   // 「我的」页: 还剩几天起显示倒数
const MEMBER_WARN = 3;   // 首页: 还剩几天起显示续费提醒(到期后 billing.py 的 EXPIRED_SHOW 天内也显示)
const daysLeft = until => Math.max(1, Math.ceil((localDate(until).d - Date.now()) / 86400000));

// 首页的会员提醒: 快到期 / 刚到期时显示, 点“知道了”当天不再显示
async function showMemberWarn() {
  const box = $("hMember");
  let b;
  try { b = await api("/api/billing"); } catch (e) { return; }
  const key = (b.until || b.expired || "") + "@" + new Date().toDateString();
  let closed = false;
  try { closed = localStorage.getItem("sb_memberWarn") === key; } catch (e) {}
  const left = b.until ? daysLeft(b.until) : null;
  const show = !b.admin && !closed && (b.until ? left <= MEMBER_WARN : !!b.expired);
  box.classList.toggle("hidden", !show);
  if (!show) return;
  $("hMemberText").textContent = b.until
    ? `会员还剩 ${left} 天（${localDate(b.until).text}到期）。现在续费会接着往后加。`
    : `会员已在 ${localDate(b.expired).text}到期，现在是免费版，练习每天有次数。`;
  $("hMemberClose").onclick = () => {
    box.classList.add("hidden");
    try { localStorage.setItem("sb_memberWarn", key); } catch (e) {}
  };
}
$("hMemberGo").onclick = () => switchTab("me");

// 会员: 免费版今天用了多少、买月卡 / 年卡(跳到 Stripe 付款页, 付完回来 ?paid=编号)
async function showMember() {
  let b;
  try { b = await api("/api/billing"); } catch (e) { return; }
  const now = $("memberNow"), usage = $("memberUsage"), plans = $("memberPlans");
  usage.textContent = ""; plans.textContent = "";
  const left = b.until ? daysLeft(b.until) : null;
  now.textContent = b.admin ? "管理员：所有功能不限次数。"
    : b.until && left <= MEMBER_SOON ? `会员还剩 ${left} 天（${localDate(b.until).text}到期），到期后回到免费版。现在续费会接着往后加，不会浪费剩下的天数。`
    : b.until ? `会员有效期到 ${localDate(b.until).text}，所有练习不限次数。`
    : (b.expired ? `会员已在 ${localDate(b.expired).text}到期，现在是免费版。` : "") + "免费版：今日学习、词库、查词、语法基础不限；其他练习每天有次数（冠词练习、听写每天 3 组，句子练习每种题型 2 组，语法专项每种 2 组，情景课每天 1 节新课，整句复习每天 1 轮；AI 每天 5 次：打开句子讲解、新生成 AI 查词 / 构词 / 联想记忆；替换练习和 AI 生成对话只给会员）。";
  for (const u of b.usage) {
    const li = document.createElement("li");
    li.textContent = u.split ? `${u.name}：今天做了 ${u.used} 组（每种题型 ${u.limit} 组）` : `${u.name}：今天 ${u.used} / ${u.limit} 组`;
    usage.appendChild(li);
  }
  $("memberNote").classList.toggle("hidden", b.admin);
  if (b.admin) return;
  if (!b.enabled) { plans.textContent = "收款还没开通。"; return; }
  for (const p of b.plans) {
    const btn = document.createElement("button");
    btn.textContent = `${b.until ? "续费" : "开通"}${p.name} ¥${p.price}`;
    if (p.id === "month") btn.className = "secondary";
    btn.onclick = async () => {
      btn.disabled = true;
      try { location.href = (await api("/api/billing/checkout", "POST", checkoutBody(p.id))).url; }
      catch (e) { btn.disabled = false; toast(e.message); }
    };
    plans.appendChild(btn);
  }
  payTip(plans);
}

// 从 Stripe 付款页回来: 核对这笔付款, 再把网址里的编号去掉
async function checkPaid() {
  const sid = new URLSearchParams(location.search).get("paid");
  if (!sid) return;
  history.replaceState(null, "", location.pathname + location.hash);
  try {
    const r = await api("/api/billing/confirm?session_id=" + encodeURIComponent(sid));
    toast(r.paid ? "付款成功，会员已开通！" : "还没收到付款，到账后会自动开通");
  } catch (e) { toast(e.message); }
  if (location.hash === "#me") showMember();
}

// 意见反馈: 所有人都能写; 管理员在下面的列表里看到
$("btnFeedback").onclick = async () => {
  const text = $("fbText").value.trim();
  if (!text) return toast("请先写一下遇到了什么问题");
  try { await api("/api/feedback", "POST", { text }); } catch (e) { return toast(e.message); }
  $("fbText").value = "";
  toast("已提交，谢谢！");
};

// 昵称和通德 ID(user_profile.py): 登录账号(用户名)不能改, 昵称 30 天能改一次
function showProfile() {
  const name = userNick || user || "?";
  $("meName").textContent = name;
  $("avatar").textContent = name.slice(0, 1).toUpperCase();
  $("meId").textContent = userUid ? `通德 ID：${userUid}` : "";
  $("meId").classList.toggle("hidden", !userUid);
  $("nickNow").textContent = `登录账号：${user}（不能改）。昵称 30 天能改一次`
    + (nickWait ? `，还要等 ${nickWait} 天。` : "。");
  $("btnNickToggle").disabled = nickWait > 0;
}
$("meId").onclick = () => copyText(userUid);
$("btnNickToggle").onclick = () => {
  $("nickEdit").classList.toggle("hidden");
  $("nickNew").value = userNick || "";
  $("nickMsg").textContent = "";
};
$("btnNickSave").onclick = async () => {
  const nick = $("nickNew").value.trim();
  if (nick === userNick) { $("nickMsg").textContent = "和现在的昵称一样"; return; }
  if (!confirm(`把昵称改成“${nick}”？改了以后 30 天内不能再改。`)) return;
  try {
    const r = await api("/api/profile/nickname", "POST", { nickname: nick });
    userNick = r.nickname; nickWait = r.nickname_wait;
  } catch (e) { $("nickMsg").textContent = e.message; return; }
  $("nickEdit").classList.add("hidden");
  showProfile();
  toast("昵称已修改");
};

// 绑定 / 更换邮箱: 绑定后能用邮箱登录和找回密码; 要输登录密码(防止别人拿到已登录的手机换掉邮箱)
function showEmail() {
  $("emailNow").textContent = userEmail ? `邮箱：${userEmail}` : "还没有绑定邮箱，忘了密码时没法自己找回。";
  $("btnEmailToggle").textContent = userEmail ? "更换邮箱" : "绑定邮箱";
}
$("btnEmailToggle").onclick = () => { $("emailEdit").classList.toggle("hidden"); $("emailMsg").textContent = ""; };
$("btnEmailCode").onclick = () => sendCode($("btnEmailCode"), "/api/email/code", { email: $("emNew").value }, $("emailMsg"));
$("btnEmailSave").onclick = async () => {
  try {
    userEmail = (await api("/api/email", "POST",
      { email: $("emNew").value, code: $("emCode").value, password: $("emPw").value })).email;
  } catch (e) { $("emailMsg").textContent = e.message; return; }
  ["emNew", "emCode", "emPw"].forEach(id => $(id).value = "");
  $("emailEdit").classList.add("hidden");
  showEmail();
  toast("邮箱已绑定");
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

// ---------- 小工具: 管理后台(admin.js)也用 ----------
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

$("optArticle").checked = needArticle();
$("optArticle").onchange = () => {
  try { localStorage.setItem("sb_needArticle", $("optArticle").checked ? "1" : "0"); } catch (e) {}
};
// 每日学习量存在服务器上, 手机和电脑一样
$("optGoal").onchange = async () => {
  try { await api("/api/today/goal?" + tzQuery(), "POST", { goal: parseInt($("optGoal").value, 10) }); toast("已保存"); }
  catch (e) { toast(e.message); }
};
// 声音设置
$("optAutoWord").checked = getSetting("autoWord");
$("optAutoWord").onchange = () => setSetting("autoWord", $("optAutoWord").checked);
$("optAutoExample").checked = getSetting("autoExample");
$("optAutoExample").onchange = () => setSetting("autoExample", $("optAutoExample").checked);
$("optSpellMode").value = getSetting("spellMode");
$("optSpellMode").onchange = () => setSetting("spellMode", $("optSpellMode").value);
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
  $("voiceHint").textContent = `默认用在线语音。设备上还有 ${vs.length} 个德语语音，不联网也能读，试听后选一个。`;
}
fillVoices();
if ("speechSynthesis" in window) speechSynthesis.onvoiceschanged = fillVoices;   // 有的浏览器语音列表是后加载的

$("btnLogout").onclick = async () => {
  try { await api("/api/logout", "POST", {}); } catch (e) {}
  user = null;
  location.replace("#home");
  showLogin();
};
