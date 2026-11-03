// 今日学习: 先复习到期的词, 再学新词; 认词 + 拼写, 评分交给后端的 FSRS
let cards = [], idx = 0, busy = false, leftToday = 0;
let hist = [];   // 本轮评过的卡: {idx, logId, repeat}, 「上一个」从最后一张开始撤销
// 试学(没登录): 卡片来自 /api/trial/cards, 评分只记在本机, 登录或注册后由 core.js 的 saveTrial() 交给服务器
const TRIAL_KEY = "sb_trial";
let trial = false, trialAnswers = [];
function trialStore() { try { localStorage.setItem(TRIAL_KEY, JSON.stringify(trialAnswers)); } catch (e) {} }

const CASES = ["第一格 Nom.", "第二格 Gen.", "第三格 Dat.", "第四格 Akk."];
const PERSONS = ["ich", "du", "er/sie/es", "wir", "ihr", "sie/Sie"];

async function loadReview() {
  $("flash").textContent = "";
  $("cardBox").classList.add("hidden");
  $("done").classList.add("hidden");
  trial = !user;
  if (trial) {
    const r = await api("/api/trial/cards");
    cards = r.cards; idx = 0; hist = []; trialAnswers = [];
    $("rStats").textContent = `试学 ${cards.length} 个词 · 不用注册`;
    return render();
  }
  const r = await api("/api/review/today?" + tzQuery());
  cards = r.cards; idx = 0; hist = [];
  $("rStats").textContent = `复习 ${r.due} · 新词 ${r.new}`;
  render();
}
onShow.review = loadReview;

function render() {
  const done = idx >= cards.length;
  $("cardBox").classList.toggle("hidden", done);
  $("done").classList.toggle("hidden", !done);
  $("rProgress").textContent = done ? "" : `第 ${idx + 1} / ${cards.length} 张`;
  $("btnUndo").classList.toggle("hidden", !hist.length);
  if (done) return showDone();
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
  $("btnCard").classList.add("hidden");
  $("aResult").textContent = "";
  fillWordCard("a", c, { pos: false });   // 答案区, 和单词卡共用(wordcard.js)
  $("aWord").classList.toggle("hidden", !spell);
  if (spell) $("aMeaning").textContent = "";   // 拼写题的释义就是题目
  $("btnSpeakEx").classList.toggle("hidden", !c.example);
  $("answer").classList.add("hidden");
  if (spell) $("spellIn").focus();
  else if (getSetting("autoWord")) speakDe(wordText(c));   // 拼写题要等答完才读, 免得泄露答案
}

// 一轮有上限, 今天还有词时显示“继续学习”, 学完了才是“再学 10 个”
async function showDone() {
  $("doneSub").textContent = "";
  if (trial) {
    trialStore();
    const n = new Set(trialAnswers.map(a => a.word_id)).size;
    $("doneMsg").textContent = `试学完成，学了 ${n} 个词 🎉`;
    $("doneSub").textContent = "注册后保存这些词的进度，明天按记忆曲线提醒你复习，还能从 A1 单词书接着学。";
    $("btnReload").textContent = "免费注册，保存进度";
    $("btnHome").textContent = "回首页";
    return;
  }
  $("doneMsg").textContent = "今天的学习完成了 🎉";
  $("btnReload").textContent = "再学 10 个";
  leftToday = 0;
  let t;
  try { t = await api("/api/today?" + tzQuery()); } catch (e) { return; }
  leftToday = t.due + t.new;
  if (leftToday) {
    $("doneMsg").textContent = `这一轮完成了，今天还有 ${leftToday} 个词`;
    $("btnReload").textContent = "继续学习";
  }
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
  $("btnCard").classList.toggle("hidden", trial);   // 单词卡要登录(/api/words)
  if (c.mode === "spell" && getSetting("autoWord")) speakDe(wordText(c));
  if (getSetting("autoExample") && c.example) speakDe(exampleDe(c.example), true);
}

$("btnShow").onclick = reveal;
$("spellIn").onkeydown = e => { if (e.key === "Enter") reveal(); };

$("btnSpeak").onclick = () => { if (idx < cards.length) speakDe(wordText(cards[idx])); };
$("btnSpeakEx").onclick = () => { if (idx < cards.length) speakDe(exampleDe(cards[idx].example)); };
$("btnCard").onclick = () => { if (idx < cards.length) openWordId(cards[idx].id, cards[idx].german); };

async function answer(rating) {
  if (busy || idx >= cards.length) return;
  const c = cards[idx];
  if (trial) return trialAnswer(c, rating);
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

// 试学的评分: 不发给服务器, 只记下来; 下次复习的天数注册后才算
const TRIAL_FLASH = { 2: "有点难，过一两天再复习", 3: "记住了，过几天再复习", 4: "很简单，过一段时间再复习" };
function trialAnswer(c, rating) {
  const repeat = rating === 1 ? { ...c, mode: "spell", is_new: 0 } : null;
  if (repeat) cards.push(repeat);
  trialAnswers.push({ word_id: c.id, rating, mode: c.mode });
  hist.push({ idx, repeat, trial: true });
  $("flash").textContent = c.german + "：" + (rating === 1 ? "稍后再练一次" : TRIAL_FLASH[rating]);
  idx++; render();
}

// 上一个: 撤销上一次评分(进度恢复原样), 回到那张卡重新答
async function undo() {
  if (busy || !hist.length) return;
  const h = hist.pop();
  if (h.trial) trialAnswers.pop();
  else {
  busy = true;
  try { await api("/api/review/undo", "POST", { log_id: h.logId }); }
  catch (e) { toast(e.message); render(); return; }
  finally { busy = false; }
  }
  if (h.repeat) cards.splice(cards.indexOf(h.repeat), 1);   // 后加的卡已先撤销, 所以它在队尾
  idx = h.idx;
  $("flash").textContent = "已撤销「" + cards[idx].german + "」的评分，请重新作答";
  render();
}
$("btnUndo").onclick = undo;

// 快捷键: 空格/回车 显示答案, 翻面后 = 良好(拼错时 = 继续); 1-4 评分; P 读单词; E 读例句; D 单词卡
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
  if (k === "d" && shown) { $("btnCard").click(); return true; }
  return false;
};
$("btnReload").onclick = async () => {
  if (trial) return openLogin("reg", "注册后试学的词会保存到你的进度");
  if (!leftToday) {
    try { await api("/api/today/more?" + tzQuery(), "POST", {}); } catch (e) { return toast(e.message); }
  }
  await loadReview();
  if (!cards.length) toast("这本书的新词学完了，换一本吧");
};
$("btnHome").onclick = () => $("btnBack").click();
