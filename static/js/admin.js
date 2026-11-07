// 管理后台(只有管理员): 概览、用户、内容。后端 admin.py, 文档 docs/features/admin.md
// 入口在「我的」页; 反馈、待审核、邀请码的接口没变, 只是从「我的」页挪到这里

function showAdminEntry() {
  const box = $("adminEntry"); box.textContent = "";
  box.appendChild(listItem({ text: "管" }, "管理后台", "用户、会员、反馈和报错、待审核单词、邀请码", () => go("admin")));
}

// 相对时间: 刚才 / 3 小时前 / 5 天前 / 具体日期
function admAgo(s) {
  if (!s) return "没有记录";
  const min = (Date.now() - localDate(s).d) / 60000;
  if (min < 60) return "1 小时内";
  if (min < 1440) return `${Math.floor(min / 60)} 小时前`;
  if (min < 1440 * 30) return `${Math.floor(min / 1440)} 天前`;
  return localDate(s).text;
}
const admFullDate = s => s ? (d => `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`)(localDate(s).d) : "-";
const admMoney = (cents, cur) => (cur === "cny" ? "¥" : (cur || "").toUpperCase() + " ") + (cents / 100).toFixed(cents % 100 ? 2 : 0);
const admName = u => u.nickname && u.nickname !== u.username ? `${u.nickname}（${u.username}）` : u.username;

// ---------- 标签 ----------
let admTab = "overview";
function admShowTab(tab) {
  admTab = tab;
  $("admTabs").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
  document.querySelectorAll("[data-page=admin] [data-pane]").forEach(p => p.classList.toggle("hidden", p.dataset.pane !== tab));
  if (tab === "overview") admLoadOverview();
  else if (tab === "users") admLoadUsers();
  else { loadReports(); loadPending(); loadInvites(); admShowBanks(); }
}
// 有后端手写题库的知识点(目前只有定冠词): 进原来的题库页(gbank.js)
function admShowBanks() {
  const box = $("admBanks"); box.textContent = "";
  for (const t of GRAMMAR_TOPICS.filter(t => t.adminBank)) {
    box.appendChild(listItem({ text: "题" }, t.title, "手写题和 AI 出题、停用、报错", () => { gTopic = t; go("gbank"); }));
  }
}
$("admTabs").querySelectorAll("button").forEach(b => b.onclick = () => admShowTab(b.dataset.tab));

onShow.admin = () => {
  if (!isAdmin) return location.replace("#me");
  $("userFind").value = "";   // 每次打开都清空: 浏览器万一自动填了用户名, 也不会只剩自己
  admShowTab(admTab);
};

// ---------- 概览 ----------
async function admLoadOverview() {
  let r;
  try { r = await api("/api/admin/overview?" + tzQuery()); } catch (e) { return toast(e.message); }
  const box = $("admOverview"); box.textContent = "";
  const money = r.payments.month.map(p => admMoney(p.total, p.currency)).join(" + ") || "0";
  const groups = [
    ["用户", [[r.users.total, "注册用户", () => admGoUsers("")], [r.users.new_7d, "7 天新注册"],
              [r.users.active_1d, "24 小时活跃"], [r.users.active_7d, "7 天活跃"]]],
    ["会员和付款", [[r.members.active, "会员", () => admGoUsers("member")], [r.members.expiring_7d, "7 天内到期"],
                   [r.payments.today, "24 小时付款"], [money, "30 天收入"]]],
    ["待处理", [[r.todo.feedback, "意见反馈", () => admShowTab("content")], [r.todo.reports, "内容报错", () => admShowTab("content")],
               [r.todo.pending, "待审核单词", () => admShowTab("content")], [r.users.banned, "已停用账号", () => admGoUsers("banned")]]],
    ["今天", [[r.today.reviews, "复习次数"], [r.today.learners, "复习的人"],
             [r.today.ai_generated, "AI 新生成"], [r.today.ai_free, "免费用户 AI 次数"]]],
  ];
  for (const [title, tiles] of groups) {
    const h = document.createElement("h2"); h.className = "glabel"; h.textContent = title;
    const grid = document.createElement("div"); grid.className = "admgrid";
    for (const [num, label, fn] of tiles) {
      const b = document.createElement(fn ? "button" : "div");
      const n = document.createElement("b"); n.textContent = num;
      const t = document.createElement("small"); t.textContent = label;
      b.append(n, t);
      if (fn) b.onclick = fn;
      grid.appendChild(b);
    }
    box.append(h, grid);
  }
}

