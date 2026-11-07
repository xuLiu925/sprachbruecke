// 句子练习: 填空 / 排序 / 中译德(不影响今日学习)。入口页 #sentence 选题型和练习范围, 答题页 #squiz
// 后端 sentences.py 按词 + 题型用 FSRS 排期, 每种题型一本错题本; 答错的本组最后再练一次, 只记第一次作答
const S_MODES = {
  cloze:     { ico: { text: "__" }, name: "句子填空", sub: "看中文，填出句子里缺的词（要写对变位和变格）" },
  order:     { ico: { text: "1·2" }, name: "连词成句", sub: "把打乱的词排成正确的句子，练语序" },
  translate: { ico: { text: "中→德" }, name: "中译德", sub: "看中文写出整句德语，再和例句对照" },
};
let sMode = "cloze", sq = [], si = 0;
let sAnswers = [];    // sAnswers[i] = { ok, input, picked, msg }; ok 为 null = 等用户自己判断
let sPool = [], sPicked = [];   // 排序题: 打乱后的顺序、已选的(都是 tokens 的下标)
let sPreset = null;   // 情景课自带的题目 {mode, name, questions}; null = 向服务器要题。rules = 复数练习(规律提示、记录作答)

// ---------- 入口页: 题型 + 练习范围 ----------
let sScopes = [], sScopeNow = "", sScopeRun = "";
const sModeItems = {};
for (const [mode, m] of Object.entries(S_MODES)) {
  const it = listItem(m.ico, m.name, m.sub, () => sPickMode(mode));
  sModeItems[mode] = it;
  $("sList").appendChild(it);
}
// 错题本页、单词列表页用: 每种题型一份, api 里带题型
const S_LISTS = Object.fromEntries(Object.keys(S_MODES).map(mode => [mode, {
  api: "/api/sentences/" + mode, scopes: () => sScopes, unit: "词", sample: "例如：Palette, abholen, schnell",
  start(scope) { sMode = mode; sScopeNow = scope; setSetting("sScope", scope); sGo(scope); },
}]));
function sGo(scope) { sPreset = null; sScopeRun = scope; go("squiz"); }

async function sLoadScopes() {
  for (const [mode, it] of Object.entries(sModeItems)) it.classList.toggle("current", mode === sMode);
  let r;
  try { r = await api(`/api/sentences/${sMode}/books`); } catch (e) { return toast(e.message); }
  sScopes = scopeItems(r);
  const saved = getSetting("sScope");
  sScopeNow = sScopes.some(x => x.id === saved) ? saved : r.current;
  sShowScopes();
}
function sShowScopes() {
  scopeInto($("sScope"), sScopes, sScopeNow, id => { sScopeNow = id; setSetting("sScope", id); sShowScopes(); },
            id => gnOpen(id, S_LISTS[sMode]));
}
function sPickMode(mode) { sMode = mode; setSetting("sMode", mode); sLoadScopes(); }
onShow.sentence = () => {
  const saved = getSetting("sMode");
  if (S_MODES[saved]) sMode = saved;
  sLoadScopes();
};
$("sStartBtn").onclick = () => { if (sScopeNow) sGo(sScopeNow); };

async function sStart() {
  if (sPreset) sMode = sPreset.mode;
  else if (!sScopeRun && S_MODES[getSetting("sMode")]) sMode = getSetting("sMode");   // 直接刷新答题页
  $("title").textContent = sPreset ? sPreset.name : S_MODES[sMode].name;
  $("sqBox").classList.add("hidden");
  $("sqDone").classList.add("hidden");
  if (sPreset && sPreset.questions) sq = sPreset.questions;
  else try {
    const scope = sScopeRun || getSetting("sScope") || "";         // 直接刷新答题页时用上次的范围
    sq = (await api(sPreset ? sPreset.url                           // 词形练习每组重新要题
      : `/api/sentences?mode=${sMode}&scope=${encodeURIComponent(scope)}&${tzQuery()}`)).questions;
  } catch (e) { toast(e.message); return; }
  si = 0; sAnswers = [];
  sRender();
}
onShow.squiz = sStart;
$("sqAgain").onclick = sStart;

