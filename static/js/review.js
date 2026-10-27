// 今日复习: 认词 + 拼写, 评分交给后端的 FSRS
let cards = [], idx = 0, busy = false;
let hist = [];   // 本轮评过的卡: {idx, logId, repeat}, 「上一个」从最后一张开始撤销

const CASES = ["第一格 Nom.", "第二格 Gen.", "第三格 Dat.", "第四格 Akk."];
const PERSONS = ["ich", "du", "er/sie/es", "wir", "ihr", "sie/Sie"];

async function loadReview() {
  $("flash").textContent = "";
  $("cardBox").classList.add("hidden");
  $("done").classList.add("hidden");
  const r = await api("/api/review/today");
  cards = r.cards; idx = 0; hist = [];
  $("rStats").textContent = `复习 ${r.due} · 新词 ${r.new}`;
  render();
}
onShow.review = loadReview;

function wordInto(el, c) {
  el.textContent = "";
  if (c.gender) {
    const a = document.createElement("span");
    a.className = "art " + c.gender; a.textContent = c.gender;
    el.appendChild(a);
  }
  el.appendChild(document.createTextNode(c.german));
}

function table(head, rows) {
  const t = document.createElement("table"); t.className = "forms";
  const tr = t.insertRow();
  for (const h of head) { const th = document.createElement("th"); th.textContent = h; tr.appendChild(th); }
  for (const r of rows) { const row = t.insertRow(); for (const x of r) row.insertCell().textContent = x; }
  return scrollBox(t);   // 名词很长时(如 Geschwindigkeitsbegrenzungen)在卡片里左右滑
}

function renderForms(f, box = $("aForms")) {
  box.textContent = "";
  if (!f) return;
  if (f.cases) {
    const hasPl = f.cases.pl.some(x => x);
    box.appendChild(table(hasPl ? ["", "单数", "复数"] : ["", "单数（无复数）"],
      CASES.map((n, i) => hasPl ? [n, f.cases.sg[i], f.cases.pl[i]] : [n, f.cases.sg[i]])));
  }
  if (f.praesens) box.appendChild(table(["人称", "现在时"], PERSONS.map((p, i) => [p, f.praesens[i]])));
  if (f.past) {
    const p = document.createElement("div"); p.className = "pastline";
    p.textContent = `过去式 ${f.past[0]} · 完成时 ${f.past[1]}`;
    box.appendChild(p);
  }
}

function render() {
  const done = idx >= cards.length;
  $("cardBox").classList.toggle("hidden", done);
  $("done").classList.toggle("hidden", !done);
  $("rProgress").textContent = done ? "" : `第 ${idx + 1} / ${cards.length} 张`;
  $("btnUndo").classList.toggle("hidden", !hist.length);
  if (done) return;
  const c = cards[idx];
  const spell = c.mode === "spell";
  const art = spell && c.gender && needArticle();
  $("modeTag").textContent = spell ? "拼写：写出德语" + (art ? "（带冠词）" : "")
                                   : (c.is_new ? "新词：先想想它的意思" : "认词：想想它的意思");
  const w = $("wWord");
  if (spell) { w.className = "word prompt"; w.textContent = c.meaning; }
  else { w.className = "word"; wordInto(w, c); }
  $("wPos").textContent = c.pos || "";
  $("spellBox").classList.toggle("hidden", !spell);
  $("spellIn").value = "";
  $("btnSpeak").classList.toggle("hidden", spell);   // 拼写题先不让听, 免得泄露答案
  $("btnShow").textContent = spell ? "检查" : "显示答案";
  $("btnShow").classList.remove("hidden");
  $("aResult").textContent = "";
  wordInto($("aWord"), c);
  $("aWord").classList.toggle("hidden", !spell);
  $("aMeaning").textContent = spell ? "" : c.meaning;
  $("aPlural").textContent = c.plural && !(c.forms && c.forms.cases) ? "复数：" + c.plural : "";
  $("aExample").textContent = c.example || "";
  renderForms(c.forms);
  $("btnSpeakEx").classList.toggle("hidden", !c.example);
  $("answer").classList.add("hidden");
  if (spell) $("spellIn").focus();
  else if (getSetting("autoWord")) speakDe(wordText(c));   // 拼写题要等答完才读, 免得泄露答案
}

// 拼写判断: 忽略大小写和多余空格; ae/oe/ue/ss 代替 ä/ö/ü/ß 也算对, 但提示正确写法
const fold = s => s.toLowerCase().replace(/\s+/g, " ").trim();
const ascii = s => fold(s).replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss");
function checkSpell(c, input) {
  const art = c.gender && needArticle();
  const want = art ? c.gender + " " + c.german : c.german;
  if (!fold(input)) return { ok: false, msg: "✘ 没有作答" };
  if (fold(input) === fold(want)) return { ok: true, msg: "✔ 正确" };
  if (ascii(input) === ascii(want)) return { ok: true, msg: "✔ 正确（注意写法：" + want + "）" };
  if (art) {
    const m = fold(input).match(/^(der|die|das) (.+)$/);
    const body = m ? m[2] : fold(input);
    if (ascii(body) === ascii(c.german)) return { ok: false, msg: m ? "✘ 冠词错了" : "✘ 名词要带冠词" };
  }
  return { ok: false, msg: "✘ 答错了" };
}

