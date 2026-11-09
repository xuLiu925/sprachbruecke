// 语法基础: 知识点列表 → 知识点(说明 + 速查表 + 例句) → 练习(选择题)。内容在 grammar-data.js
let gTopic = null;                       // 正在看的知识点
let gQs = [], gi = 0, gScore = 0, gAnswered = false;
let gPicks = [], gOpts = [];             // gPicks[i] = 第 i 题的作答 {value, opts}, 回看时原样显示; gOpts = 这题显示的选项

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
    qs.push({ prompt: fillFrame(c, g, nouns), hint: `${nouns[g][0]} · ${GENDER_ZH[g]}`, options, answer, fixed: true,
              explain: `${CASE_REASON[c]}；${GENDER_ZH[g]} → ${answer}` });
  }
  return shuffle(qs).slice(0, 10);
}

// 题库在后端的知识点: 从选中的单词书或错题本出题, 取不到时用程序生成的题。fixed = 选项每题都一样, 按钮不换位置
// kind = indef / kein / poss: 不定冠词、否定冠词、物主冠词; verb / perfekt / usage: 动词现在时、完成时、搭配; 不带就是定冠词
async function bankQuiz(local, kind) {
  const url = ["verb", "perfekt", "usage"].includes(kind) ? `${gList().api}?scope=${gScopeNow}&n=14&` + tzQuery()
    : kind ? `/api/grammar/articles?type=${kind}&scope=${gScopeNow}&n=14` : `/api/grammar/nouns?scope=${gScopeNow}&n=14&` + tzQuery();
  try { return (await api(url)).questions; }
  catch (e) { toast("题库加载失败，先做基础题"); return shuffle(local); }
}

function prepQuiz(sentences) {
  return shuffle(sentences).map(([prompt, answer, explain]) =>
    ({ prompt, options: ["der", "die", "das", "den", "dem"], answer, explain, fixed: true }));
}

function verbQuiz(verbs, n) {
  const all = verbs.flatMap(v => PERSONS6.map((p, i) => ({ v, i })));
  return shuffle(all).slice(0, n).map(({ v, i }) => ({
    prompt: `${PERSONS6[i]} ___`, hint: `（${v}）`, options: [...new Set(VERBS[v])], answer: VERBS[v][i], fixed: true,
    explain: `${v}：${PERSONS6[i]} → ${VERBS[v][i]}`,
  }));
}

function orderQuiz(items) {
  return shuffle(items).map(([right, w1, w2, explain]) =>
    ({ prompt: "选出语序正确的句子", options: shuffle([right, w1, w2]), answer: right, explain, wide: true }));
}

// 疑问词题: 选疑问词 6 题; 看回答选问句、看问句选回答各 3 题
function wQuiz() {
  const words = shuffle(W_WORDS).slice(0, 6).map(([prompt, answer, options, zh, explain]) =>
    ({ prompt, answer, options, zh, explain, hint: "选疑问词" }));
  const pairs = shuffle(W_PAIRS).slice(0, 6).map(([question, reply, wrongQ, wrongA, explain, zh], i) => (i % 2
    ? { prompt: reply, answer: question, options: shuffle([question, ...wrongQ]), zh, explain, wide: true, hint: "这是回答，问句是哪一个？" }
    : { prompt: question, answer: reply, options: shuffle([reply, ...wrongA]), zh, explain, wide: true, hint: "选合适的回答" }));
  return shuffle([...words, ...pairs]);
}