// ---------- 用户 ----------
let admFilter = "", admUsers = [], admSearchTimer = null;
function admGoUsers(filter) { admFilter = filter; $("userFind").value = ""; admShowTab("users"); }

async function admLoadUsers(more) {
  const offset = more ? admUsers.length : 0;
  const q = $("userFind").value.trim();
  $("userFilter").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.f === admFilter));
  let r;
  try {
    r = await api(`/api/admin/users?q=${encodeURIComponent(q)}&filter=${admFilter}&offset=${offset}`);
  } catch (e) { return toast(e.message); }
  if (q !== $("userFind").value.trim()) return;   // 输入又变了, 等下一次结果
  admUsers = more ? admUsers.concat(r.users) : r.users;
  const ul = $("userList");
  if (!more) ul.textContent = "";
  for (const u of r.users) admUserRow(ul, u);
  $("userMore").classList.toggle("hidden", !r.more);
  $("userCount").textContent = q || admFilter
    ? `找到 ${admUsers.length}${r.more ? "+" : ""} 个 / 共 ${r.total} 个用户`
    : `共 ${r.total} 个用户，新注册的在前`;
  if (!admUsers.length) ul.textContent = "没有找到";
}

function admUserRow(box, u) {
  const row = adminRow(box, "");
  row.classList.add("clickable");
  const t = row.firstChild;
  const head = document.createElement("div");
  const name = document.createElement("b"); name.textContent = admName(u) + (u.me ? "（我）" : "");
  head.appendChild(name);
  for (const [show, text, cls] of [[u.admin, "管理员", "learning"], [u.member_until, "会员", "mastered"], [u.banned, "已停用", "weak"]]) {
    if (!show) continue;
    const c = document.createElement("span"); c.className = "chip " + cls; c.textContent = text; c.style.marginLeft = "6px";
    head.appendChild(c);
  }
  const meta = document.createElement("div"); meta.className = "meta left"; meta.style.fontSize = "13px";
  meta.textContent = [`ID ${u.uid || "-"}`, `已学 ${u.learned}`, `最近使用：${admAgo(u.last_seen)}`, u.email].filter(Boolean).join(" · ");
  t.append(head, meta);
  row.onclick = () => { admUserId = u.id; go("auser"); };
}

$("userFind").oninput = () => { clearTimeout(admSearchTimer); admSearchTimer = setTimeout(() => admLoadUsers(), 300); };
$("userFind").onfocus = () => $("userFind").removeAttribute("readonly");
$("userFilter").querySelectorAll("button").forEach(b => b.onclick = () => { admFilter = b.dataset.f; admLoadUsers(); });
$("userMore").onclick = () => admLoadUsers(true);

// ---------- 一个用户的详情 ----------
let admUserId = null, admUser = null;
onShow.auser = async () => {
  if (!isAdmin || !admUserId) return location.replace("#admin");
  $("auMsg").textContent = "";
  await admLoadUser();
};

function admLines(box, lines) {
  box.textContent = "";
  for (const [k, v] of lines) {
    const row = document.createElement("div"); row.className = "lline";
    const a = document.createElement("span"); a.className = "meta left"; a.textContent = k;
    const b = document.createElement("span"); b.textContent = v; b.style.textAlign = "right"; b.style.overflowWrap = "anywhere";
    row.append(a, b); box.appendChild(row);
  }
}

