// 学习路径: A1 → C1 每一级学什么、学到哪了、下一步做什么。后端 learn_path.py, 文档 docs/features/learning-path.md
// 进度都用已有数据算: 单词书学过的词、语法知识点的最好成绩(grammar.js 每组做完存到服务器)、情景课学完的课
let pathData = null, pathLevel = null, pathLessons = null;

// 以前的语法成绩只在本机(sb_gbest_知识点): 第一次打开时传到服务器, 传过一次就不再传
async function pathSyncLocal() {
  try { if (localStorage.getItem("sb_gbest_synced")) return; } catch (e) { return; }
  const items = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (!k.startsWith("sb_gbest_") || k === "sb_gbest_synced") continue;
      const v = JSON.parse(localStorage.getItem(k));
      if (Array.isArray(v) && v.length === 2) items.push([k.slice(9), v[0], v[1]]);
    }
  } catch (e) { return; }
  try {
    if (items.length) await api("/api/path/grammar", "POST", { items });
    localStorage.setItem("sb_gbest_synced", "1");
  } catch (e) {}
}
// grammar.js 的 gDone: 每组做完记一次(服务器只留最好的)
function pathSaveGrammar(id, score, total) {
  if (user && total) api("/api/path/grammar", "POST", { items: [[id, score, total]] }).catch(() => {});
}

async function pathLoad() {
  await pathSyncLocal();
  const [p, l] = await Promise.all([api("/api/path"), pathLessons ? null : api("/api/lessons").catch(() => null)]);
  pathData = p;
  if (l) pathLessons = Object.fromEntries(l.lessons.map(x => [x.id, x]));
  return p;
}

const pathTopic = id => GRAMMAR_TOPICS.find(t => t.id === id);
const pathCount = arr => arr.filter(x => x.done).length;
const pathWordsLeft = lv => Math.max(lv.words.goal - lv.words.learned, 0);

// 下一步: 单词、语法、情景课三部分里完成比例最低的那一部分, 比例一样时语法 > 情景课 > 单词
function pathNext(lv) {
  const cands = [];
  const g = lv.grammar.find(x => !x.done), l = lv.lessons.find(x => !x.done);
  if (g) {
    const t = pathTopic(g.id);
    cands.push({ r: pathCount(lv.grammar) / lv.grammar.length, text: "语法：" + (t ? t.title : g.id), go: () => openTopic(g.id) });
  }
  if (l) {
    const info = pathLessons && pathLessons[l.id];
    cands.push({ r: pathCount(lv.lessons) / lv.lessons.length, text: "情景课：" + (info ? info.title : l.id),
                 go: () => openLesson(info || { id: l.id }) });
  }
  if (pathWordsLeft(lv) > 0) {
    cands.push({ r: lv.words.learned / lv.words.goal, text: `单词：${lv.level} 还差 ${pathWordsLeft(lv)} 个`, go: () => pathStudyWords(lv.level) });
  }
  if (!cands.length) return { text: `${lv.level} 学完了，去下一级`, go: () => { pathLevel = null; go("path"); } };
  return cands.reduce((a, b) => (b.r < a.r ? b : a));
}

// 学单词: 当前单词书不是这一级时先换过来, 再进今日学习
async function pathStudyWords(level) {
  if (pathData && pathData.book !== level) {
    try { await api("/api/books/current", "POST", { book: level }); } catch (e) { return toast(e.message); }
    pathData.book = level;
    toast(`单词书已换成 ${BOOK_NAMES[level] || level}`);
  }
  go("review");
}

// 今天页和学习页的卡片(前缀 h / l)
async function showPathCard(pre) {
  let p;
  try { p = await pathLoad(); } catch (e) { return; }
  const lv = p.levels.find(x => x.level === p.current);
  const next = pathNext(lv);
  $(pre + "PathTag").textContent = lv.level;
  $(pre + "PathPct").textContent = `完成 ${lv.percent}%`;
  $(pre + "PathNext").textContent = "下一步 · " + next.text;
  $(pre + "PathBar").style.width = lv.percent + "%";
  $(pre + "Path").onclick = () => { pathLevel = null; go("path"); };
  if ($(pre + "PathBox")) $(pre + "PathBox").classList.remove("hidden");
}

onShow.path = async () => {
  let p;
  try { p = await pathLoad(); } catch (e) { return toast(e.message); }
  pathRender(pathLevel || p.current);
};

