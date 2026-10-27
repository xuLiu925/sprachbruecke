// 语法基础: 知识点列表 → 知识点(说明 + 速查表 + 例句) → 练习(选择题)。内容在 grammar-data.js
let gTopic = null;                       // 正在看的知识点
let gQs = [], gi = 0, gScore = 0, gAnswered = false;

const rand = arr => arr[Math.floor(Math.random() * arr.length)];
function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}
const GENDER_KEYS = ["m", "f", "n", "pl"];
const GENDER_ZH = { m: "阳性", f: "阴性", n: "中性", pl: "复数" };

// ---------- 出题 ----------
function fillFrame(c, g, nouns) {
  return CASE_FRAMES[c][g === "pl" ? 1 : 0].replace("{n}", nouns[g][c]);
}

function articleQuiz(form, nouns, cases, genders) {
  const options = [...new Set(cases.flatMap(c => genders.map(g => form(c, GENDER_KEYS.indexOf(g)))))];
  const qs = [];
  for (const c of cases) for (const g of genders) {
    const answer = form(c, GENDER_KEYS.indexOf(g));
    qs.push({ prompt: fillFrame(c, g, nouns), hint: `${nouns[g][0]} · ${GENDER_ZH[g]}`, options, answer,
              explain: `${CASE_REASON[c]}；${GENDER_ZH[g]} → ${answer}` });
  }
  return shuffle(qs).slice(0, 10);
}

function prepQuiz(sentences) {
  return shuffle(sentences).map(([prompt, answer, explain]) =>
    ({ prompt, options: ["der", "die", "das", "den", "dem"], answer, explain }));
}

function verbQuiz(verbs, n) {
  const all = verbs.flatMap(v => PERSONS6.map((p, i) => ({ v, i })));
  return shuffle(all).slice(0, n).map(({ v, i }) => ({
    prompt: `${PERSONS6[i]} ___`, hint: `（${v}）`, options: [...new Set(VERBS[v])], answer: VERBS[v][i],
    explain: `${v}：${PERSONS6[i]} → ${VERBS[v][i]}`,
  }));
}

function orderQuiz(items) {
  return shuffle(items).map(([right, w1, w2, explain]) =>
    ({ prompt: "选出语序正确的句子", options: shuffle([right, w1, w2]), answer: right, explain, wide: true }));
}

// 形容词词尾题: type = weak / mixed / strong
function adjQuiz(type, n) {
  const qs = [];
  if (type === "strong") {
    for (const [c, g, sentence, adjs] of STRONG_ITEMS) {
      const adj = rand(adjs), gi = GENDER_KEYS.indexOf(g), end = STRONG_END[c][gi];
      qs.push({ prompt: sentence, hint: `（${adj}）· ${GENDER_ZH[g]}`, answer: adj + end,
                options: ["e", "en", "er", "es", "em"].map(e => adj + e),
                explain: `${ADJ_TYPE_NAME.strong} · ${CASE_NAMES[c]}${GENDER_ZH[g]} → -${end}` });
    }
  } else {
    const article = type === "weak" ? (c, gi) => DEF_ARTICLES[c][gi] : mixedArticle;
    const ends = type === "weak" ? WEAK_END : MIXED_END;
    for (const c of [0, 1, 2, 3]) for (const g of GENDER_KEYS) {
      const adj = rand(ADJ_PEOPLE), gi = GENDER_KEYS.indexOf(g), end = ends[c][gi];
      const prompt = ADJ_FRAMES[c][g === "pl" ? 1 : 0].replace("{a}", article(c, gi)).replace("{n}", QUIZ_NOUNS[g][c]);
      qs.push({ prompt, hint: `（${adj}）· ${GENDER_ZH[g]}`, answer: adj + end,
                options: ["e", "en", "er", "es", "em"].map(e => adj + e),
                explain: `${ADJ_TYPE_NAME[type]} · ${CASE_NAMES[c]}${GENDER_ZH[g]} → -${end}` });
    }
  }
  return shuffle(qs).slice(0, n);
}

// 比较级题: 给原级, 选比较级或最高级(错误选项是手写的常见错法)
function compFormQuiz(n) {
  return shuffle(COMPARISON).slice(0, n).map(([base, komp, sup, kWrong, sWrong, rule]) => {
    const isSup = Math.random() < 0.5;
    return { prompt: `${base} → ___`, hint: isSup ? "最高级" : "比较级",
             answer: isSup ? sup : komp, options: isSup ? [sup, ...sWrong] : [komp, ...kWrong],
             explain: `${base} → ${komp} → ${sup}（${rule}）` };
  });
}

