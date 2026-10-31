// 词库: 列表和搜索、添加单词(含变格/变位)、批量导入
let editingId = null;   // 正在编辑的词; null = 添加新词
$("goAdd").onclick = () => { editingId = null; go("add"); };
$("goImport").onclick = () => go("import");
function openEdit(id) { editingId = id; go("edit"); }
let viewingId = null, viewWord = null;   // 正在查看的词
function openView(id) { viewingId = id; go("view"); }

// 级别筛选
let wLevel = "";
const LEVEL_FILTERS = [["", "全部"], ["A1", "A1"], ["A2", "A2"], ["B1", "B1"], ["B2", "B2"], ["C1", "C1"],
                       ["dsh", "DSH"], ["common", "常用"], ["mine", "我加的"], ["hidden", "已删除"]];
for (const [v, label] of LEVEL_FILTERS) {
  const b = document.createElement("button");
  b.textContent = label; b.dataset.level = v;
  b.classList.toggle("on", v === wLevel);
  b.onclick = () => {
    wLevel = v;
    document.querySelectorAll("#wLevels button").forEach(x => x.classList.toggle("on", x.dataset.level === v));
    loadWords();
  };
  $("wLevels").appendChild(b);
}

function localDate(s) {   // 数据库里是 UTC 字符串, 显示成本地日期
  const d = new Date(s.replace(" ", "T") + "Z");
  return { d, text: `${d.getMonth() + 1}月${d.getDate()}日` };
}

function statusChip(w) {
  const c = document.createElement("span");
  c.className = "chip " + w.status;
  if (w.status === "new") c.textContent = "未学";
  else if (w.status === "mastered") c.textContent = "已掌握";
  else {
    const t = localDate(w.next_review);
    c.textContent = t.d <= new Date() ? "待复习" : "学习中 · " + t.text;
  }
  return c;
}

let searchTimer, searchSeq = 0;
async function loadWords() {
  const seq = ++searchSeq;
  const q = $("wSearch").value.trim();
  // 在“全部”里输入内容 = 查词(能查变位变格, 最相关的在前); 选了级别 = 在这个范围里筛选
  const dict = q && !wLevel;
  const url = dict ? "/api/dict?q=" + encodeURIComponent(q) : "/api/words?q=" + encodeURIComponent(q) + "&level=" + wLevel;
  let r;
  try { r = await api(url); } catch (e) { if (seq === searchSeq) toast(e.message); return; }
  if (seq !== searchSeq) return;   // 只显示最后一次搜索的结果
  const box = $("wList"); box.textContent = "";
  const limit = dict ? 50 : 200;
  $("wCount").textContent = q && !r.words.length ? `没有找到“${q}”`
    : (q ? "找到 " : "共 ") + r.words.length + " 个" + (r.words.length >= limit ? `（最多显示 ${limit} 个）` : "");
  box.classList.toggle("hidden", !r.words.length);
  for (const w of r.words) {
    const row = document.createElement("button"); row.className = "item wordrow";
    row.onclick = () => w.id ? openView(w.id) : openGlossaryWord(w);   // 情景课的仓储词还不在词库里, 用单词卡显示
    const body = document.createElement("span"); body.className = "body";
    const t = document.createElement("b"); wordInto(t, w);
    const s = document.createElement("small");
    s.textContent = [w.form ? `${w.form} 的原形` : "", w.glossary ? "📦 仓储词" : "", w.private ? "🔒 我加的" : "", w.edited ? "✏️ 已改" : "",
                     w.level, w.pos, w.meaning].filter(Boolean).join(" · ");
    body.append(t, s);
    if (w.hidden) {
      const c = document.createElement("span"); c.className = "chip"; c.textContent = "已删除";
      row.append(body, c);
    } else row.append(body, statusChip(w));
    box.appendChild(row);
  }
}
onShow.words = loadWords;
$("wSearch").oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadWords, 250); };

// ---- 单词详情(查看) ----
function studyText(w) {
  if (w.status === "new") return "还没学过。选它所在的单词书，复习时就会出现。";
  const due = localDate(w.next_review);
  const parts = [
    w.status === "mastered" ? "✔ 已掌握" : "学习中",
    due.d <= new Date() ? "现在就该复习了" : "下次复习：" + due.text,
    `复习过 ${w.reps} 次`, `忘过 ${w.lapses} 次`,
  ];
  if (w.stability != null) parts.push(`记忆稳定性约 ${w.stability} 天`);
  return parts.join(" · ");
}

