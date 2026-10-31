// 句子练习: 填空 / 排序 / 中译德(不影响复习计划)
const S_MODES = {
  cloze:     { ico: "🕳️", name: "句子填空", sub: "看中文，填出句子里缺的词（要写对变位和变格）" },
  order:     { ico: "🧩", name: "连词成句", sub: "把打乱的词排成正确的句子，练语序" },
  translate: { ico: "🇩🇪", name: "中译德", sub: "看中文写出整句德语，再和例句对照" },
};
let sMode = "cloze", sq = [], si = 0;
let sAnswers = [];    // sAnswers[i] = { ok, input, picked, msg }; ok 为 null = 等用户自己判断
let sPool = [], sPicked = [];   // 排序题: 打乱后的顺序、已选的(都是 tokens 的下标)

for (const [mode, m] of Object.entries(S_MODES)) {
  $("sList").appendChild(listItem(m.ico, m.name, m.sub, () => { sMode = mode; go("squiz"); }));
}

async function sStart() {
  $("title").textContent = S_MODES[sMode].name;
  $("sqBox").classList.add("hidden");
  $("sqDone").classList.add("hidden");
  try { sq = (await api("/api/sentences?mode=" + sMode)).questions; } catch (e) { toast(e.message); return; }
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
  $("sqProgress").textContent = `第 ${si + 1} / ${sq.length} 题`;
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
  $("sqCheck").classList.remove("hidden");
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
    a = { ok: same ? true : null, picked: sPicked.slice(), msg: same ? "✔ 正确" : "和例句的语序不同，请对照：" };
  } else {
    const input = $("sqIn").value;
    if (!input.trim()) return $("sqIn").focus();
    if (sMode === "cloze") {
      const r = checkSpell({ german: q.blank.answer, gender: "" }, input);
      a = { ok: r.ok, input, msg: r.msg };
    } else {
      const same = sPlain(input) === sPlain(q.de);
      a = { ok: same ? true : null, input, msg: same ? "✔ 和例句一样" : "请和例句对照：" };
    }
  }
  sAnswers[si] = a;
  $("sqIn").readOnly = sMode !== "order";
  $("sqIn").blur();                 // 离开输入框, 快捷键才生效
  if (sMode === "order") sRenderChips();
  sShow(q, a);
  if (getSetting("autoExample")) speakDe(q.de);
}
$("sqCheck").onclick = sCheck;
$("sqNext").onclick = sCheck;

function sShow(q, a) {
  $("sqResult").textContent = a.msg;
  $("sqResult").className = a.ok === false ? "msg" : a.ok ? "ok" : "";
  $("sqDe").textContent = q.de;
  wordInto($("sqWord"), q);
  $("sqMeaning").textContent = q.meaning;
  $("sqSelf").classList.toggle("hidden", a.ok !== null);
  $("sqNext").classList.toggle("hidden", a.ok === null);
  $("sqAnswer").classList.remove("hidden");
  $("sqCheck").classList.add("hidden");
}

// 语序灵活、同一句中文有多种译法, 不一样不等于错, 所以由用户自己判断
function sSelf(ok) {
  const a = sAnswers[si];
  if (!a || a.ok !== null) return;
  a.ok = ok;
  sShow(sq[si], a);
}
$("sqSelfYes").onclick = () => sSelf(true);
$("sqSelfNo").onclick = () => sSelf(false);
$("sqSay").onclick = () => { if (si < sq.length) speakDe(sq[si].de); };
$("sqBack").onclick = () => { if (si > 0) { si--; sRender(); } };   // 只回看, 不能改答案

function sFinish() {
  const wrong = sq.filter((q, i) => !sAnswers[i].ok);
  $("sqScore").textContent = sq.length ? `得分 ${sq.length - wrong.length} / ${sq.length}` : "还没有可以出题的例句";
  const box = $("sqWrong"); box.textContent = "";
  if (wrong.length) {
    box.append("再看一遍：");
    for (const q of wrong) {
      const line = document.createElement("div");
      line.textContent = `${q.de} — ${q.zh}`;
      box.appendChild(line);
    }
  } else if (sq.length) box.textContent = "全部答对了 🎉";
  else box.textContent = "这种题需要带中文翻译的例句，换一本单词书试试。";
}

// 回车 检查 / 下一题(在输入框里也有效)
$("sqIn").onkeydown = e => {
  if (e.key !== "Enter" || e.isComposing) return;
  e.preventDefault(); e.stopPropagation(); sCheck();
};
onKey.squiz = (e, typing) => {
  if (typing || e.ctrlKey || si >= sq.length) return false;
  const a = sAnswers[si], pending = a && a.ok === null;
  if (e.key === "Enter" || e.key === " ") { sCheck(); return true; }
  if (pending && (e.key === "1" || e.key === "2")) { sSelf(e.key === "1"); return true; }
  if (a && e.key.toLowerCase() === "p") { $("sqSay").click(); return true; }
  if (sMode !== "order" || a) return false;
  if (e.key === "Backspace" && sPicked.length) { sPicked.pop(); sRenderChips(); return true; }
  const left = sPool.filter(n => !sPicked.includes(n)), n = parseInt(e.key, 10);   // 数字键 = 选剩下的第几个词
  if (n >= 1 && n <= left.length) { sPick(left[n - 1]); return true; }
  return false;
};
