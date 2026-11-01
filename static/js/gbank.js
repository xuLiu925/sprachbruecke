// 语法题库管理(管理员): AI 出草稿、手动加题、修改、停用
let gbDrafts = [], gbOptions = [], gbAi = false;

function gbMsg(text, ok) { $("gbMsg").textContent = text || ""; $("gbMsg").className = ok ? "ok" : "msg"; }
const gbUrl = path => `/api/grammar/${gTopic.id}/${path}`;

onShow.gbank = async () => {
  if (!gTopic || !gTopic.bank) return location.replace("#grammar");
  $("title").textContent = gTopic.title + "题库";
  gbMsg("");
  await gbLoad();
};

async function gbLoad() {
  let r, st;
  try { [r, st] = await Promise.all([api(gbUrl("questions")), api(gbUrl("quiz") + "?n=1")]); }
  catch (e) { return toast(e.message); }
  gbOptions = r.options; gbAi = st.ai;
  $("gbGen").disabled = !gbAi;
  $("gbGen").textContent = gbAi ? "✨ 生成题目" : "还没有配置 API Key";
  $("gbManual").open = !gbAi;
  const on = r.questions.filter(q => q.status === "active").length;
  $("gbCount").textContent = `共 ${r.questions.length} 题，启用 ${on} 题`;
  const box = $("gbList"); box.textContent = "";
  for (const q of r.questions) box.appendChild(gbRow(q));
  gbNounReports();
}

// 自动出的名词题的报错: 题目不存数据库, 这里只记下问题, 处理后清除
async function gbNounReports() {
  let r;
  try { r = await api("/api/grammar/nouns/reports"); } catch (e) { return; }
  const box = $("gbNounReports"); box.textContent = "";
  box.classList.toggle("hidden", !r.reports.length);
  for (const x of r.reports) {
    const row = document.createElement("div"); row.className = "lline";
    const t = document.createElement("div"); t.textContent = `⚠️ ${x.german}：${x.reason}`;
    const b = document.createElement("button"); b.className = "mini"; b.textContent = "处理好了，清除";
    b.onclick = async () => {
      try { await api("/api/grammar/nouns/reports/" + x.id, "DELETE"); } catch (e) { return toast(e.message); }
      gbNounReports();
    };
    row.append(t, b); box.appendChild(row);
  }
}

const GB_SOURCE = { seed: "初始题", manual: "手动", ai: "AI，未核对" };
function gbRow(q) {
  const row = document.createElement("div"); row.className = "lline";
  const de = document.createElement("div"); de.textContent = q.prompt.replace("___", `[${q.answer}]`);
  const info = document.createElement("div"); info.className = "lzh";
  info.textContent = [GB_SOURCE[q.source], q.status === "hidden" ? "已停用" : "", q.zh].filter(Boolean).join(" · ");
  row.append(de, info);
  if (q.report) {
    const rp = document.createElement("div"); rp.className = "msg"; rp.textContent = "⚠️ 报错：" + q.report;
    row.appendChild(rp);
  }
  const acts = document.createElement("div"); acts.className = "lacts";
  const edit = document.createElement("button"); edit.className = "mini"; edit.textContent = "修改";
  edit.onclick = () => { gbDrafts.push({ ...q }); gbRender(); };
  const off = document.createElement("button"); off.className = "mini";
  off.textContent = q.status === "active" ? "停用" : "启用";
  off.onclick = async () => {
    try { await api(`/api/grammar/questions/${q.id}/status`, "POST", { status: q.status === "active" ? "hidden" : "active" }); }
    catch (e) { return toast(e.message); }
    gbLoad();
  };
  acts.append(edit, off);
  row.appendChild(acts);
  return row;
}

function gbBody() {
  const request = $("gbWant").value.trim();
  if (request.length < 2) { gbMsg("请先写一下想出什么题"); return null; }
  return { request, n: +$("gbN").value };
}

$("gbGen").onclick = async () => {
  const body = gbBody();
  if (!body) return;
  const btn = $("gbGen"); gbMsg(""); btn.disabled = true; btn.textContent = "AI 正在出题…";
  try { gbDrafts.push(...(await api(gbUrl("generate"), "POST", body)).questions); gbRender(); }
  catch (e) { gbMsg(e.message); if (e.status === 429 || e.status === 503) $("gbManual").open = true; }
  btn.disabled = !gbAi; btn.textContent = "✨ 生成题目";
};
$("gbCopy").onclick = async () => {
  const body = gbBody();
  if (!body) return;
  try { copyText((await api(gbUrl("prompt"), "POST", body)).prompt); } catch (e) { gbMsg(e.message); }
};
$("gbRead").onclick = async () => {
  try {
    gbDrafts.push(...(await api(gbUrl("check"), "POST", { text: $("gbPaste").value })).questions);
    $("gbPaste").value = ""; gbMsg(""); gbRender();
  } catch (e) { gbMsg(e.message); }
};
$("gbAdd").onclick = () => {
  gbDrafts.push({ prompt: "", answer: gbOptions[0], hint: "", explain: "", zh: "", source: "manual" });
  gbRender();
};

function gbField(d, key, label, min) {
  const t = document.createElement("textarea");
  t.className = "lnedit"; t.placeholder = label; t.value = d[key] || ""; t.spellcheck = false;
  if (min) t.style.height = min;
  t.oninput = () => { d[key] = t.value; };
  return t;
}

// 草稿: 句子都能直接改, 保存时后端再检查一遍
function gbRender() {
  const box = $("gbDrafts"); box.textContent = "";
  $("gbDraftBox").classList.toggle("hidden", !gbDrafts.length);
  gbDrafts.forEach((d, i) => {
    const row = document.createElement("div"); row.className = "lline";
    const sel = document.createElement("select");
    for (const o of gbOptions) sel.add(new Option(o, o));
    sel.value = d.answer; sel.onchange = () => { d.answer = sel.value; };
    const del = document.createElement("button"); del.className = "mini"; del.textContent = "去掉这题";
    del.onclick = () => { gbDrafts.splice(i, 1); gbRender(); };
    row.append(gbField(d, "prompt", "德语句子，用 ___ 表示空格"), sel,
               gbField(d, "hint", "提示，如 die Palette · 阴性", "42px"),
               gbField(d, "explain", "中文解释"), gbField(d, "zh", "中文翻译"), del);
    box.appendChild(row);
  });
  if (gbDrafts.length) $("gbDraftBox").scrollIntoView({ behavior: "smooth" });
}

$("gbSave").onclick = async () => {
  let r;
  try { r = await api(gbUrl("questions"), "POST", { questions: gbDrafts }); }
  catch (e) { return toast(e.message); }
  gbDrafts = []; gbRender();
  toast(r.skipped ? `保存 ${r.saved} 题，${r.skipped} 题重复已跳过` : `已保存 ${r.saved} 题`);
  if (r.missing.length) alert(`已保存。这些词不在海外仓词汇里，选这本书时练不到：${r.missing.join("、")}`);
  gbLoad();
};