onShow.view = async () => {
  if (!viewingId) return switchTab("words");   // 直接刷新 #view 时没有要看的词
  let w;
  try { w = await api("/api/words/" + viewingId); } catch (e) { return switchTab("words"); }
  viewWord = w;
  const bookTags = w.books.map(b => BOOK_NAMES[b] || b);
  $("vLevel").textContent = w.private ? "🔒 我加的词（只有你能看到）"
    : [w.level && w.level + " 单词书", ...bookTags].filter(Boolean).join(" · ") || "示例词";
  wordInto($("vWord"), w);
  $("vPos").textContent = w.pos || "";
  $("vMeaning").textContent = w.meaning;
  $("vPlural").textContent = w.plural && !(w.forms && w.forms.cases) ? "复数：" + w.plural : "";
  $("vExample").textContent = w.example || "";
  $("vSpeakEx").classList.toggle("hidden", !w.example);
  renderForms(w.forms, $("vForms"));
  renderDetails(w.details, $("vDetails"));
  $("vStatus").textContent = studyText(w);
  $("vQueue").classList.toggle("hidden", w.status !== "new" || w.hidden);
  $("vQueue").disabled = !!w.queued;
  $("vQueue").textContent = w.queued ? "已加入复习" : "加入复习";
  showNotice(w);
  if (getSetting("autoWord")) speakDe(wordText(w));
};
$("vSpeak").onclick = () => viewWord && speakDe(wordText(viewWord));
$("vSpeakEx").onclick = () => viewWord && speakDe(exampleDe(viewWord.example));
$("vQueue").onclick = async () => {
  try { await api("/api/review/queue", "POST", { word_id: viewingId }); } catch (e) { return toast(e.message); }
  $("vQueue").disabled = true; $("vQueue").textContent = "已加入复习";
  toast("已加入复习");
};
$("vEdit").onclick = () => openEdit(viewingId);

// 单词书的详细内容: 音标、词根、用法、更多例句、词组、近反义词、相关词、提示
const DETAIL_SECTIONS = [["root", "词根"], ["usage", "用法"], ["examples", "更多例句"], ["phrases", "常用词组"],
                         ["synonyms", "近义词"], ["antonyms", "反义词"], ["related", "相关词"], ["notes", "提示"]];
function renderDetails(d, box) {
  box.textContent = "";
  if (!d) return;
  if (d.machine) {
    const p = document.createElement("p"); p.className = "meta"; p.textContent = "⚠️ 这个释义是机器翻译，可能不准";
    box.appendChild(p);
  }
  if (d.ipa) {
    const p = document.createElement("p"); p.className = "meta"; p.textContent = `[${d.ipa}]`;
    box.appendChild(p);
  }
  for (const [key, title] of DETAIL_SECTIONS) {
    if (!d[key] || !d[key].length) continue;
    const h = document.createElement("h4"); h.className = "detail-title"; h.textContent = title;
    box.appendChild(h);
    for (const line of [].concat(d[key])) {
      const p = document.createElement("p"); p.className = "detail-line"; p.textContent = line;
      box.appendChild(p);
    }
  }
}

// 改过 / 删掉的词: 提示 + 恢复按钮
function showNotice(w) {
  const box = $("vNotice"), text = $("vNoticeText");
  box.classList.toggle("hidden", !w.hidden && !w.edited);
  $("vEdit").classList.toggle("hidden", w.hidden);
  text.textContent = "";
  if (w.hidden) {
    text.textContent = "🗑️ 这个词你删掉了（只对你自己隐藏，复习进度还在）。";
    $("vRestore").textContent = "↩️ 恢复这个词";
    $("vRestore").onclick = () => restore("unhide", "已恢复");
  } else if (w.edited) {
    const o = w.original;
    text.append("✏️ 你改过这个词，改动只对你自己生效。");
    const orig = document.createElement("div"); orig.className = "orig";
    orig.textContent = "原来的内容：" + wordText(o) + " — " + o.meaning;
    text.appendChild(orig);
    $("vRestore").textContent = "↩️ 恢复原来的内容";
    $("vRestore").onclick = () => confirm("恢复成原来的内容吗？你的修改会丢掉。") && restore("revert", "已恢复原来的内容");
  }
}

