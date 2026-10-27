// 听写: 听发音写单词(不影响复习计划)
let dict = [], dj = 0, dAnswers = [];   // dAnswers[i] = 第 i 个词的作答 {input, r}, 没答过是 undefined

async function startDictation() {
  $("dictBox").classList.add("hidden");
  $("dictDone").classList.add("hidden");
  try { dict = (await api("/api/drill/dictation")).words; } catch (e) { toast(e.message); return; }
  dj = 0; dAnswers = [];
  $("dictBox").classList.remove("hidden");
  dictRender();
}
onShow.dictation = startDictation;
$("dictAgain").onclick = startDictation;

function dictRender() {
  $("dictBack").classList.toggle("hidden", dj === 0);
  const done = dj >= dict.length;
  $("dictBox").classList.toggle("hidden", done);
  $("dictDone").classList.toggle("hidden", !done);
  if (done) {
    const wrong = dict.filter((w, i) => !dAnswers[i].r.ok);
    $("dictScore").textContent = dict.length ? `得分 ${dict.length - wrong.length} / ${dict.length}` : "还没有可以听写的词";
    const box = $("dictWrong"); box.textContent = "";
    if (wrong.length) {
      box.append("写错的词：");
      for (const w of wrong) {
        const line = document.createElement("div");
        line.textContent = `${wordText(w)} — ${w.meaning}`;
        box.appendChild(line);
      }
    } else if (dict.length) box.textContent = "全部写对了 🎉";
    return;
  }
  const w = dict[dj], a = dAnswers[dj];
  $("dictProgress").textContent = `第 ${dj + 1} / ${dict.length} 个`;
  $("dictPos").textContent = w.gender ? (needArticle() ? "名词，要带冠词" : "名词") : (w.pos || "");
  $("dictIn").value = a ? a.input : "";
  $("dictIn").readOnly = !!a;          // 用“上一个”回来看的词: 只看, 不能改
  if (a) { dictShow(w, a.r); return; }
  $("dictAnswer").classList.add("hidden");
  $("dictCheck").classList.remove("hidden");
  $("dictIn").focus();
  dictPlay();
}

function dictPlay(rate = null) { if (dj < dict.length) speakDe(wordText(dict[dj]), false, rate); }
$("dictPlay").onclick = () => dictPlay();
$("dictSlow").onclick = () => dictPlay(0.6);

function dictShow(w, r) {
  $("dictResult").textContent = r.msg;
  $("dictResult").className = r.ok ? "ok" : "msg";
  wordInto($("dictWord"), w);
  $("dictMeaning").textContent = w.meaning;
  $("dictAnswer").classList.remove("hidden");
  $("dictCheck").classList.add("hidden");
}

function dictCheck() {
  if (dj >= dict.length) return;
  if (dAnswers[dj]) { dj++; dictRender(); return; }   // 已经检查过: 回车 = 下一个
  const w = dict[dj];
  let input = $("dictIn").value;
  if (!input.trim()) { dictPlay(); return; }          // 空着按回车 = 再听一遍
  // 不要求冠词时, 写了冠词也算(朗读时冠词会读出来)
  if (w.gender && !needArticle()) input = input.trim().replace(/^(der|die|das)\s+/i, "");
  const r = checkSpell(w, input);
  dAnswers[dj] = { input: $("dictIn").value, r };
  dictShow(w, r);
  if (!r.ok) dictPlay();                              // 写错了再读一遍正确的
}
$("dictCheck").onclick = dictCheck;
$("dictNext").onclick = dictCheck;
$("dictBack").onclick = () => { if (dj > 0) { dj--; dictRender(); } };   // 只回看, 不能改答案

// 回车 检查 / 下一个; Ctrl+回车 再听一遍(在输入框里也有效)
function dictKey(e) {
  if (e.key !== "Enter" || e.isComposing) return false;
  if (e.ctrlKey) dictPlay(); else dictCheck();
  return true;
}
$("dictIn").onkeydown = e => { if (dictKey(e)) { e.preventDefault(); e.stopPropagation(); } };
onKey.dictation = (e, typing) => !typing && dictKey(e);
