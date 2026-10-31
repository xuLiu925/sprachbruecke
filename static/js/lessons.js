// 情景课: 读课文(点词看详情) → 练习 → 用德语写出来。内容在 static/lessons.json, 完成记录存本机
let lessons = null, lessonNow = null, lessonShown = null, wsSeq = 0, wsWord = null, lessonAi = false;
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
function closeWordSheet() { $("wsheet").classList.add("hidden"); wsWord = null; wsSeq++; }
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
  return lessonNow.glossary.find(hit) || lessons.flatMap(l => l.glossary).find(hit);
}

async function openWordSheet(token, line) {
  const seq = ++wsSeq;
  const lemma = (line.map && line.map[token]) || LESSON_FORMS[token.toLowerCase()] || token;
  const gl = lessonGlossary(lemma);
  $("wsheet").classList.remove("hidden");
  $("wsWord").textContent = token;
  $("wsPlural").textContent = ""; $("wsMeaning").textContent = "查询中…"; $("wsLesson").textContent = "";
  $("wsAdd").classList.add("hidden"); $("wsView").classList.add("hidden"); $("wsSay").classList.add("hidden");
  let found = null;
  try { found = (await api("/api/lookup?w=" + encodeURIComponent(gl ? gl.german : lemma))).word; }
  catch (e) { if (seq === wsSeq) toast(e.message); }
  if (seq !== wsSeq) return;                 // 查询期间又点了别的词
  const w = found || gl;
  if (!w) {
    wsWord = null;
    $("wsMeaning").textContent = "词库里没有这个词";
    return;
  }
  wsWord = found ? { ...w } : { ...gl, learned: false, queued: false };
  wordInto($("wsWord"), w);
  $("wsPlural").textContent = [w.pos, w.plural ? "复数 " + w.plural : "", token !== w.german ? "文中是 " + token : ""]
    .filter(Boolean).join(" · ");
  $("wsMeaning").textContent = w.meaning;
  if (gl && found && gl.meaning !== found.meaning) $("wsLesson").textContent = "在仓库里：" + gl.meaning;
  $("wsSay").classList.remove("hidden");
  $("wsAdd").classList.remove("hidden"); wsButton(wsWord);
  $("wsView").classList.toggle("hidden", !found);
  if (getSetting("autoWord")) speakDe(wordText(w));
}
$("wsSay").onclick = () => { if (wsWord) speakDe(wordText(wsWord)); };
$("wsView").onclick = () => { if (wsWord && wsWord.id) openView(wsWord.id); };
$("wsAdd").onclick = async () => {
  const w = wsWord;
  if (!w) return;
  const body = w.id ? { word_id: w.id } : { german: w.german, gender: w.gender, pos: w.pos, plural: w.plural, meaning: w.meaning };
  try {
    const r = await api("/api/review/queue", "POST", body);
    w.id = r.word_id; w.learned = r.learned; w.queued = r.queued;
    if (wsWord === w) { wsButton(w); $("wsView").classList.remove("hidden"); }
    toast(r.learned ? "这个词已经学过了" : "已加入复习");
  } catch (e) { toast(e.message); }
};