async function restore(action, msg) {
  try { await api(`/api/words/${viewingId}/${action}`, "POST", {}); toast(msg); onShow.view(); }
  catch (e) { toast(e.message); }
}

// ---- 添加单词时的变格 / 变位 ----
// 选了冠词 → 名词变格; 词性里有“动词” → 动词变位
let formKind = null;
function currentKind() {
  if ($("nGender").value) return "noun";
  return /动词|verb/i.test($("nPos").value) ? "verb" : null;
}

function updateFormsBox() {
  const k = currentKind();
  if (k === formKind) return;
  formKind = k;
  $("formsBox").classList.toggle("hidden", !k);
  const box = $("formsInputs"); box.textContent = "";
  if (!k) return;
  $("formsTitle").textContent = k === "noun" ? "名词变格（可选，带冠词；左列单数，右列复数）" : "动词现在时变位（可选）";
  const labels = k === "noun" ? CASES : [...PERSONS, "过去式", "完成时"];
  labels.forEach((l, i) => {
    const row = document.createElement("div"); row.className = "frow";
    const s = document.createElement("span"); s.textContent = l; row.appendChild(s);
    for (const col of k === "noun" ? ["sg", "pl"] : ["v"]) {
      const inp = document.createElement("input"); inp.id = `f_${col}${i}`;
      if (k === "verb" && i === 7) inp.placeholder = "如 ist gegangen / hat gemacht";
      row.appendChild(inp);
    }
    box.appendChild(row);
  });
}
$("nGender").onchange = updateFormsBox;
$("nPos").oninput = updateFormsBox;

function readForms() {
  const v = id => $(id).value.trim();
  if (formKind === "noun") {
    const sg = [0,1,2,3].map(i => v("f_sg" + i)), pl = [0,1,2,3].map(i => v("f_pl" + i));
    return sg.some(x => x) || pl.some(x => x) ? { cases: { sg, pl } } : undefined;
  }
  if (formKind === "verb") {
    const p = [0,1,2,3,4,5].map(i => v("f_v" + i)), past = [v("f_v6"), v("f_v7")];
    const f = {};
    if (p.some(x => x)) f.praesens = p;
    if (past.some(x => x)) f.past = past;
    return Object.keys(f).length ? f : undefined;
  }
}

// 按常规规则推算的草稿, 不规则词会错, 必须人工核对
function draftNoun(g, w, pl) {
  const A = { der: ["der","des","dem","den"], die: ["die","der","der","die"], das: ["das","des","dem","das"] }[g];
  const gen = g === "die" ? w : (/(s|ß|x|z|sch)$/.test(w) ? w + "es" : w + "s");
  const sg = [A[0] + " " + w, A[1] + " " + gen, A[2] + " " + w, A[3] + " " + w];
  if (!pl) return { sg, pl: ["", "", "", ""] };
  const dat = /[ns]$/.test(pl) ? pl : pl + "n";
  return { sg, pl: ["die " + pl, "der " + pl, "den " + dat, "die " + pl] };
}

function draftVerb(inf) {
  if (/eln$/.test(inf)) {            // sammeln → ich sammle
    const s = inf.slice(0, -1);
    return [s.slice(0, -2) + "le", s + "st", s + "t", inf, s + "t", inf];
  }
  if (/ern$/.test(inf)) {            // wandern → ich wandere
    const s = inf.slice(0, -1);
    return [s + "e", s + "st", s + "t", inf, s + "t", inf];
  }
  if (!/en$/.test(inf)) return null;
  const s = inf.slice(0, -2);
  // arbeiten → du arbeitest, öffnen → du öffnest
  const e = /([td]|(ch|[^aeiouäöülrhmn])[mn])$/.test(s) ? "e" : "";
  // heißen → du heißt
  const du = /[sßxz]$/.test(s) ? s + "t" : s + e + "st";
  return [s + "e", du, s + e + "t", inf, s + e + "t", inf];
}

