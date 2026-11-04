// 情景课: 读课文(点词看详情) → 练习 → 用德语写出来。列表(含词表)来自 /api/lessons, 课文打开时才取, 完成记录存本机
let lessons = null, lessonNow = null, lessonShown = null, wsSeq = 0, wsWord = null, lessonAi = false, lessonMember = false;
let wsStack = [], wsNow = null, wsLoads = Promise.resolve();   // 单词卡看过的词, 返回时重新打开
let wsAsk = null;     // 单词卡要交给 AI 查的 {q, context}
const LESSON_LEVELS = { A1: "A1 入门", A2: "A2 基础", B1: "B1 进阶" };

// 学习进度存在服务器(lessons.py 的 /api/lessons/progress): last = 最近打开的课, done = 学完的课
let lessonState = { last: null, done: [] };

async function loadLessons() {
  if (lessons) return lessons;
  const [r, mine] = await Promise.all([api("/api/lessons"), api("/api/custom_lessons")]);
  lessons = [...mine.lessons, ...r.lessons];
  lessonAi = mine.ai; lessonMember = mine.member;
  lessonState = { last: r.last, done: r.done || [] };
  // 以前“学完了”存在本机浏览器里: 没上传过的搬到服务器, 然后清掉本机的
  const local = Object.keys(getSetting("lessonDone") || {}).filter(id => !lessonState.done.includes(id));
  if (local.length) {
    try {
      lessonState.done = (await api("/api/lessons/progress", "POST", { done: local })).done;
      setSetting("lessonDone", {});
    } catch (e) {}
  }
  return lessons;
}
const lessonDone = () => Object.fromEntries(lessonState.done.map(id => [id, true]));

function lessonProgress(body) {   // 记进度, 失败不打扰(下次学完 / 打开会再记)
  api("/api/lessons/progress", "POST", body).then(r => { lessonState = { last: r.last, done: r.done }; }).catch(() => {});
}

// 打开一节课: 自带课程这时才取全文(免费版每天能开的新课有限, billing.py), 并记为最近打开的课
async function openLesson(l) {
  let full = l;
  if (!l.custom) {
    try { full = (await api("/api/lessons/" + encodeURIComponent(l.id))).lesson; }
    catch (e) { return e.status === 402 || toast(e.message); }
  }
  lessonState.last = l.id;
  lessonProgress({ last: l.id });
  lessonNow = full; go("lesson");
}

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
      list.appendChild(listItem(done[l.id] ? { text: "✓", cls: "das" } : { text: ico }, l.title, l.scene, () => openLesson(l)));
    }
    box.append(h, list);
  };
  section("我的工作对话", all.filter(x => x.custom), "我的");
  for (const [lv, name] of Object.entries(LESSON_LEVELS)) {
    section(name, all.filter(x => x.level === lv && !x.custom), lv);
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
  const say = iconButton("mini", "朗读这一句", "听");
  say.onclick = () => speakDe(line.de);
  const tr = document.createElement("button"); tr.className = "mini"; tr.textContent = "中文";
  tr.onclick = () => zh.classList.toggle("hidden");
  const note = document.createElement("div"); note.className = "lnote hidden";
  const ex = document.createElement("button"); ex.className = "mini"; ex.textContent = "讲解";
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
    const de = document.createElement("button"); de.className = "lmodel"; de.innerHTML = ICON_SPEAK; de.append(m.de);
    de.onclick = () => speakDe(m.de);
    const zh = document.createElement("div"); zh.className = "lzh"; zh.textContent = m.zh;
    row.append(de, zh); model.appendChild(row);
  }
};