function pathRender(level) {
  const p = pathData;
  pathLevel = level;
  const lv = p.levels.find(x => x.level === level);
  // 级别切换: 现在这一级标出来, 学完的打勾
  const chips = $("paLevels"); chips.textContent = "";
  for (const x of p.levels) {
    const b = document.createElement("button");
    b.textContent = `${x.level}${x.percent >= 100 ? " ✓" : x.level === p.current ? " · 现在" : ""}`;
    b.classList.toggle("on", x.level === level);
    b.onclick = () => pathRender(x.level);
    chips.appendChild(b);
  }
  $("paTitle").textContent = lv.level + (lv.level === p.current ? "（现在在学）" : "");
  $("paPct").textContent = `完成 ${lv.percent}%`;
  $("paBar").style.width = lv.percent + "%";
  const next = pathNext(lv);
  $("paNext").textContent = next.text;
  $("paNext").onclick = next.go;

  // 单词
  const w = lv.words;
  $("paWordsT").textContent = `${BOOK_NAMES[lv.level] || lv.level} 单词书`;
  $("paWordsN").textContent = w.total ? `学过 ${w.learned} / 目标 ${w.goal}（共 ${w.total}）` : "还没有这一级的单词书";
  $("paWordsBar").style.width = (w.goal ? Math.min(w.learned / w.goal, 1) * 100 : 0) + "%";
  const otherBook = p.book !== lv.level;
  $("paBookNote").classList.toggle("hidden", !otherBook || !w.total);
  $("paBookNote").textContent = otherBook ? `现在的单词书是 ${BOOK_NAMES[p.book] || p.book}，点下面的按钮会换成 ${lv.level}。` : "";
  $("paWordsGo").textContent = pathWordsLeft(lv) ? (otherBook ? `换成 ${lv.level} 单词书并开始学` : "去今日学习")
                                                 : "单词已达标，去今日学习复习";
  $("paWordsGo").disabled = !w.total;
  $("paWordsGo").onclick = () => pathStudyWords(lv.level);

  // 语法
  $("paGrammarBox").classList.toggle("hidden", !lv.grammar.length);
  $("paGrammarT").textContent = `语法（${pathCount(lv.grammar)} / ${lv.grammar.length}）`;
  const gb = $("paGrammar"); gb.textContent = "";
  for (const g of lv.grammar) {
    const t = pathTopic(g.id);
    if (!t) continue;
    const sub = g.done ? `已完成 · 最好 ${g.best[0]} / ${g.best[1]}`
              : g.best ? `最好 ${g.best[0]} / ${g.best[1]}，再练到 80% 以上` : "还没练";
    const it = listItem({ text: g.done ? "✓" : (GROUP_ICONS[t.group] || "?"), cls: g.done ? "das" : "" }, t.title, sub, () => openTopic(g.id));
    gb.appendChild(it);
  }
  // 情景课
  $("paLessonBox").classList.toggle("hidden", !lv.lessons.length);
  $("paLessonT").textContent = `情景课（${pathCount(lv.lessons)} / ${lv.lessons.length}）`;
  const lb = $("paLessons"); lb.textContent = "";
  for (const l of lv.lessons) {
    const info = (pathLessons && pathLessons[l.id]) || { id: l.id, title: l.id, scene: "" };
    lb.appendChild(listItem({ text: l.done ? "✓" : "课", cls: l.done ? "das" : "" }, info.title,
                            l.done ? "已学完" : (info.scene || "还没学完"), () => openLesson(info)));
  }
  $("paSoon").classList.toggle("hidden", lv.grammar.length || lv.lessons.length);
  $("paSoon").textContent = `${lv.level} 的语法和情景课还在准备中，现在先背这一级的单词。`;

  // 巩固练习: 用这一级单词书出题(不计进度)
  const ex = $("paExtra"); ex.textContent = "";
  const sent = mode => () => { setSetting("sMode", mode); setSetting("sScope", lv.level); go("sentence"); };
  for (const [tile, name, sub, fn] of [
    [{ text: "__" }, "句子填空", "用学过的词填句子", sent("cloze")],
    [{ text: "句" }, "句子听力", "听整句，写出空里的词", sent("listen")],
    [{ text: "听" }, "单词听写", "听发音写单词", () => { setSetting("dScope", lv.level); go("dictation"); }],
    [{ text: "说" }, "整句复习", "情景课里的句子，限时开口说", () => rpOpen(null)],
  ]) ex.appendChild(listItem(tile, name, sub, fn));
}