$("btnDraft").onclick = () => {
  const m = $("addMsg"); m.className = "msg"; m.textContent = "";
  const w = $("nGerman").value.trim();
  if (!w) { m.textContent = "先填德语词"; return; }
  if (formKind === "noun") {
    const d = draftNoun($("nGender").value, w, $("nPlural").value.trim());
    [0,1,2,3].forEach(i => { $("f_sg" + i).value = d.sg[i]; $("f_pl" + i).value = d.pl[i]; });
  } else if (formKind === "verb") {
    const d = draftVerb(w);
    if (!d) { m.textContent = "这个词推算不了，请手动填写"; return; }
    d.forEach((x, i) => $("f_v" + i).value = x);
  }
};

const FIELDS = { german: "nGerman", gender: "nGender", pos: "nPos", plural: "nPlural", meaning: "nMeaning", example: "nExample" };

function fillForm(w) {
  for (const [k, id] of Object.entries(FIELDS)) $(id).value = w[k] || "";
  formKind = undefined; updateFormsBox();   // undefined: 强制按当前词性重建输入框
  const f = w.forms || {};
  if (formKind === "noun" && f.cases) [0,1,2,3].forEach(i => { $("f_sg" + i).value = f.cases.sg[i]; $("f_pl" + i).value = f.cases.pl[i]; });
  if (formKind === "verb") {
    (f.praesens || []).forEach((x, i) => $("f_v" + i).value = x);
    (f.past || []).forEach((x, i) => $("f_v" + (6 + i)).value = x);
  }
  $("addMsg").textContent = "";
}

onShow.add = () => {
  fillForm({});
  $("btnAdd").textContent = "添加";
  $("btnDelete").classList.add("hidden");
  $("editInfo").classList.remove("hidden");
  $("editInfo").textContent = "🔒 加的词只有你自己能看到。词库里已经有的词不会重复添加。";
};

onShow.edit = async () => {
  if (!editingId) return switchTab("words");   // 直接刷新 #edit 时没有要编辑的词
  const w = await api("/api/words/" + editingId);
  fillForm(w);
  $("btnAdd").textContent = "保存";
  $("btnDelete").classList.remove("hidden");
  $("editInfo").classList.remove("hidden");
  $("editInfo").textContent = (w.level ? "属于 " + w.level + " 单词书。" : "") +
    "改动只对你自己生效，以后可以在详情页「恢复原来的内容」。";
};

$("btnDelete").onclick = async () => {
  if (!confirm("删除后这个词只对你隐藏，复习进度会保留，以后可以在词库「已删除」里恢复。确定删除吗？")) return;
  try { await api("/api/words/" + editingId, "DELETE"); toast("已删除"); switchTab("words"); }   // 详情页也没了, 直接回词库
  catch (e) { $("addMsg").textContent = e.message; }
};

$("btnAdd").onclick = async () => {
  const m = $("addMsg"); m.className = "msg"; m.textContent = "";
  const body = Object.fromEntries(Object.entries(FIELDS).map(([k, id]) => [k, $(id).value]));
  if (current === "edit") {
    try {
      await api("/api/words/" + editingId, "PUT", { ...body, forms: readForms() || null });
      toast("已保存"); $("btnBack").click();
    } catch (e) { m.textContent = e.message; }
    return;
  }
  try {
    const r = await api("/api/words", "POST", { ...body, forms: readForms() });
    m.className = "msg ok"; m.textContent = r.added ? "已添加（只有你能看到）" : "词库里已经有这个词了";
    if (r.added) {
      ["nGerman","nPos","nPlural","nMeaning","nExample"].forEach(i => $(i).value = "");
      document.querySelectorAll("#formsInputs input").forEach(i => i.value = "");
      updateFormsBox();
    }
  } catch (e) { m.textContent = e.message; }
};

// ---- 批量导入 ----
$("btnBulk").onclick = async () => {
  const m = $("bulkMsg"); m.className = "msg"; m.textContent = "";
  const items = [];
  for (const line of $("bulk").value.split("\n")) {
    if (!line.trim()) continue;
    const parts = line.split(line.includes("\t") ? "\t" : ",").map(s => s.trim());
    items.push({ german: parts[0], gender: parts[1] || "", pos: parts[2] || "",
                 plural: parts[3] || "", meaning: parts[4] || "", example: parts[5] || "" });
  }
  if (!items.length) { m.textContent = "没有内容"; return; }
  try {
    const r = await api("/api/words", "POST", items);
    m.className = "msg ok"; m.textContent = `新增 ${r.added} 个，跳过重复 ${r.skipped} 个`;
    $("bulk").value = "";
  } catch (e) { m.textContent = e.message; }
};
