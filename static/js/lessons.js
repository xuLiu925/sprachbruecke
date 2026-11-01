// 情景课: 读课文(点词看详情) → 练习 → 用德语写出来。内容在 static/lessons.json, 完成记录存本机
let lessons = null, lessonNow = null, lessonShown = null, wsSeq = 0, wsWord = null, lessonAi = false;
let wsStack = [], wsNow = null, wsLoads = Promise.resolve();   // 单词卡看过的词, 返回时重新打开
let wsAsk = null;     // 单词卡要交给 AI 查的 {q, context}
const LESSON_LEVELS = { A1: "A1 入门", A2: "A2 基础", B1: "B1 进阶" };

async function loadLessons() {
  if (lessons) return lessons;
  const [r, mine] = await Promise.all([fetch("static/lessons.json"), api("/api/custom_lessons")]);
  if (!r.ok) throw new Error("课程加载失败");
  lessons = [...mine.lessons, ...(await r.json()).lessons];
  lessonAi = mine.ai;
  return lessons;
}
const lessonDone = () => getSetting("lessonDone") || {};

$("lDue").onclick = () => rpOpen(null);
$("lRoleplay").onclick = () => { if (lessonNow) rpOpen(lessonNow.id); };

onShow.lessons = async () => {
  showSentenceDue($("lDue"));
  let all;
  try { all = await loadLessons(); } catch (e) { return toast(e.message); }
  const box = $("lessonList"), done = lessonDone(); box.textContent = "";
  const section = (name, items, ico) => {
    if (!items.length) return;
    const h = document.createElement("h2"); h.textContent = name;
    const list = document.createElement("div"); list.className = "list";
    for (const l of items) {
      list.appendChild(listItem(done[l.id] ? "✅" : ico, l.title, l.scene, () => { lessonNow = l; go("lesson"); }));
    }
    box.append(h, list);
  };
  section("我的工作对话", all.filter(x => x.custom), "📝");
  for (const [lv, name] of Object.entries(LESSON_LEVELS)) {
    section(name, all.filter(x => x.level === lv && !x.custom), "📦");
  }
};
$("lNew").onclick = () => go("lnew");

function lessonTokens(box, line) {
  const re = /[A-Za-zÄÖÜäöüß]+(?:-[A-Za-zÄÖÜäöüß]+)*/g;   // E-Mail 算一个词
  let at = 0;
  for (const m of line.de.matchAll(re)) {
    box.append(line.de.slice(at, m.index));
    const b = document.createElement("button");
    b.className = "tok"; b.textContent = m[0];
    b.onclick = () => openWordSheet(m[0], line);
    box.appendChild(b);
    at = m.index + m[0].length;
  }
  box.append(line.de.slice(at));
}

function lessonLine(line) {
  const row = document.createElement("div"); row.className = "lline";
  const who = document.createElement("div"); who.className = "lwho"; who.textContent = line.who;
  const de = document.createElement("div"); de.className = "lde"; lessonTokens(de, line);
  const zh = document.createElement("div"); zh.className = "lzh hidden"; zh.textContent = line.zh;
  const acts = document.createElement("div"); acts.className = "lacts";
  const say = document.createElement("button"); say.className = "mini"; say.textContent = "🔊 听";
  say.onclick = () => speakDe(line.de);
  const tr = document.createElement("button"); tr.className = "mini"; tr.textContent = "中文";
  tr.onclick = () => zh.classList.toggle("hidden");
  const note = document.createElement("div"); note.className = "lnote hidden";
  const ex = document.createElement("button"); ex.className = "mini"; ex.textContent = "📖 讲解";
  ex.onclick = () => openExplain(note, line, lessonNow.level);
  acts.append(say, tr, ex);
  row.append(who, de, zh, acts, note);
  return row;
}