// 形容词词尾题: type = weak / mixed / strong
function adjQuiz(type, n) {
  const qs = [];
  if (type === "strong") {
    for (const [c, g, sentence, adjs] of STRONG_ITEMS) {
      const adj = rand(adjs), gi = GENDER_KEYS.indexOf(g), end = STRONG_END[c][gi];
      qs.push({ prompt: sentence, hint: `（${adj}）· ${GENDER_ZH[g]}`, answer: adj + end, fixed: true,
                options: ["e", "en", "er", "es", "em"].map(e => adj + e),
                explain: `${ADJ_TYPE_NAME.strong} · ${CASE_NAMES[c]}${GENDER_ZH[g]} → -${end}` });
    }
  } else {
    const article = type === "weak" ? (c, gi) => DEF_ARTICLES[c][gi] : mixedArticle;
    const ends = type === "weak" ? WEAK_END : MIXED_END;
    for (const c of [0, 1, 2, 3]) for (const g of GENDER_KEYS) {
      const adj = rand(ADJ_PEOPLE), gi = GENDER_KEYS.indexOf(g), end = ends[c][gi];
      const prompt = ADJ_FRAMES[c][g === "pl" ? 1 : 0].replace("{a}", article(c, gi)).replace("{n}", QUIZ_NOUNS[g][c]);
      qs.push({ prompt, hint: `（${adj}）· ${GENDER_ZH[g]}`, answer: adj + end, fixed: true,
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
  "冠词": "der", "代词": "ich", "介词": "mit", "动词": "sein", "语序": "V2", "形容词词尾": "-er",
  "比较级": "gut+", "完成时": "hat", "可分动词": "an|", "否定": "nicht", "数字和时间": "12", "问句": "wer",
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
    const it = listItem({ text: GROUP_ICONS[t.group] || "?" }, t.title, t.level, () => { gTopic = t; go("gtopic"); });
    it.querySelector(".badge").replaceWith(scoreChip(bestScore(t.id)));
    list.appendChild(it);
  }
  if (gJumpGroup) {   // 从「学习」页点了某一类(home.js)
    const h = [...box.querySelectorAll("h2")].find(x => x.textContent === gJumpGroup);
    gJumpGroup = null;
    if (h) h.scrollIntoView();
  }
};

// ---------- 知识点页 ----------
const hasChinese = s => /[一-鿿]/.test(s);

// 表格里的德语: 单个词和逗号分开的词点开单词卡, 短语和句子点一下朗读
function speakableCell(td, text) {
  td.textContent = text;
  if (!text || text === "—" || text.startsWith("-") || hasChinese(text)) return;
  const words = text.split(", ");
  if (words.every(w => /^[\p{L}-]+$/u.test(w))) {
    td.textContent = "";
    words.forEach((w, i) => {
      if (i) td.append(", ");
      const b = document.createElement("button"); b.className = "tok"; b.textContent = w;
      b.onclick = () => openWordSheet(w, { de: "" });
      td.appendChild(b);
    });
    return;
  }
  td.className = "say"; td.title = "点一下朗读";
  td.onclick = () => speakDe(text);
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
    for (const line of tab.notes || []) {
      const p = document.createElement("p"); p.className = "meta left"; p.textContent = line; tb.appendChild(p);
    }
    for (const id of tab.links || []) {    // 跳到相关知识点: 网址不变, 要手动刷新这一页
      const other = GRAMMAR_TOPICS.find(x => x.id === id);
      const b = document.createElement("button"); b.className = "mini"; b.textContent = other.title;
      b.onclick = () => { gTopic = other; onShow.gtopic(); window.scrollTo(0, 0); };
      tb.appendChild(b);
    }
  }
  const ex = $("gExamples"); ex.textContent = "";
  for (const s of t.examples) {
    const row = document.createElement("div"); row.className = "exrow left";
    const b = document.createElement("button"); b.className = "mini"; b.innerHTML = ICON_SPEAK; b.setAttribute("aria-label", "朗读"); b.onclick = () => speakDe(s);
    const p = document.createElement("p"); p.textContent = s;
    row.append(b, p); ex.appendChild(row);
  }
  const best = bestScore(t.id);
  // 题库知识点的进度显示在练习范围里; 每组固定题数, 最好成绩很快就满分, 没有参考价值
  $("gStart").textContent = !user && t.bank ? "注册后练习（题目来自你的单词书）"
    : "开始练习" + (best && !t.bank ? `（上次最好 ${best[0]} / ${best[1]}）` : "");
  $("gBank").classList.toggle("hidden", !(t.adminBank && isAdmin));
  $("gScopeRow").classList.toggle("hidden", !t.bank || !user);
  if (t.bank && user) gScopeLoad();
};
$("gBank").onclick = () => go("gbank");

// 练习范围: 单词书和错题本, 放在开始按钮前, 一眼能看到现在练的是什么。选这里不改变首页的当前单词书
let gScopeNow = "", gScopeList = [];
const G_SCOPE_ICONS = { wrong: { text: "错", cls: "warm" }, warehouse: { text: "仓" }, all: { text: "全部" } };
const gList = () => ({ perfekt: PERFEKT_LIST, usage: USAGE_LIST }[gTopic.verb] || (gTopic.verb ? VERB_LIST : NOUN_LIST));
async function gScopeLoad() {
  let r;
  try { r = await api(gList().api + "/books"); } catch (e) { return toast(e.message); }
  gScopeList = scopeItems(r);
  const saved = getSetting("gScope");
  gScopeNow = gScopeList.some(x => x.id === saved) ? saved : r.current;   // 以前选的“学过的词”这类范围已经没有了
  gScopeShow();
}
function gScopeShow() {
  scopeInto($("gScope"), gScopeList, gScopeNow, id => { gScopeNow = id; setSetting("gScope", id); gScopeShow(); }, id => gnOpen(id, gList()));
}
// 定冠词和复数练习共用: 后端返回的范围 → 列表项, 再画出来
function scopeItems(r) {
  return [...r.books.map(b => ({ id: b.book, name: BOOK_NAMES[b.book] || b.book,
                                 sub: `已掌握 ${b.mastered} · 已练 ${b.practiced} / ${b.nouns}` + (b.weak ? ` · 待巩固 ${b.weak}` : "") })),
          { id: "wrong", name: "错题本", sub: `${r.wrong} 个词` }];
}
function scopeInto(box, list, now, pick, open) {
  box.textContent = "";
  for (const s of list) {
    const it = listItem(G_SCOPE_ICONS[s.id] || { text: s.id.length <= 3 ? s.id : "书" }, s.name, s.sub, () => pick(s.id));
    it.classList.toggle("current", s.id === now);
    const see = document.createElement("span"); see.className = "scopesee"; see.textContent = "查看";
    see.onclick = e => { e.stopPropagation(); open(s.id); };
    it.replaceChild(see, it.lastChild);
    box.appendChild(it);
  }
}
$("gStart").onclick = () => {
  if (!user && gTopic && gTopic.bank) return openLogin("reg", "这个练习按你的单词书出题，注册后就能做");
  go("gquiz");
};

// ---------- 练习 ----------
onShow.gquiz = async () => {
  if (!gTopic) return location.replace("#grammar");
  $("title").textContent = gTopic.title;
  $("gqBox").classList.add("hidden");
  $("gqDone").classList.add("hidden");
  gQs = await gTopic.quiz(); gi = 0; gScore = 0; gPicks = [];
  $("gqHints").checked = getSetting("gHints");
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

// 把 ___ 显示成空格; answered 时按顺序填上答案, 答案和其他词一样能点
// ein / kein / 物主冠词的答案按词形查不准(meinen 会查到动词), 用题目带的原形和说明
function promptInto(el, q, answered) {
  el.textContent = "";
  const fill = answered ? q.fill || q.answer : "";
  const parts = q.prompt.split("___"), f = fill ? fill.split(" … ") : [];
  const known = q.answer_lemma ? { map: { [q.answer]: q.answer_lemma }, notes: { [q.answer]: q.answer_note } } : {};
  parts.forEach((p, i) => {
    lessonTokens(el, { de: p });        // 题目里的德语词能点, 看释义
    if (i < parts.length - 1) {
      const s = document.createElement("span"); s.className = "blank" + (fill ? " filled" : "");
      if (f[i]) lessonTokens(s, { ...known, de: f[i] });
      else s.textContent = "    ";
      el.appendChild(s);
    }
  });
}

// 题库知识点可以关掉词性提示; 自动出的题关掉后还留着单复数, 否则同形的词有两个答案
function gHint() {
  if (gi >= gQs.length) return;
  const q = gQs[gi], on = !gTopic.bank || getSetting("gHints") || gAnswered;
  $("gqHint").textContent = (on ? q.hint : q.must) || "";
}
$("gqHints").onchange = () => { setSetting("gHints", $("gqHints").checked); gHint(); };

function gRender() {
  if (gi >= gQs.length) return gDone();
  const q = gQs[gi];
  gAnswered = false;
  $("gqProgress").textContent = `第 ${gi + 1} / ${gQs.length} 题` + (q.retry ? " · 错题再练一次" : "");
  $("gqHintRow").classList.toggle("hidden", !gTopic.bank);
  $("gqHintText").textContent = gTopic.hintLabel || "显示词性提示";
  promptInto($("gqPrompt"), q);
  $("gqSent").textContent = gTopic.bank ? q.zh || "" : "";   // 题库题做题时就显示翻译: 中文没有冠词, 不会泄露答案
  gHint();
  let opts = q.options;
  if (opts.length > 6) {
    const pick = new Set([q.answer, ...shuffle(opts.filter(o => o !== q.answer)).slice(0, 3)]);
    opts = q.fixed ? opts.filter(o => pick.has(o)) : shuffle([...pick]);    // 选项太多时抽 4 个, 固定题保持原来的先后
  } else if (!q.wide && !q.fixed) opts = shuffle(opts);
  const seen = gPicks[gi];
  if (seen) opts = seen.opts;            // 回看: 选项和答题时一样
  gOpts = opts;
  const box = $("gqOpts"); box.textContent = "";
  box.className = "opts" + (q.wide ? " wide" : opts.length === 2 || opts.length === 4 ? " two" : "");   // 2 个或 4 个选项排成两列
  opts.forEach((o, i) => {
    const b = document.createElement("button"); b.className = "secondary";
    b.textContent = (q.wide ? `${i + 1}. ` : "") + o; b.dataset.value = o;
    b.onclick = () => gChoose(o);
    box.appendChild(b);
  });
  $("gqFeedback").classList.add("hidden");
  $("gqGiveUp").classList.remove("hidden");
  $("gqPrev").classList.toggle("hidden", gi === 0);
  if (seen) gShowAnswer(seen.value);
}

// 冠词题答错的原因: gender = 词性记错了, case = 词性没错, 格或词尾用错了(复数的冠词不分词性, 只可能是格)
// ein / kein / 物主冠词的题点“不会”不算词性错: 更可能是词尾没记住
// 动词题: stem = 词形没记住, person = 人称用错了; 点“不会”时词干要变或不规则的算词形
// 完成时和搭配的题带 kinds: 每个错误选项的错因(aux 助动词, part 过去分词, person 人称, prep 介词, case 格);
// 点“不会”算 skip_kind, 没写就是过去分词
function gErrKind(q, value) {
  if (q.kinds) return value === q.answer ? null : value === null ? q.skip_kind || "part" : q.kinds[value] || null;
  if (q.verb) {
    if (value === q.answer) return null;
    return (value === null ? q.stem_picks.length : q.stem_picks.includes(value)) ? "stem" : "person";
  }
  if (!q.gender_picks || value === q.answer) return null;
  if (value === null) return q.must === "复数" || q.article ? "case" : "gender";
  return q.gender_picks.includes(value) ? "gender" : "case";
}

// value = null 表示点了“不会”: 直接看答案, 算答错
function gChoose(value) {
  if (gAnswered) return;
  const q = gQs[gi];
  if (!q.retry) {                        // 得分只算第一次; 题库知识点的错题排到最后再练一次
    const ok = value === q.answer;
    if (ok) gScore++;
    else if (gTopic.bank) gQs.push({ ...q, retry: true });
    if (q.verb) api(gList().api + "/result", "POST", { word_id: q.word_id, ok, person: q.person,
                    kind: gErrKind(q, value), hinted: !!getSetting("gHints") }).catch(() => {});
    else if (q.word_id) api("/api/grammar/nouns/result?" + tzQuery(), "POST", { word_id: q.word_id, ok, must: q.must, case: q.case,
                       kind: gErrKind(q, value), hinted: !!getSetting("gHints"), cell: q.cell }).catch(() => {});
  }
  gPicks[gi] = { value, opts: gOpts };
  gShowAnswer(value);
}

function gShowAnswer(value) {
  gAnswered = true;
  const q = gQs[gi], ok = value === q.answer;
  if (!ok && q.word_id) tipOnce("tip_wrong", "做错的题会自动进错题本，在「练习」页最上面能专门练。");
  document.querySelectorAll("#gqOpts button").forEach(b => {
    b.disabled = true;
    if (b.dataset.value === q.answer) b.className = "good";
    else if (b.dataset.value === value) b.className = "bad";
  });
  if (!q.wide) promptInto($("gqPrompt"), q, true);
  gHint();
  const why = { gender: "词性错了，", case: q.article ? "词尾用错了，" : "格用错了，", stem: "词形错了，", person: "人称错了，",
                aux: "助动词错了，", part: "过去分词错了，", prep: "介词错了，" }[gErrKind(q, value)] || "";
  $("gqResult").textContent = ok ? "✓ 正确" : (value === null ? "不会，正确答案：" : `✗ ${why}正确答案：`) + q.answer;
  $("gqResult").className = ok ? "ok" : "msg";
  $("gqZh").textContent = gTopic.bank ? "" : q.zh || "";
  $("gqExplain").textContent = q.explain || "";
  const noun = (q.hint || "").match(/^(der|die|das) ([^ ·]+)/);     // 提示写着 die Palette · 阴性 的题
  genderReason($("gqGender"), noun && noun[2], noun && noun[1], q.meaning || "");
  const explainable = gTopic.id === "art-def" || (q.verb && !q.short);      // 动词的短题 du ___ 不是句子, 不用讲解
  exampleExplain($("gqGender"), explainable ? `${gSentence()}\n${q.zh || ""}` : "");   // 讲解填好答案的整句
  $("gqGiveUp").classList.add("hidden");
  $("gqCard").classList.toggle("hidden", !q.verb);                   // 卡片里有变位表, 答完才给看
  $("gqReport").classList.toggle("hidden", !q.id && !q.word_id);     // 题库题和自动出的题能报错
  $("gqFeedback").classList.remove("hidden");
}
$("gqGiveUp").onclick = () => gChoose(null);
$("gqCard").onclick = () => { const q = gQs[gi]; if (q.verb) openWordId(q.word_id, q.german); };
$("gqReport").onclick = async () => {
  const reason = (prompt("这题哪里有问题？") || "").trim();
  if (!reason) return;
  const q = gQs[gi];
  try {
    if (q.id) await api(`/api/grammar/questions/${q.id}/report`, "POST", { reason });
    else await api("/api/grammar/nouns/report", "POST", { word_id: q.word_id, prompt: q.prompt, reason });
    toast("已记录");
  } catch (e) { toast(e.message); }
};

function gSentence() {   // 题目填好答案后的德语(用来朗读)
  const q = gQs[gi];
  if (q.plain) return q.prompt;                      // 可分 / 不可分: 读动词本身
  if (q.wide || / = ___$/.test(q.prompt)) return q.answer;   // 选句子、数字、钟点: 读答案
  return fillBlanks(q.prompt, q.fill || q.answer);
}
$("gqSay").onclick = () => speakDe(gSentence());
$("gqNext").onclick = () => { gi++; gRender(); };
$("gqPrev").onclick = () => { if (gi > 0) { gi--; gRender(); } };   // 只回看, 不能改答案

// 这一组错得最多的格子(ein / kein / 物主冠词), 只看第一次作答
function gWeakCell() {
  const count = {};
  gQs.forEach((q, i) => {
    if (q.cell_name && !q.retry && gPicks[i] && gPicks[i].value !== q.answer) count[q.cell_name] = (count[q.cell_name] || 0) + 1;
  });
  const top = Object.entries(count).sort((a, b) => b[1] - a[1])[0];
  return top ? `错得最多：${top[0]}（${top[1]} 题）。` : "";
}

function gDone() {
  $("gqBox").classList.add("hidden");
  $("gqDone").classList.remove("hidden");
  const total = gQs.filter(q => !q.retry).length;      // 错题重练不计入总分
  if (!total) {
    $("gqScore").textContent = "这个范围还没有词";
    $("gqDoneMsg").textContent = gScopeNow === "wrong" ? "错题本是空的，换个范围继续练。" : "换个练习范围试试。";
    return;
  }
  $("gqScore").textContent = `得分 ${gScore} / ${total}`;
  const best = bestScore(gTopic.id);
  if (!best || gScore / total > best[0] / best[1]) {
    try { localStorage.setItem("sb_gbest_" + gTopic.id, JSON.stringify([gScore, total])); } catch (e) {}
  }
  pathSaveGrammar(gTopic.id, gScore, total);   // path.js: 存到服务器(学习路径看它算完成), 服务器只留最好的
  $("gqDoneMsg").textContent = gScore === total ? "全对了" : gWeakCell() + "错的地方回到速查表再看一眼，再练一次。";
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
  if (e.key === "Backspace") { $("gqPrev").click(); return true; }
  if (!gAnswered && e.key === "?") { gChoose(null); return true; }
  if (!gAnswered && /^[1-9]$/.test(e.key)) {
    const b = document.querySelectorAll("#gqOpts button")[+e.key - 1];
    if (b) { b.click(); return true; }
  }
  if (gAnswered && (e.key === "Enter" || e.key === " ")) { $("gqNext").click(); return true; }
  if (gAnswered && e.key.toLowerCase() === "d" && gQs[gi].verb) { $("gqCard").click(); return true; }
  return false;
};
