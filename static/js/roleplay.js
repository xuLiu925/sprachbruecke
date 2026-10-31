// 角色扮演和整句复习: 只听对方的话, 限时开口回答, 再和参考回答对照、自评。评分进 FSRS
let rpSource = null;     // 课程编号; null = 整句复习(到期的句子)
let rpItems = [], rpI = 0, rpTimer = null, rpRevealed = false, rpDone = 0, rpAgain = new Set();

function rpOpen(lessonId) { rpSource = lessonId; go("roleplay"); }

function rpStopTimer() {
  clearTimeout(rpTimer); rpTimer = null;
  const bar = $("rpBar"); bar.style.transition = "none"; bar.style.width = "0";
}
window.addEventListener("hashchange", rpStopTimer);

onShow.roleplay = async () => {
  $("title").textContent = rpSource ? "角色扮演" : "整句复习";
  $("rpBox").classList.add("hidden");
  $("rpDone").classList.add("hidden");
  try {
    const url = rpSource ? "/api/roleplay/lesson/" + rpSource : "/api/roleplay/due";
    rpItems = (await api(url)).items;
  } catch (e) { return toast(e.message); }
  rpI = 0; rpDone = 0; rpAgain = new Set();
  rpRender();
};
$("rpRestart").onclick = () => onShow.roleplay();

// 给的时间跟句子长度走: 读完对方的话, 再想一想、说出来
function rpSeconds(it) {
  const n = s => s.split(/\s+/).length;
  return Math.round(4 + n(it.prompt) * 0.5 + n(it.answer) * 0.7);
}
function rpStartTimer(it) {
  rpStopTimer();
  const sec = rpSeconds(it), bar = $("rpBar");
  bar.style.width = "100%";
  void bar.offsetWidth;                 // 让浏览器先画满, 下面的动画才会开始
  bar.style.transition = `width ${sec}s linear`;
  bar.style.width = "0";
  rpTimer = setTimeout(rpReveal, sec * 1000);
}

function rpRender() {
  rpStopTimer();
  const done = rpI >= rpItems.length;
  $("rpBox").classList.toggle("hidden", done);
  $("rpDone").classList.toggle("hidden", !done);
  if (done) return rpFinish();
  const it = rpItems[rpI];
  rpRevealed = false;
  $("rpProgress").textContent = `第 ${rpI + 1} / ${rpItems.length} 句 · ${it.level} ${it.title}`;
  $("rpWho").textContent = it.who + " 对你说：";
  $("rpHint").classList.add("hidden");
  $("rpHint").textContent = "你要表达：" + it.answer_zh;
  $("rpReveal").classList.add("hidden");
  $("rpAsk").classList.remove("hidden");
  speakDe(it.prompt);
  rpStartTimer(it);
}

function rpPlay(rate) {
  if (rpI >= rpItems.length) return;
  speakDe(rpItems[rpI].prompt, false, rate);
  if (!rpRevealed) rpStartTimer(rpItems[rpI]);      // 重听时重新计时
}
$("rpReplay").onclick = () => rpPlay();
$("rpSlow").onclick = () => rpPlay(0.6);
$("rpShowHint").onclick = () => $("rpHint").classList.remove("hidden");

function rpReveal() {
  if (rpI >= rpItems.length || rpRevealed) return;
  rpStopTimer();
  rpRevealed = true;
  const it = rpItems[rpI];
  $("rpPromptDe").textContent = it.prompt;
  $("rpPromptZh").textContent = it.prompt_zh;
  $("rpAnswerDe").textContent = it.answer;
  $("rpAnswerZh").textContent = it.answer_zh;
  $("rpAsk").classList.add("hidden");
  $("rpReveal").classList.remove("hidden");
  speakDe(it.answer);
}
$("rpShow").onclick = rpReveal;
$("rpSayAnswer").onclick = () => { if (rpI < rpItems.length) speakDe(rpItems[rpI].answer); };
$("rpSayPrompt").onclick = () => rpPlay();

async function rpRate(rating) {
  if (!rpRevealed || rpI >= rpItems.length) return;
  const it = rpItems[rpI];
  try { await api("/api/roleplay/answer", "POST", { key: it.key, rating }); }
  catch (e) { return toast(e.message); }
  if (rating === 1) { rpAgain.add(it.key); rpItems.push(it); }   // 没说出来: 本组最后再练一次
  else rpDone++;
  rpI++;
  rpRender();
}
document.querySelectorAll("#rpRate button").forEach(b => b.onclick = () => rpRate(+b.dataset.r));

function rpFinish() {
  stopSpeak();
  if (!rpItems.length) {
    $("rpScore").textContent = rpSource ? "这一课没有对话练习" : "现在没有要复习的句子 🎉";
    $("rpNote").textContent = rpSource ? "" : "在情景课里做过角色扮演的句子，到期后会出现在这里。";
    return;
  }
  $("rpScore").textContent = `练完了 ${rpDone} 句`;
  $("rpNote").textContent = rpAgain.size
    ? `其中 ${rpAgain.size} 句第一次没说出来，已经多练了一遍，之后会更早复习。`
    : "全部说出来了 🎉 这些句子之后会按计划复习。";
}

// 空格 / 回车 看答案; 1 2 3 评分; R 重听, S 慢速
onKey.roleplay = (e, typing) => {
  if (typing || e.ctrlKey || rpI >= rpItems.length) return false;
  if (rpRevealed && ["1", "2", "3"].includes(e.key)) { rpRate(+e.key); return true; }
  if (e.key === " " || e.key === "Enter") { rpReveal(); return true; }
  const k = e.key.toLowerCase();
  if (k === "r") { rpPlay(); return true; }
  if (k === "s") { rpPlay(0.6); return true; }
  return false;
};