async function admLoadUser() {
  let u;
  try { u = await api(`/api/admin/users/${admUserId}?` + tzQuery()); } catch (e) { return toast(e.message); }
  admUser = u;
  $("title").textContent = admName(u);
  const member = u.member_until ? `到 ${admFullDate(u.member_until)}`
    : u.member_last ? `已过期（${admFullDate(u.member_last)}）` : "不是会员";
  admLines($("auInfo"), [
    ["昵称", u.nickname || u.username], ["登录账号", u.username], ["通德 ID", u.uid || "-"],
    ["邮箱", u.email || "没有绑定"], ["注册时间", u.created_at ? admFullDate(u.created_at) : "（2026-11-08 前注册，没有记录）"],
    ["最近使用", admAgo(u.last_seen)], ["会员", u.admin ? "管理员，不限" : member],
    ...(u.banned ? [["已停用", u.banned]] : []),
  ]);
  admLines($("auStudy"), [
    ["学过的词", u.learned], ["已掌握", u.mastered], ["最近 7 天复习", `${u.reviews_7d} 次`],
    ["最后一次复习", admAgo(u.last_review)], ["自己加的词", u.added_words], ["自建情景对话", u.lessons], ["写过的反馈", u.feedback],
  ]);
  const pay = $("auPay");
  if (!u.payments.length) pay.textContent = "没有付款记录";
  else admLines(pay, u.payments.map(p => [
    `${admFullDate(p.paid_at || p.created_at)} · ${p.plan === "year" ? "年卡" : p.plan === "month" ? "月卡" : p.plan}`,
    admMoney(p.amount, p.currency) + (p.status === "paid" ? "" : "（没付完）")]));
  $("auUsageTitle").textContent = u.usage_day ? `免费次数用量（${u.usage_day}）` : "免费次数用量";
  if (!u.usage.length) $("auUsage").textContent = "没有记录（会员和管理员不记次数）";
  else admLines($("auUsage"), u.usage.map(x => [x.feature, x.count]));
  const self = u.me || u.admin;
  ["auMember", "auReset", "auBan"].forEach(id => $(id).classList.toggle("hidden", self));
  $("auBan").textContent = u.banned ? "恢复账号" : "停用账号";
  $("auBan").className = u.banned ? "secondary" : "danger";
}

$("auMember").onclick = async () => {
  const v = prompt(`给 ${admUser.username} 加几天会员？（填 0 = 取消会员）`, "30");
  if (v === null) return;
  try { await api(`/api/admin/users/${admUser.id}/membership`, "POST", { days: Number(v) }); } catch (e) { return toast(e.message); }
  toast("已修改会员");
  admLoadUser();
};
$("auReset").onclick = async () => {
  if (!confirm(`把 ${admUser.username} 的密码重置成一个临时密码？他原来的密码会失效，已登录的设备会下线。`)) return;
  let r;
  try { r = await api(`/api/admin/users/${admUser.id}/reset_password`, "POST", {}); } catch (e) { return toast(e.message); }
  $("auMsg").className = "msg left";
  $("auMsg").textContent = `${r.username} 的临时密码：${r.password}（请转告他，登录后在“我的”里改密码）`;
};
$("auBan").onclick = async () => {
  const banned = !admUser.banned;
  let reason = "";
  if (banned) {
    reason = prompt(`停用 ${admUser.username}？他会马上下线、不能再登录，数据都保留，以后可以恢复。\n原因（只有管理员能看到）：`, "");
    if (reason === null) return;
  } else if (!confirm(`恢复 ${admUser.username} 的账号？`)) return;
  try { await api(`/api/admin/users/${admUser.id}/ban`, "POST", { banned, reason }); } catch (e) { return toast(e.message); }
  toast(banned ? "已停用" : "已恢复");
  admLoadUser();
};