onShow.lesson = () => {
  if (!lessonNow) return location.replace("#lessons");
  const l = lessonNow;
  $("title").textContent = l.title;
  if (lessonShown === l.id) return;   // 从单词详情 / 练习回来: 写了一半的内容要保留
  lessonShown = l.id;
  $("lLevel").textContent = LESSON_LEVELS[l.level] + (l.custom ? " · AI 生成，未核对" : "");
  $("lDelete").classList.toggle("hidden", !l.custom);
  $("lScene").textContent = l.scene;
  const box = $("lLines"); box.textContent = "";
  l.lines.forEach(x => box.appendChild(lessonLine(x)));
  $("lTask").textContent = l.task.prompt;
  const tips = $("lTips"); tips.textContent = "";
  for (const t of l.task.tips) { const li = document.createElement("li"); li.textContent = t; tips.appendChild(li); }
  $("lWrite").value = "";
  $("lModel").classList.add("hidden");
  $("lShowModel").classList.remove("hidden");
  const model = $("lModel"); model.textContent = "";
  for (const m of l.task.model) {
    const row = document.createElement("div"); row.className = "lline";
    const de = document.createElement("button"); de.className = "lmodel"; de.textContent = "🔊 " + m.de;
    de.onclick = () => speakDe(m.de);
    const zh = document.createElement("div"); zh.className = "lzh"; zh.textContent = m.zh;
    row.append(de, zh); model.appendChild(row);
  }
};

$("lShowModel").onclick = () => {
  $("lModel").classList.remove("hidden");
  $("lShowModel").classList.add("hidden");
  const d = lessonDone(); d[lessonNow.id] = true; setSetting("lessonDone", d);
};
$("lDelete").onclick = async () => {
  const l = lessonNow;
  if (!l || !l.custom || !confirm(`删除“${l.title}”？这一课的整句复习也会停止。`)) return;
  try { await api("/api/custom_lessons/" + l.id.slice(1), "DELETE"); } catch (e) { return toast(e.message); }
  lessons = null; lessonNow = null; lessonShown = null;
  toast("已删除");
  location.replace("#lessons");
};
$("lPlayAll").onclick =() => { lessonNow.lines.forEach((x, i) => speakDe(x.de, i > 0)); };

// 把课文变成句子练习的题目, 用 sentence.js 的答题页
function lessonGloss(c) { return { german: c.base, gender: c.gender, meaning: c.meaning }; }
function lessonCloze(l) {
  return l.cloze.map(c => {
    const x = l.lines[c.line], at = x.de.search(new RegExp(`(?<!\\p{L})${c.answer}(?!\\p{L})`, "u"));
    return { ...lessonGloss(c), de: x.de, zh: x.zh, tokens: [],
             blank: { before: x.de.slice(0, at), answer: c.answer, after: x.de.slice(at + c.answer.length) } };
  });
}
function lessonOrder(l) {
  const qs = l.lines.filter(x => !/[.!?]./.test(x.de) && /[.!?]$/.test(x.de)).map(x => {
    const tokens = x.de.slice(0, -1).split(/\s+/).map(t => t.replace(/,/g, ""));
    return { german: "", gender: "", meaning: "", de: x.de, zh: x.zh, tokens };
  }).filter(q => q.tokens.length >= 3 && q.tokens.length <= 12);
  return qs.sort(() => Math.random() - 0.5).slice(0, 6);
}
$("lCloze").onclick = () => { sPreset = { mode: "cloze", name: "本课填空", questions: lessonCloze(lessonNow) }; go("squiz"); };
$("lOrder").onclick = () => { sPreset = { mode: "order", name: "本课连词成句", questions: lessonOrder(lessonNow) }; go("squiz"); };