function sShuffled(n) {
  const a = [...Array(n).keys()];
  for (let t = 0; t < 5; t++) {
    for (let i = n - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    if (a.some((x, i) => x !== i)) break;     // 别刚好是正确顺序
  }
  return a;
}

function sRender() {
  const done = si >= sq.length;
  $("sqBox").classList.toggle("hidden", done);
  $("sqDone").classList.toggle("hidden", !done);
  $("sqBack").classList.toggle("hidden", si === 0 || done);
  if (done) return sFinish();
  const q = sq[si], a = sAnswers[si];
  $("sqProgress").textContent = `第 ${si + 1} / ${sq.length} 题` + (q.retry ? " · 错题再练一次" : "");
  $("sqRuleRow").classList.toggle("hidden", !(sPreset && sPreset.rules));
  $("sqRuleOn").checked = getSetting("pHints");
  sRuleHint();
  $("sqZh").textContent = q.zh;
  const cloze = sMode === "cloze", order = sMode === "order";
  $("sqCloze").classList.toggle("hidden", !cloze);
  $("sqHint").classList.toggle("hidden", !cloze);
  if (cloze) {
    $("sqCloze").textContent = q.blank.before + "_____" + q.blank.after;
    $("sqHint").textContent = `提示：${wordText(q)}（${q.meaning}）`;
  }
  $("sqTyping").classList.toggle("hidden", order);
  $("sqOrder").classList.toggle("hidden", !order);
  $("sqAnswer").classList.add("hidden");
  $("sqActions").classList.remove("hidden");
  if (order) {
    sPool = sShuffled(q.tokens.length);
    sPicked = a ? a.picked.slice() : [];
    sRenderChips();
  } else {
    $("sqIn").style.minHeight = cloze ? "0" : "88px";
    $("sqIn").rows = cloze ? 1 : 3;
    $("sqIn").placeholder = cloze ? "填入缺的词" : "写出这句话的德语";
    $("sqIn").value = a ? a.input : "";
    $("sqIn").readOnly = !!a;        // 用“上一题”回来看的: 只看, 不能改
    if (!a) $("sqIn").focus();
  }
  if (a) sShow(q, a);
}

// 复数练习: 开关打开时, 答题前显示这个词用哪条规律
function sRuleHint() {
  const q = sq[si], on = sPreset && sPreset.rules && getSetting("pHints") && !sAnswers[si];
  $("sqRuleHint").classList.toggle("hidden", !on);
  $("sqRuleHint").textContent = on ? "规律：" + q.rule_hint : "";
}
$("sqRuleOn").onchange = () => { setSetting("pHints", $("sqRuleOn").checked); if (si < sq.length) sRuleHint(); };

function sChip(box, text, fn, off) {
  const b = document.createElement("button");
  b.className = "secondary"; b.textContent = text; b.onclick = fn;
  b.style.visibility = off ? "hidden" : "";   // 用过的词留空位, 其他词不跟着移动
  box.appendChild(b);
}
function sRenderChips() {
  const q = sq[si], locked = !!sAnswers[si];
  const line = $("sqLine"), pool = $("sqChips");
  line.textContent = ""; pool.textContent = "";
  sPicked.forEach((n, i) => sChip(line, q.tokens[n], () => {
    if (!locked) { sPicked.splice(i, 1); sRenderChips(); }
  }));
  if (!locked) for (const n of sPool) sChip(pool, q.tokens[n], () => sPick(n), sPicked.includes(n));
}
function sPick(n) {
  if (sAnswers[si] || sPicked.includes(n)) return;
  sPicked.push(n);
  sRenderChips();
}

const sPlain = s => fold(s.replace(/[.,!?;]/g, " "));   // 比较整句: 不管标点、大小写和多余空格

function sCheck() {
  if (si >= sq.length) return;
  if (sAnswers[si]) {
    if (sAnswers[si].ok !== null) { si++; sRender(); }   // 已经判过: 回车 = 下一题
    return;
  }
  const q = sq[si];
  let a;
  if (sMode === "order") {
    if (sPicked.length < q.tokens.length) return toast("还有词没有排");
    const same = sPicked.map(n => q.tokens[n]).join(" ") === q.tokens.join(" ");
    a = { ok: same ? true : null, picked: sPicked.slice(), msg: same ? "✓ 正确" : "和例句的语序不同，请对照：" };
  } else {
    const input = $("sqIn").value;
    if (!input.trim()) return $("sqIn").focus();
    if (sMode === "cloze") {
      const results = (q.accept || [q.blank.answer]).map(x => checkSpell({ german: x, gender: "" }, input));
      const r = results.find(x => x.ok) || results[0];     // 有的词两种写法都对
      a = { ok: r.ok, input, msg: r.msg };
    } else {
      const same = sPlain(input) === sPlain(q.de);
      a = { ok: same ? true : null, input, msg: same ? "✓ 和例句一样" : "请和例句对照：" };
    }
  }
  sSubmit(q, a);
}

// 对错定下来以后(自评的题等用户选了): 记一次作答, 答错的排到本组最后再练一次。情景课、词形练习等 sPreset 的题不记
function sDecided(q, ok) {
  if (sPreset || q.retry || !q.word_id) return;
  api(`/api/sentences/${sMode}/result`, "POST", { word_id: q.word_id, ok }).catch(() => {});
  if (!ok) sq.push({ ...q, retry: true });
}

function sSubmit(q, a) {
  sAnswers[si] = a;
  if (sPreset && sPreset.onAnswer && !q.retry) sPreset.onAnswer(q, a.ok);
  if (a.ok !== null) sDecided(q, a.ok);
  sRuleHint();
  $("sqIn").readOnly = sMode !== "order";
  $("sqIn").blur();                 // 离开输入框, 快捷键才生效
  if (sMode === "order") sRenderChips();
  sShow(q, a);
  if (getSetting("autoExample")) speakDe(q.de);
}

// 不会: 直接看答案, 算答错, 结尾进“再看一遍”
function sGiveUp() {
  if (si >= sq.length || sAnswers[si]) return;
  sSubmit(sq[si], { ok: false, input: "", picked: [], msg: "不会，记一下答案" });
}
$("sqCheck").onclick = sCheck;
$("sqGiveUp").onclick = sGiveUp;
$("sqNext").onclick = sCheck;

function sShow(q, a) {
  $("sqResult").textContent = a.msg;
  $("sqResult").className = a.ok === false ? "msg" : a.ok ? "ok" : "";
  exampleInto($("sqDe"), q.de, null);
  // 词形练习的答案只是一个词组, 不用讲解
  exampleExplain($("sqDe"), sPreset && sPreset.url ? "" : `${q.de}\n${q.zh}`);
  $("sqGloss").classList.toggle("hidden", !q.german);   // 情景课的排序题没有目标词
  wordInto($("sqWord"), q);
  $("sqMeaning").textContent = q.meaning;
  $("sqRule").classList.toggle("hidden", !q.rule);
  $("sqRule").textContent = q.rule ? "规律：" + q.rule : "";
  $("sqReport").classList.toggle("hidden", !q.rule);
  $("sqSelf").classList.toggle("hidden", a.ok !== null);
  $("sqNext").classList.toggle("hidden", a.ok === null);
  $("sqAnswer").classList.remove("hidden");
  $("sqActions").classList.add("hidden");
}

// 语序灵活、同一句中文有多种译法, 不一样不等于错, 所以由用户自己判断
function sSelf(ok) {
  const a = sAnswers[si];
  if (!a || a.ok !== null) return;
  a.ok = ok;
  sDecided(sq[si], ok);
  sShow(sq[si], a);
}
$("sqSelfYes").onclick = () => sSelf(true);
$("sqSelfNo").onclick = () => sSelf(false);
$("sqSay").onclick = () => { if (si < sq.length) speakDe(sq[si].de); };
$("sqBack").onclick = () => { if (si > 0) { si--; sRender(); } };   // 只回看, 不能改答案

function sFinish() {
  const total = sq.filter(q => !q.retry).length;       // 得分只算第一次作答
  const wrong = sq.filter((q, i) => !q.retry && !sAnswers[i].ok);
  $("sqScore").textContent = sq.length ? `得分 ${total - wrong.length} / ${total}` : "还没有可以出的题";
  const box = $("sqWrong"); box.textContent = "";
  if (wrong.length) {
    box.append("再看一遍：");
    for (const q of wrong) {
      const line = document.createElement("div");
      line.textContent = q.recap || `${q.de} — ${q.zh}`;
      box.appendChild(line);
    }
  } else if (sq.length) box.textContent = "全部答对了";
  else box.textContent = sPreset ? (sPreset.empty || "这一课没有这种题。")
    : sScopeRun === "wrong" ? "错题本是空的，换个范围继续练。" : "这种题需要带中文翻译的例句，换一本单词书试试。";
  if (wrong.length && !sPreset) box.append(document.createElement("div"), "答错的词已经加进这种题型的错题本。");
}

// 回车 检查 / 下一题(在输入框里也有效)
$("sqIn").onkeydown = e => {
  if (e.key === "?" && sMode === "cloze" && !e.isComposing) {     // 填空题里问号不是答案, 中译德要能打问号
    e.preventDefault(); e.stopPropagation(); sGiveUp(); return;
  }
  if (e.key !== "Enter" || e.isComposing) return;
  e.preventDefault(); e.stopPropagation(); sCheck();
};
onKey.squiz = (e, typing) => {
  if (typing || e.ctrlKey || si >= sq.length) return false;
  const a = sAnswers[si], pending = a && a.ok === null;
  if (e.key === "?" && !a) { sGiveUp(); return true; }
  if (e.key === "Enter" || e.key === " ") { sCheck(); return true; }
  if (pending && (e.key === "1" || e.key === "2")) { sSelf(e.key === "1"); return true; }
  if (a && e.key.toLowerCase() === "p") { $("sqSay").click(); return true; }
  if (sMode !== "order" || a) return false;
  if (e.key === "Backspace" && sPicked.length) { sPicked.pop(); sRenderChips(); return true; }
  const left = sPool.filter(n => !sPicked.includes(n)), n = parseInt(e.key, 10);   // 数字键 = 选剩下的第几个词
  if (n >= 1 && n <= left.length) { sPick(left[n - 1]); return true; }
  return false;
};