// ---------- 内容: 反馈和报错 ----------
async function loadReports() {
  let r;
  try { r = await api("/api/admin/feedback"); } catch (e) { return toast(e.message); }
  const box = $("reportList"); box.textContent = "";
  if (!r.items.length) box.textContent = "没有新的反馈和报错";
  for (const x of r.items) {
    const row = adminRow(box, "");
    const t = row.firstChild;
    const head = document.createElement("div"); head.className = "meta left"; head.style.fontSize = "13px";
    head.textContent = `${x.kind_name} · ${x.user || "（已删除的用户）"} · ${localDate(x.created_at).text}`;
    t.appendChild(head);
    if (x.target) {
      const tg = document.createElement("div"); tg.textContent = x.target; t.appendChild(tg);
    } else if (x.type === "report") {
      const tg = document.createElement("div"); tg.className = "meta left"; tg.textContent = "（内容已被删掉或重新生成）";
      t.appendChild(tg);
    }
    const reason = document.createElement("div"); reason.className = "lzh"; reason.textContent = x.reason;
    t.appendChild(reason);
    if (x.word_id) miniBtn(row, "单词卡", () => openWordId(x.word_id, x.target));
    miniBtn(row, "已处理", async () => {
      const body = x.type === "feedback" ? { type: "feedback", id: x.id } : { type: "report", kind: x.kind, key: x.key };
      try { await api("/api/admin/feedback/done", "POST", body); } catch (e) { return toast(e.message); }
      loadReports();
    });
  }
}

// ---------- 内容: 待审核单词 ----------
// 用户加的、词典里没有的词: 通过后所有人都能查到, 拒绝后还留在加过的人的学习计划里
async function loadPending() {
  let r;
  try { r = await api("/api/admin/pending"); } catch (e) { return toast(e.message); }
  const box = $("pendingList"); box.textContent = "";
  if (!r.words.length) box.textContent = "没有待审核的词";
  for (const w of r.words) {
    const row = document.createElement("div"); row.className = "lline nwordhead";
    const t = document.createElement("span");
    const head = document.createElement("b"); wordInto(head, w);
    const note = document.createElement("div"); note.className = "lzh";
    note.textContent = [`${w.users} 人加过`, w.compound ? `可能是复合词：${w.compound}` : "",
                        w.kind === "no_meaning" ? "缺公共释义" : ""].filter(Boolean).join(" · ");
    t.append(head, "  " + w.meaning, note);
    const act = document.createElement("span"); act.style.flex = "none";
    const button = (label, fn) => {
      const b = document.createElement("button"); b.className = "mini"; b.textContent = label;
      b.onclick = async () => { try { await fn(); } catch (e) { toast(e.message); } };
      act.appendChild(b);
    };
    if (w.kind === "pending") {
      for (const [label, status] of [["通过", "public"], ["拒绝", "rejected"]]) {
        button(label, async () => { await api("/api/admin/pending/" + w.id, "POST", { status }); loadPending(); });
      }
    } else {
      button("写释义", () => confirmMeaning(w, "", false));
      if (r.ai) button("AI 草稿", async () => confirmMeaning(w, (await api(`/api/admin/words/${w.id}/draft`, "POST", {})).meaning, true));
    }
    row.append(t, act); box.appendChild(row);
  }
}
// 公共释义要管理员确认才写入, AI 的草稿也一样
async function confirmMeaning(w, draft, ai) {
  const meaning = (prompt(`「${w.german}」的中文释义：`, draft) || "").trim();
  if (!meaning) return;
  await api(`/api/admin/words/${w.id}/meaning`, "POST", { meaning, ai });
  loadPending();
}

// ---------- 内容: 邀请码 ----------
// 邀请链接: 打开后注册页填好邀请码, 不用邮箱(core.js 的 inviteLink)
const inviteUrl = code => location.origin + location.pathname + "?invite=" + encodeURIComponent(code);

async function loadInvites() {
  let inv;
  try { inv = await api("/api/invites"); } catch (e) { return toast(e.message); }
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
      miniBtn(row, "复制链接", () => copyText(inviteUrl(i.code)));
      miniBtn(row, "作废", async () => {
        if (!confirm(`作废邀请码 ${i.code}？`)) return;
        try { await api("/api/invites/" + i.code, "DELETE"); } catch (e) { return toast(e.message); }
        loadInvites();
      });
    }
  }
}
$("btnInvite").onclick = async () => {
  let r;
  try { r = await api("/api/invites", "POST", {}); } catch (e) { return toast(e.message); }
  await loadInvites();
  copyText(inviteUrl(r.code));
};