// ---------- 点词: 底部弹出单词卡 ----------
function closeWordSheet() {
  $("wsheet").classList.add("hidden"); wsWord = null; wsSeq++; wsMoreReset();
  wsStack = []; wsNow = null; wsBackShow();
}
const wsBox = () => $("wsheet").firstElementChild;
function wsBackShow() {
  const prev = wsStack[wsStack.length - 1];
  $("wsBack").classList.toggle("hidden", !prev);
  $("wsBack").textContent = prev ? "‹ " + prev.label : "";
}
// 打开新词前记下当前这张卡: 显示的词、滚动位置、详情是否展开。点到同一个词不记
function wsEnter(next) {
  const low = next.label.toLowerCase();
  const same = wsNow && [wsNow.label, wsWord && wsWord.german].some(x => x && x.toLowerCase() === low);
  if (wsNow && !same) {
    wsStack.push({ ...wsNow, label: (wsWord && wsWord.german) || wsNow.label, scroll: wsBox().scrollTop,
                   more: !$("wsMore").classList.contains("hidden") });
  }
  wsNow = next;
  wsBackShow();
  wsBox().scrollTop = 0;
}
// 回到上一张卡, 内容都加载完再恢复详情和滚动位置, 否则卡片还不够高, 滚不到原来的位置
async function wsBack() {
  const prev = wsStack.pop();
  if (!prev) return;
  wsNow = prev;
  wsBackShow();
  if (prev.glossary) openGlossaryWord(prev.glossary, true, true);
  else await openWordSheet(prev.token, prev.line, true);
  await wsLoads;
  if (wsNow !== prev) return;                // 这期间又点了别的词
  if (prev.more && wsWord && wsWord.id) await $("wsView").onclick();
  if (wsNow === prev) wsBox().scrollTop = prev.scroll;
}
$("wsBack").onclick = wsBack;
$("wsClose").onclick = closeWordSheet;
$("wsheet").onclick = e => { if (e.target === $("wsheet")) closeWordSheet(); };
window.addEventListener("hashchange", closeWordSheet);

function wsButton(w) {
  const b = $("wsAdd");
  b.disabled = !!(w.learned || w.queued);
  b.textContent = w.learned ? "已经学过" : w.queued ? "已加入复习" : "加入复习";
}

// 缩合词和词库反查不到的常见形式 → 原形
const LESSON_FORMS = { im: "in", ins: "in", am: "an", ans: "an", zum: "zu", zur: "zu", vom: "von", beim: "bei",
                       den: "der", jeden: "jeder", "nächsten": "nächste", "lädt": "laden", sprich: "sprechen",
                       ankommt: "ankommen", "wäre": "sein" };

function lessonGlossary(lemma) {          // 本课优先, 再看其他课; 复数也能找到
  const key = lemma.toLowerCase();
  const hit = g => g.german.toLowerCase() === key || (g.plural || "").toLowerCase() === key;
  return (lessonNow && lessonNow.glossary.find(hit)) || (lessons || []).flatMap(l => l.glossary).find(hit);
}

// 例句(“德语\n中文”)里的德语词可以点, 中文行照常显示
function exampleInto(el, text, level = "B1") {
  const [de, ...rest] = (text || "").split("\n");
  el.textContent = "";
  lessonTokens(el, { de });
  if (rest.length) el.append(document.createElement("br"), rest.join("\n"));
  if (level) exampleExplain(el, text, level);
}

// 例句下面的“讲解”。每次换句子都重建, 上一句的讲解自然收起; text 为空时不显示
function exampleExplain(el, text, level = "B1") {
  const anchor = el.closest(".exrow") || el;
  let box = anchor.nextElementSibling;
  if (!box || !box.classList.contains("exnote")) {
    box = document.createElement("div"); box.className = "exnote";
    anchor.after(box);
  }
  box.textContent = "";
  const [de, ...rest] = (text || "").split("\n");
  if (!de.trim()) return;
  const note = document.createElement("div"); note.className = "lnote hidden";
  const btn = document.createElement("button"); btn.className = "mini"; btn.textContent = "📖 讲解";
  btn.onclick = () => openExplain(note, { de: de.trim(), zh: rest.join(" ").trim() }, level);
  box.append(btn, note);
}

