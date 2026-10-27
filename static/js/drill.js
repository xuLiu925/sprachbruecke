// 冠词练习(不影响复习计划)
let drill = [], di = 0, score = 0, drillPicks = [], drillToView = false;   // drillPicks[i] = 第 i 题选的冠词, "?" = 点了不会
const drillBtns = document.querySelectorAll("#drillBtns button");
const drillAnswered = () => di < drill.length && drillPicks[di] != null;

async function startDrill() {
  $("btnDrill").classList.add("hidden");
  $("drillInfo").classList.add("hidden");
  try { drill = (await api("/api/drill/articles")).words; } catch (e) { $("drillMsg").textContent = e.message; return; }
  di = 0; score = 0; drillPicks = [];
  drillRender();
}
// 从“详情”返回时接着做这一组, 不重新开始
onShow.drill = () => { if (drillToView) drillToView = false; else startDrill(); };
window.addEventListener("hashchange", () => {   // 从详情去了别的页面(不是编辑), 下次进来就重新开始
  if (!["drill", "view", "edit"].includes(location.hash.slice(1))) drillToView = false;
});
$("btnDrill").onclick = startDrill;

function drillRender() {
  $("drillMsg").textContent = ""; $("drillMsg").className = "meta";
  $("drillInfo").classList.add("hidden");
  $("btnDrillBack").classList.toggle("hidden", di === 0);
  if (di >= drill.length) {
    $("drillWord").textContent = drill.length ? `得分 ${score} / ${drill.length}` : "词库里还没有名词";
    $("drillMeaning").textContent = ""; $("drillProgress").textContent = "";
    $("drillBtns").classList.add("hidden");
    $("btnDrill").classList.remove("hidden");
    $("btnDrillBack").classList.toggle("hidden", !drill.length);
    return;
  }
  $("btnDrill").classList.add("hidden");
  const w = drill[di];
  $("drillProgress").textContent = `${di + 1} / ${drill.length}`;
  $("drillWord").textContent = w.german;
  $("drillMeaning").textContent = w.meaning;
  $("drillBtns").classList.remove("hidden");
  drillBtns.forEach(b => b.disabled = drillAnswered());
  if (drillAnswered()) drillShowAnswer(false);   // 用“上一个”回来看的题: 直接显示当时的结果
}

// 答完不自动跳: 显示带冠词的词、复数、例句, 读一遍(答题前不读, 免得听出冠词)
function drillShowAnswer(speak) {
  const w = drill[di], ok = drillPicks[di] === w.gender;
  $("drillMsg").textContent = ok ? "✔ 正确"
    : drillPicks[di] === "?" ? `应该是 ${w.gender}` : `✘ 你选了 ${drillPicks[di]}，应该是 ${w.gender}`;
  $("drillMsg").className = ok ? "ok" : "msg";
  drillBtns.forEach(x => x.disabled = true);
  wordInto($("dWord"), w);
  $("dPlural").textContent = w.plural ? "复数：" + w.plural : "";
  $("dExample").textContent = w.example || "";
  $("btnDrillEx").classList.toggle("hidden", !w.example);
  $("drillInfo").classList.remove("hidden");
  if (!speak) return;
  if (getSetting("autoWord")) speakDe(wordText(w));
  if (getSetting("autoExample") && w.example) speakDe(exampleDe(w.example), true);
}

drillBtns.forEach(b => b.onclick = () => {
  if (di >= drill.length || drillAnswered()) return;
  drillPicks[di] = b.dataset.art;
  if (b.dataset.art === drill[di].gender) score++;
  drillShowAnswer(true);
});

function drillNext() { if (drillAnswered()) { di++; drillRender(); } }
function drillBack() { if (di > 0) { di--; drillRender(); } }   // 只回看, 不能改答案(分数不变)
$("btnDrillNext").onclick = drillNext;
$("btnDrillBack").onclick = drillBack;
$("btnDrillSpeak").onclick = () => { if (drillAnswered()) speakDe(wordText(drill[di])); };
$("btnDrillEx").onclick = () => { if (drillAnswered()) speakDe(exampleDe(drill[di].example)); };
$("btnDrillView").onclick = () => { if (drillAnswered()) { drillToView = true; openView(drill[di].id); } };

// 快捷键: 1 der / 2 die / 3 das; 答完后 空格/回车 下一个, P 读单词, E 读例句; Backspace 上一个; 做完一组后回车 = 再来一组
onKey.drill = (e, typing) => {
  if (typing || e.ctrlKey) return false;
  const art = { "1": "der", "2": "die", "3": "das", "4": "?" }[e.key];   // 4 = 不会
  if (art && di < drill.length && !drillAnswered()) {
    document.querySelector(`#drillBtns [data-art="${art}"]`).click();
    return true;
  }
  if (e.key === "Backspace") { drillBack(); return true; }
  if (e.key === " " || e.key === "Enter") {
    if (drillAnswered()) drillNext();
    else if (!$("btnDrill").classList.contains("hidden")) startDrill();
    return true;
  }
  if (!drillAnswered()) return false;
  const k = e.key.toLowerCase(), w = drill[di];
  if (k === "p") { speakDe(wordText(w)); return true; }
  if (k === "e" && w.example) { speakDe(exampleDe(w.example)); return true; }
  return false;
};