// ---------- 数字(numWord 在 grammar-data.js 里) ----------
function numberQuiz() {
  // 听德语写数字(21–99): 错误选项里有个位、十位写反的
  const qs = [], used = new Set();
  while (qs.length < 8) {
    const t = 2 + Math.floor(Math.random() * 8), u = 1 + Math.floor(Math.random() * 9), n = t * 10 + u;
    if (u === t || used.has(n)) continue;
    used.add(n);
    const options = [n, u * 10 + t, (t === 9 ? t - 1 : t + 1) * 10 + u, t * 10 + (u === 9 ? u - 1 : u + 1)].map(String);
    qs.push({ prompt: `${numWord(n)} = ___`, hint: "写成数字", answer: String(n), options,
              explain: `${numWord(n)}：先说个位 ${u}，再说十位 ${t * 10} → ${n}` });
  }
  for (const [digit, right, w1, w2, explain] of shuffle(NUMBER_SPELLING).slice(0, 6)) {
    qs.push({ prompt: `${digit} = ___`, hint: "哪个写法对？", answer: right, options: [right, w1, w2], explain });
  }
  return shuffle(qs);
}

// ---------- 钟点 ----------
const HOURS = ["zwölf", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf"];
const hourWord = h => HOURS[((h - 1) % 12 + 12) % 12 + 1];   // 0 → zwölf, 13 → eins
const CLOCK_MINUTES = [0, 5, 10, 15, 25, 30, 35, 45, 50, 55];   // 20、40 各地说法不一样, 不出题
function timePhrase(h, m) {   // 口语说法, h = 1..12
  switch (m) {
    case 0: return (h === 1 ? "ein" : hourWord(h)) + " Uhr";
    case 5: return "fünf nach " + hourWord(h);
    case 10: return "zehn nach " + hourWord(h);
    case 15: return "Viertel nach " + hourWord(h);
    case 25: return "fünf vor halb " + hourWord(h + 1);
    case 30: return "halb " + hourWord(h + 1);
    case 35: return "fünf nach halb " + hourWord(h + 1);
    case 45: return "Viertel vor " + hourWord(h + 1);
    case 50: return "zehn vor " + hourWord(h + 1);
    case 55: return "fünf vor " + hourWord(h + 1);
  }
}
const TIME_RULES = {
  0: "整点：几 + Uhr（1 点是 ein Uhr）", 5: "过了几分：fünf nach + 这个钟点", 10: "过了几分：zehn nach + 这个钟点",
  15: "过一刻：Viertel nach + 这个钟点", 25: "差 5 分到“半”：fünf vor halb + 下一个钟点",
  30: "halb + 下一个钟点（halb vier = 3:30）", 35: "过“半” 5 分：fünf nach halb + 下一个钟点",
  45: "差一刻：Viertel vor + 下一个钟点", 50: "差几分：zehn vor + 下一个钟点", 55: "差几分：fünf vor + 下一个钟点",
};
const MIRROR = { 0: 30, 5: 55, 10: 50, 15: 45, 25: 35, 30: 0, 35: 25, 45: 15, 50: 10, 55: 5 };

function timeQuiz() {
  const qs = [], used = new Set();
  while (qs.length < 8) {
    const h = 1 + Math.floor(Math.random() * 12), m = rand(CLOCK_MINUTES), key = h + ":" + m;
    if (used.has(key)) continue;
    used.add(key);
    const prev = h === 1 ? 12 : h - 1, next = h === 12 ? 1 : h + 1;
    // 错误选项: 钟点差一个(halb 最常见的错)、前后弄反
    const options = [...new Set([timePhrase(h, m), timePhrase(prev, m), timePhrase(next, m), timePhrase(h, MIRROR[m])])];
    const shown = `${h}:${String(m).padStart(2, "0")}`;
    qs.push({ prompt: `${shown} = ___`, hint: "口语说法", answer: timePhrase(h, m), options,
              explain: `${shown} = ${timePhrase(h, m)}（${TIME_RULES[m]}）` });
  }
  for (const [prompt, hint, answer, options, explain] of shuffle(DATE_ITEMS).slice(0, 4)) {
    qs.push({ prompt, hint, answer, options, explain });
  }
  return shuffle(qs);
}

// ---------- 知识点列表 ----------
function bestScore(id) {
  try { return JSON.parse(localStorage.getItem("sb_gbest_" + id)); } catch (e) { return null; }
}

const GROUP_ICONS = {
  "冠词": "📝", "代词": "👤", "介词": "📍", "动词": "🔁", "语序": "🧩", "形容词词尾": "🎨",
  "比较级": "📈", "完成时": "⏪", "可分动词": "✂️", "否定": "🚫", "数字和时间": "🔢",
};

// 练习成绩标签: 全对绿色, 六成以上蓝色, 不到六成橙色, 没练过灰色
function scoreChip(b) {
  const c = document.createElement("span");
  if (!b) { c.className = "chip"; c.textContent = "未练"; return c; }
  const r = b[0] / b[1];
  c.className = "chip " + (r === 1 ? "mastered" : r >= 0.6 ? "learning" : "weak");
  c.textContent = `${b[0]} / ${b[1]}`;
  return c;
}

onShow.grammar = () => {
  const box = $("gList"); box.textContent = "";
  let group = null, list = null;
  for (const t of GRAMMAR_TOPICS) {
    if (t.group !== group) {
      group = t.group;
      const h = document.createElement("h2"); h.textContent = group; box.appendChild(h);
      list = document.createElement("div"); list.className = "list"; box.appendChild(list);
    }
    const it = listItem(GROUP_ICONS[t.group] || "📐", t.title, t.level, () => { gTopic = t; go("gtopic"); });
    it.querySelector(".badge").replaceWith(scoreChip(bestScore(t.id)));
    list.appendChild(it);
  }
};

// ---------- 知识点页 ----------
const hasChinese = s => /[一-鿿]/.test(s);

function speakableCell(td, text) {
  td.textContent = text;
  if (text && text !== "—" && !text.startsWith("-") && !hasChinese(text)) {
    td.className = "say"; td.title = "点一下朗读";
    td.onclick = () => speakDe(text);
  }
}

onShow.gtopic = () => {
  if (!gTopic) return location.replace("#grammar");   // 直接刷新这一页时没有选中的知识点
  const t = gTopic;
  $("title").textContent = t.title;
  $("gLevel").textContent = t.group + " · " + t.level;
  const intro = $("gIntro"); intro.textContent = "";
  for (const line of t.intro) { const li = document.createElement("li"); li.textContent = line; intro.appendChild(li); }
  const tb = $("gTables"); tb.textContent = "";
  for (const tab of t.tables) {
    if (tab.title) {   // 一个知识点有好几张表时, 每张表的小标题
      const h = document.createElement("h3"); h.className = "gtitle"; h.textContent = tab.title; tb.appendChild(h);
    }
    const table = document.createElement("table"); table.className = "forms gtable";
    const hr = table.insertRow();
    for (const h of tab.head) { const th = document.createElement("th"); th.textContent = h; hr.appendChild(th); }
    for (const row of tab.rows) {
      const tr = table.insertRow();
      row.forEach((x, i) => { const td = tr.insertCell(); if (i === 0) td.textContent = x; else speakableCell(td, x); });
    }
    tb.appendChild(scrollBox(table));
  }
  const ex = $("gExamples"); ex.textContent = "";
  for (const s of t.examples) {
    const row = document.createElement("div"); row.className = "exrow left";
    const b = document.createElement("button"); b.className = "mini"; b.textContent = "🔊"; b.onclick = () => speakDe(s);
    const p = document.createElement("p"); p.textContent = s;
    row.append(b, p); ex.appendChild(row);
  }
  const best = bestScore(t.id);
  $("gStart").textContent = "开始练习" + (best ? `（上次最好 ${best[0]} / ${best[1]}）` : "");
};
$("gStart").onclick = () => go("gquiz");

// ---------- 练习 ----------
onShow.gquiz = () => {
  if (!gTopic) return location.replace("#grammar");
  $("title").textContent = gTopic.title;
  gQs = gTopic.quiz(); gi = 0; gScore = 0;
  $("gqBox").classList.remove("hidden");
  $("gqDone").classList.add("hidden");
  gRender();
};

// 题目里的 ___ 是空; 有几个空, 答案就用 " … " 隔开写几段(如 "bin … gefahren")
function fillBlanks(text, answer) {
  const f = answer.split(" … ");
  let k = 0;
  return text.replace(/___/g, () => f[k++] ?? "");
}

function promptInto(el, text, fill) {   // 把 ___ 显示成空格(答完后按顺序填上答案)
  el.textContent = "";
  const parts = text.split("___"), f = fill ? fill.split(" … ") : [];
  parts.forEach((p, i) => {
    el.append(p);
    if (i < parts.length - 1) {
      const s = document.createElement("span"); s.className = "blank" + (fill ? " filled" : "");
      s.textContent = f[i] || "    "; el.appendChild(s);
    }
  });
}

function gRender() {
  if (gi >= gQs.length) return gDone();
  const q = gQs[gi];
  gAnswered = false;
  $("gqProgress").textContent = `第 ${gi + 1} / ${gQs.length} 题`;
  promptInto($("gqPrompt"), q.prompt);
  $("gqHint").textContent = q.hint || "";
  let opts = q.options;
  if (opts.length > 6) opts = shuffle([q.answer, ...shuffle(opts.filter(o => o !== q.answer)).slice(0, 3)]);
  else if (!q.wide) opts = shuffle(opts);
  const box = $("gqOpts"); box.textContent = "";
  box.className = "opts" + (q.wide ? " wide" : opts.length === 2 || opts.length === 4 ? " two" : "");   // 2 个或 4 个选项排成两列
  opts.forEach((o, i) => {
    const b = document.createElement("button"); b.className = "secondary";
    b.textContent = (q.wide ? `${i + 1}. ` : "") + o; b.dataset.value = o;
    b.onclick = () => gChoose(o);
    box.appendChild(b);
  });
  $("gqFeedback").classList.add("hidden");
}

function gChoose(value) {
  if (gAnswered) return;
  gAnswered = true;
  const q = gQs[gi], ok = value === q.answer;
  if (ok) gScore++;
  document.querySelectorAll("#gqOpts button").forEach(b => {
    b.disabled = true;
    if (b.dataset.value === q.answer) b.className = "good";
    else if (b.dataset.value === value) b.className = "bad";
  });
  if (!q.wide) promptInto($("gqPrompt"), q.prompt, q.answer);
  $("gqResult").textContent = ok ? "✔ 正确" : "✘ 正确答案：" + q.answer;
  $("gqResult").className = ok ? "ok" : "msg";
  $("gqExplain").textContent = q.explain || "";
  $("gqFeedback").classList.remove("hidden");
}

function gSentence() {   // 题目填好答案后的德语(用来朗读)
  const q = gQs[gi];
  if (q.plain) return q.prompt;                      // 可分 / 不可分: 读动词本身
  if (q.wide || / = ___$/.test(q.prompt)) return q.answer;   // 选句子、数字、钟点: 读答案
  return fillBlanks(q.prompt, q.answer);
}
$("gqSay").onclick = () => speakDe(gSentence());
$("gqNext").onclick = () => { gi++; gRender(); };

function gDone() {
  $("gqBox").classList.add("hidden");
  $("gqDone").classList.remove("hidden");
  $("gqScore").textContent = `得分 ${gScore} / ${gQs.length}`;
  const best = bestScore(gTopic.id);
  if (!best || gScore / gQs.length > best[0] / best[1]) {
    try { localStorage.setItem("sb_gbest_" + gTopic.id, JSON.stringify([gScore, gQs.length])); } catch (e) {}
  }
  $("gqDoneMsg").textContent = gScore === gQs.length ? "全对了 🎉" : "错的地方回到速查表再看一眼，再练一次。";
}
$("gqAgain").onclick = () => onShow.gquiz();
$("gqBack").onclick = () => $("btnBack").click();

// 快捷键: 数字键选答案, 回车 / 空格 下一题
onKey.gquiz = (e, typing) => {
  if (typing || e.ctrlKey) return false;
  if (!$("gqDone").classList.contains("hidden")) {
    if (e.key === "Enter") { onShow.gquiz(); return true; }
    return false;
  }
  if (!gAnswered && /^[1-9]$/.test(e.key)) {
    const b = document.querySelectorAll("#gqOpts button")[+e.key - 1];
    if (b) { b.click(); return true; }
  }
  if (gAnswered && (e.key === "Enter" || e.key === " ")) { $("gqNext").click(); return true; }
  return false;
};