// 这些页面离开再回来会重新出题, 所以单词卡里不放“详情”, 免得丢掉正在做的这一组
const wsCanLeave = () => !["review", "drill", "dictation", "squiz", "gquiz"].includes(current);

async function openWordSheet(token, line, back = false) {
  if (!back) wsEnter({ token, line, label: token });
  wsWord = null;
  const seq = ++wsSeq;
  const lemma = (line.map && line.map[token]) || LESSON_FORMS[token.toLowerCase()] || token;
  $("wsheet").classList.remove("hidden");
  $("wsWord").textContent = token;
  $("wsPlural").textContent = ""; $("wsMeaning").textContent = "查询中…"; $("wsLesson").textContent = "";
  $("wsExample").textContent = "";
  wsMoreReset();
  genderReason($("wsGender"), "", "");
  wordParts($("wsParts"), "");
  $("wsAdd").classList.add("hidden"); $("wsView").classList.add("hidden"); $("wsSay").classList.add("hidden");
  $("wsAi").classList.add("hidden"); $("wsNoun").classList.add("hidden");
  try { await loadLessons(); } catch (e) {}   // 复习页里可能还没加载过课程; 没有仓储词表也能查词
  if (seq !== wsSeq) return;
  const gl = lessonGlossary(lemma);
  let found = null;
  try { found = (await api("/api/lookup?w=" + encodeURIComponent(gl ? gl.german : lemma))).word; }
  catch (e) { if (seq === wsSeq) toast(e.message); }
  if (seq !== wsSeq) return;                 // 查询期间又点了别的词
  const w = found || gl;
  if (!w) {
    wsWord = null;
    let r = {};
    try { r = await api("/api/dict?q=" + encodeURIComponent(lemma)); } catch (e) {}
    if (seq !== wsSeq) return;
    const saved = (r.words || []).find(x => x.ai_word);    // 以前用 AI 查过
    if (saved) return openGlossaryWord(saved, true, back);
    $("wsMeaning").textContent = "词库里没有这个词";
    if (r.can && r.ai) {                                   // 点了才调用 AI, 人名这类词不用查
      wsAsk = { q: lemma, context: line.de };
      $("wsAi").disabled = false; $("wsAi").textContent = "✨ 用 AI 查询";
      $("wsAi").classList.remove("hidden");
    }
    return;
  }
  wsWord = found ? { ...w } : { ...gl, learned: false, queued: false };
  wordInto($("wsWord"), w);
  $("wsPlural").textContent = [w.pos, w.plural ? "复数 " + w.plural : "", token !== w.german ? "文中是 " + token : ""]
    .filter(Boolean).join(" · ");
  $("wsMeaning").textContent = w.meaning;
  wsLoads = Promise.all([genderReason($("wsGender"), w.german, w.gender, w.meaning),
                         wordParts($("wsParts"), w.german, w.meaning)]);
  if (gl && found && gl.meaning !== found.meaning) $("wsLesson").textContent = "在仓库里：" + gl.meaning;
  $("wsSay").classList.remove("hidden");
  $("wsAdd").classList.remove("hidden"); wsButton(wsWord);
  $("wsNoun").classList.toggle("hidden", !w.gender);
  $("wsView").classList.toggle("hidden", !found);
  if (getSetting("autoWord") && !back) speakDe(wordText(w));
}
// 查词结果里的仓储词: 不用查询, 内容都在手上
// keep = 还是同一张卡(查词的结果), 不算打开新词; back = 从下一张卡返回, 不再朗读
function openGlossaryWord(g, keep = false, back = false) {
  if (!keep) wsEnter({ glossary: g, label: g.german });
  wsSeq++;
  wsWord = { ...g, id: null, learned: false, queued: false };
  wsMoreReset();
  $("wsAi").classList.add("hidden");
  $("wsheet").classList.remove("hidden");
  wordInto($("wsWord"), g);
  $("wsPlural").textContent = [g.pos, g.plural ? "复数 " + g.plural : ""].filter(Boolean).join(" · ");
  $("wsMeaning").textContent = g.meaning;
  wsLoads = Promise.all([genderReason($("wsGender"), g.german, g.gender, g.meaning),
                         wordParts($("wsParts"), g.german, g.meaning)]);
  $("wsExample").textContent = g.example || "";
  $("wsLesson").textContent = g.ai_word ? "AI 生成，未核对" : "";
  $("wsSay").classList.remove("hidden");
  $("wsView").classList.add("hidden");
  $("wsAdd").classList.remove("hidden"); wsButton(wsWord);
  $("wsNoun").classList.toggle("hidden", !g.gender);
  if (getSetting("autoWord") && !back) speakDe(wordText(g));
}
$("wsAi").onclick = async () => {
  const seq = wsSeq, btn = $("wsAi");
  btn.disabled = true; btn.textContent = "AI 正在查询…";
  let r;
  try { r = await api("/api/dict/ai", "POST", wsAsk); }
  catch (e) {
    if (seq === wsSeq) { toast(e.message); btn.disabled = false; btn.textContent = "✨ 用 AI 查询"; }
    return;
  }
  if (seq !== wsSeq) return;                 // 查询期间关掉了单词卡或点了别的词
  if (r.word) return openGlossaryWord(r.word, true);
  btn.classList.add("hidden");
  $("wsMeaning").textContent = "AI 也没有查到这个词";
};
// 加入我的词性本: 词库里的词用编号, 情景课的仓储词用德语词
$("wsNoun").onclick = async () => {
  const w = wsWord;
  if (!w) return;
  try {
    const r = await api("/api/grammar/nouns/list", "POST", w.id ? { word_id: w.id } : { text: w.german });
    toast(r.added ? "已加入词性本" : r.skipped ? "已经在词性本里了" : "没有加入");
  } catch (e) { toast(e.message); }
};
$("wsSay").onclick = () => { if (wsWord) speakDe(wordText(wsWord)); };
// 详情在单词卡里展开, 不离开当前页面, 练习进度不受影响
function wsMoreReset() {
  $("wsMore").classList.add("hidden");
  $("wsForms").textContent = ""; $("wsDetails").textContent = ""; $("wsMoreEx").textContent = "";
  $("wsView").textContent = "详情";
}
$("wsView").onclick = async () => {
  if (!wsWord || !wsWord.id) return;
  if (!$("wsMore").classList.contains("hidden")) return wsMoreReset();
  const seq = wsSeq, id = wsWord.id;
  let w;
  try { w = await api("/api/words/" + id); } catch (e) { return toast(e.message); }
  if (seq !== wsSeq) return;                 // 查询期间关掉了单词卡或点了别的词
  renderForms(w.forms, $("wsForms"));
  renderDetails(w.details, $("wsDetails"));
  exampleInto($("wsMoreEx"), w.example, null);
  $("wsFull").classList.toggle("hidden", !wsCanLeave());
  $("wsMore").classList.remove("hidden");
  $("wsView").textContent = "收起";
};
$("wsFull").onclick = () => {
  if (!wsWord || !wsWord.id) return;
  const id = wsWord.id;
  closeWordSheet();
  if (current === "view") { viewingId = id; onShow.view(); window.scrollTo(0, 0); }   // 详情页里点词: 网址不变, 要手动刷新
  else openView(id);
};
$("wsAdd").onclick = async () => {
  const w = wsWord;
  if (!w) return;
  const body = w.id ? { word_id: w.id }
    : { german: w.german, gender: w.gender, pos: w.pos, plural: w.plural, meaning: w.meaning, example: w.example || "" };
  try {
    const r = await api("/api/review/queue", "POST", body);
    w.id = r.word_id; w.learned = r.learned; w.queued = r.queued;
    if (wsWord === w) { wsButton(w); $("wsView").classList.remove("hidden"); }
    toast(r.learned ? "这个词已经学过了" : "已加入复习");
  } catch (e) { toast(e.message); }
};