function reveal() {
  if (idx >= cards.length || !$("answer").classList.contains("hidden")) return;
  const c = cards[idx];
  let show = [1, 2, 3, 4];
  if (c.mode === "spell") {
    const r = checkSpell(c, $("spellIn").value);
    $("aResult").textContent = r.msg;
    $("aResult").className = r.ok ? "ok" : "msg";
    show = r.ok ? [2, 3, 4] : [1];   // 拼错了只能记为“忘了”
    $("btnR1").textContent = r.ok ? "忘了" : "继续（记为忘了）";
  } else {
    $("btnR1").textContent = "忘了";
  }
  [1, 2, 3, 4].forEach(n => $("btnR" + n).classList.toggle("hidden", !show.includes(n)));
  $("answer").classList.remove("hidden");
  $("btnShow").classList.add("hidden");
  $("spellIn").blur();   // 让后面的 1-4 / 空格 当快捷键, 而不是打进输入框
  $("btnSpeak").classList.remove("hidden");
  if (c.mode === "spell" && getSetting("autoWord")) speakDe(wordText(c));
  if (getSetting("autoExample") && c.example) speakDe(exampleDe(c.example), true);
}

$("btnShow").onclick = reveal;
$("spellIn").onkeydown = e => { if (e.key === "Enter") reveal(); };

$("btnSpeak").onclick = () => { if (idx < cards.length) speakDe(wordText(cards[idx])); };
$("btnSpeakEx").onclick = () => { if (idx < cards.length) speakDe(exampleDe(cards[idx].example)); };

async function answer(rating) {
  if (busy || idx >= cards.length) return;
  const c = cards[idx];
  busy = true;
  let r;
  try { r = await api("/api/review/answer", "POST", { word_id: c.id, rating, mode: c.mode }); }
  catch (e) { alert(e.message); return; }
  finally { busy = false; }
  // 忘了的词排到队尾, 本轮再用拼写考一次
  const repeat = rating === 1 ? { ...c, mode: "spell", is_new: 0 } : null;
  if (repeat) cards.push(repeat);
  hist.push({ idx, logId: r.log_id, repeat });
  $("flash").textContent = c.german + (rating === 1 ? "：稍后再练一次"
    : `：${r.interval_days} 天后复习` + (r.mastered ? " · 已掌握 ✔" : ""));
  idx++; render();
}
[1, 2, 3, 4].forEach(n => $("btnR" + n).onclick = () => answer(n));

// 上一个: 撤销上一次评分(进度恢复原样), 回到那张卡重新答
async function undo() {
  if (busy || !hist.length) return;
  const h = hist.pop();
  busy = true;
  try { await api("/api/review/undo", "POST", { log_id: h.logId }); }
  catch (e) { toast(e.message); render(); return; }
  finally { busy = false; }
  if (h.repeat) cards.splice(cards.indexOf(h.repeat), 1);   // 后加的卡已先撤销, 所以它在队尾
  idx = h.idx;
  $("flash").textContent = "已撤销「" + cards[idx].german + "」的评分，请重新作答";
  render();
}
$("btnUndo").onclick = undo;

// 快捷键: 空格/回车 显示答案, 翻面后 = 良好(拼错时 = 继续); 1-4 评分; P 读单词; E 读例句
onKey.review = (e, typing) => {
  if (typing || e.ctrlKey) return false;
  if (e.key === "Backspace") { undo(); return true; }   // 做完一轮后也能撤销最后一张
  if (idx >= cards.length) return false;
  const c = cards[idx], shown = !$("answer").classList.contains("hidden");
  const visible = n => !$("btnR" + n).classList.contains("hidden");
  if (e.key === " " || e.key === "Enter") {
    if (!shown) {
      if (c.mode === "spell") $("spellIn").focus(); else reveal();
    } else answer(visible(3) ? 3 : 1);
    return true;
  }
  if (/^[1-4]$/.test(e.key)) {
    if (shown && visible(+e.key)) answer(+e.key);
    return true;
  }
  const k = e.key.toLowerCase();
  if (k === "p" && (c.mode !== "spell" || shown)) { speakDe(wordText(c)); return true; }   // 拼写题答完前不读
  if (k === "e" && shown && c.example) { speakDe(exampleDe(c.example)); return true; }
  return false;
};
$("btnReload").onclick = loadReview;
$("btnHome").onclick = () => $("btnBack").click();