$("lShowModel").onclick = () => {
  $("lModel").classList.remove("hidden");
  $("lShowModel").classList.add("hidden");
  if (!lessonState.done.includes(lessonNow.id)) {
    lessonState.done.push(lessonNow.id);
    lessonProgress({ done: [lessonNow.id] });
  }
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
  spellReset($("wsSpell"));
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
  if (prev.wordId) await openWordId(prev.wordId, prev.label, true);
  else if (prev.glossary) openGlossaryWord(prev.glossary, true, true);
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
  b.textContent = w.learned ? "已经学过" : w.queued ? "已加入学习" : "加入学习";
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
  const btn = document.createElement("button"); btn.className = "mini"; btn.textContent = "讲解";
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
  $("wsPlural").textContent = ""; $("wsMeaning").textContent = "查询中…";
  $("wsLesson").textContent = (line.notes && line.notes[token]) || "";   // 冠词题的答案: 说明词形怎么来的
  $("wsExample").textContent = "";
  $("wsAlts").classList.add("hidden");
  wsMoreReset();
  genderReason($("wsGender"), "", "");
  wordParts($("wsParts"), "");
  spellReset($("wsSpell")); $("wsSpellBtn").classList.add("hidden");
  $("wsAdd").classList.add("hidden"); $("wsView").classList.add("hidden"); $("wsSay").classList.add("hidden");
  $("wsAi").classList.add("hidden"); $("wsNoun").classList.add("hidden");
  try { await loadLessons(); } catch (e) {}   // 复习页里可能还没加载过课程; 没有仓储词表也能查词
  if (seq !== wsSeq) return;
  const gl = lessonGlossary(lemma);
  let found = null, alts = [];
  try { ({ word: found, alts = [] } = await api("/api/lookup?w=" + encodeURIComponent(gl ? gl.german : lemma))); }
  catch (e) {
    if (seq !== wsSeq) return;
    if (e.status === 401 && !user) { closeWordSheet(); return openLogin("reg", "注册后可以查所有单词"); }   // 游客只能查试学的词
    toast(e.message);
  }
  if (seq !== wsSeq) return;                 // 查询期间又点了别的词
  if (found && !found.id && gl) found = null;   // 课文词表里有就用词表的(仓储词的意思更准)
  if (found && !found.id) {                  // 词库没有、词典有: 显示词典词条, 可以加入学习
    openGlossaryWord(found, true, back);
    const notes = ["词典里的词，还没进词库"];
    if (token.toLowerCase() !== found.german.toLowerCase()) notes.push("文中是 " + token);
    $("wsLesson").textContent = notes.join("；");
    return wsAltsShow(alts, line);
  }
  const w = found || gl;
  if (!w) {
    wsWord = null;
    let r = {};
    try { r = await api("/api/dict?q=" + encodeURIComponent(lemma)); } catch (e) {}
    if (seq !== wsSeq) return;
    const saved = (r.words || []).find(x => x.ai_word);    // 以前用 AI 查过
    if (saved) return openGlossaryWord(saved, true, back);
    $("wsMeaning").textContent = "词库里没有这个词";
    if (r.gen && r.ai) {                                   // 点了才调用 AI, 人名这类词不用查
      wsAsk = { q: lemma, context: line.de };
      $("wsAi").disabled = false; $("wsAi").textContent = "用 AI 查询";
      $("wsAi").classList.remove("hidden");
    }
    return;
  }
  wsWord = found ? { ...w } : { ...gl, learned: false, queued: false };
  wsLoads = fillWordCard("ws", w, { forms: false, example: false, note: token !== w.german ? "文中是 " + token : "" });
  if (gl && found && gl.meaning !== found.meaning) $("wsLesson").textContent = "在仓库里：" + gl.meaning;
  $("wsSay").classList.remove("hidden");
  $("wsAdd").classList.remove("hidden"); wsButton(wsWord);
  $("wsNoun").classList.toggle("hidden", !w.gender);
  $("wsView").classList.toggle("hidden", !found);
  if (getSetting("autoWord") && !back) speakDe(wordText(w));
  if (found) wsAltsShow(alts, line);
}
// 同一个词形对得上几个原形时(regnet: regnen / regen), 自动选了常用的那个, 这里给出其他的
function wsAltsShow(alts, line) {
  const box = $("wsAlts");
  box.textContent = "";
  box.classList.toggle("hidden", !alts.length);
  if (!alts.length) return;
  box.append("不是这个词？");
  for (const a of alts) {
    const b = document.createElement("button");
    b.className = "linkbtn"; b.textContent = a;
    b.onclick = () => openWordSheet(a, { de: line.de });
    box.append(" ", b);
  }
}
// 查词结果里的仓储词: 不用查询, 内容都在手上
// keep = 还是同一张卡(查词的结果), 不算打开新词; back = 从下一张卡返回, 不再朗读
function openGlossaryWord(g, keep = false, back = false) {
  if (!keep) wsEnter({ glossary: g, label: g.german });
  wsSeq++;
  wsWord = { ...g, id: null, learned: false, queued: false };
  wsMoreReset();
  $("wsAlts").classList.add("hidden");
  $("wsAi").classList.add("hidden");
  $("wsheet").classList.remove("hidden");
  wsLoads = fillWordCard("ws", g, { forms: false, example: false });
  $("wsExample").textContent = g.example || "";
  $("wsLesson").textContent = g.ai_word ? "AI 生成，未核对" : "";
  $("wsSay").classList.remove("hidden");
  $("wsView").classList.add("hidden");
  $("wsAdd").classList.remove("hidden"); wsButton(wsWord);
  $("wsNoun").classList.toggle("hidden", !g.gender);
  if (getSetting("autoWord") && !back) speakDe(wordText(g));
}
// 按编号打开, 同形词(der See / die See)不会找错。不朗读; 学过的词不放“加入学习”, 今日学习的新词已在计划里, 也不放
async function openWordId(id, label, back = false) {
  if (!back) wsEnter({ wordId: id, label });
  const seq = ++wsSeq;
  let w;
  try { w = await api("/api/words/" + id); }
  catch (e) { if (seq === wsSeq) { closeWordSheet(); toast(e.message); } return; }
  if (seq !== wsSeq) return;                 // 查询期间关掉了单词卡或点了别的词
  openGlossaryWord(w, true, true);
  wsWord = { ...w };
  $("wsExample").textContent = "";           // 例句在详情里, 可以点词
  wsButton(wsWord);
  $("wsAdd").classList.toggle("hidden", w.status !== "new" || current === "review");
  $("wsView").classList.remove("hidden");
  if (!back) wsMoreFill(w);                  // 返回时由 wsBack 按原来的状态展开
}
$("wsAi").onclick = async () => {
  const seq = wsSeq, btn = $("wsAi");
  btn.disabled = true; btn.textContent = "AI 正在查询…";
  let r;
  try { r = await api("/api/dict/ai", "POST", wsAsk); }
  catch (e) {
    if (seq === wsSeq) { toast(e.message); btn.disabled = false; btn.textContent = "用 AI 查询"; }
    return;
  }
  if (seq !== wsSeq) return;                 // 查询期间关掉了单词卡或点了别的词
  if (r.word) return openGlossaryWord(r.word, true);
  btn.classList.add("hidden");
  $("wsMeaning").textContent = "AI 也没有查到这个词";
};
// 加入错题本: 词库里的词用编号, 自建对话的词用德语词
$("wsNoun").onclick = async () => {
  const w = wsWord;
  if (!w) return;
  try {
    const r = await api("/api/grammar/nouns/list", "POST", w.id ? { word_id: w.id } : { text: w.german });
    toast(r.added ? "已加入错题本" : r.skipped ? "已经在错题本里了" : "没有加入");
  } catch (e) { toast(e.message); }
};
$("wsSay").onclick = () => { if (wsWord) speakDe(wordText(wsWord)); };
$("wsSpellBtn").onclick = () => { if (wsWord) spellWord(wsWord.german, $("wsSpell")); };
// 详情在单词卡里展开, 不离开当前页面, 练习进度不受影响
function wsMoreReset() {
  $("wsMore").classList.add("hidden");
  $("wsForms").textContent = ""; $("wsDetails").textContent = ""; $("wsMoreEx").textContent = "";
  $("wsView").textContent = "详情";
}
function wsMoreFill(w) {
  fillWordMore("ws", w);
  exampleInto($("wsMoreEx"), w.example, null);
  $("wsFull").classList.toggle("hidden", !wsCanLeave());
  $("wsMore").classList.remove("hidden");
  $("wsView").textContent = "收起";
}
$("wsView").onclick = async () => {
  if (!wsWord || !wsWord.id) return;
  if (!$("wsMore").classList.contains("hidden")) return wsMoreReset();
  const seq = wsSeq, id = wsWord.id;
  let w;
  try { w = await api("/api/words/" + id); } catch (e) { return toast(e.message); }
  if (seq !== wsSeq) return;                 // 查询期间关掉了单词卡或点了别的词
  wsMoreFill(w);
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
  if (w.needs_meaning) {                     // 词典有这个词但没有中文释义: 写上才能加入, 只有他能看到
    const meaning = (prompt(`「${w.german}」的中文释义：`) || "").trim();
    if (!meaning) return;
    try { await api("/api/words", "POST", { german: w.german, gender: w.gender, meaning }); }
    catch (e) { return toast(e.message); }
    w.queued = true; wsButton(w); toast("已加入今日学习");
    return;
  }
  const body = w.id ? { word_id: w.id }
    : { german: w.german, gender: w.gender, pos: w.pos, plural: w.plural, meaning: w.meaning, example: w.example || "" };
  try {
    const r = await api("/api/review/queue", "POST", body);
    w.id = r.word_id; w.learned = r.learned; w.queued = r.queued;
    if (wsWord === w) { wsButton(w); $("wsView").classList.remove("hidden"); }
    toast(r.learned ? "这个词已经学过了" : "已加入今日学习");
  } catch (e) { toast(e.message); }
};