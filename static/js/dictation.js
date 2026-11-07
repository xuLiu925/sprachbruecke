// 听写: 听发音写单词。入口页 #dictation 选练习范围, 答题页 #dquiz。后端 dictation.py(FSRS 排期、错题本), 不影响今日学习
// 写错的词排到本组最后再考一次(retry), 得分和记录只算第一次作答
let dict = [], dj = 0, dAnswers = [];   // dAnswers[i] = 第 i 题的作答 {input, r}, 没答过是 undefined
let dScopes = [], dScopeNow = "", dScopeRun = "";

// ---------- 入口页: 练习范围 ----------
const DICT_LIST = {
  api: "/api/dictation", scopes: () => dScopes, unit: "词", sample: "例如：Palette, abholen, schnell",
  start(scope) { dPick(scope); dStart(scope); },
};
function dPick(id) { dScopeNow = id; setSetting("dScope", id); }
function dStart(scope) { dScopeRun = scope; go("dquiz"); }
function dShow() {
  scopeInto($("dsScope"), dScopes, dScopeNow, id => { dPick(id); dShow(); }, id => gnOpen(id, DICT_LIST));
}
onShow.dictation = async () => {
  let r;
  try { r = await api("/api/dictation/books"); } catch (e) { return toast(e.message); }
  dScopes = scopeItems(r);
  const saved = getSetting("dScope");
  dScopeNow = dScopes.some(x => x.id === saved) ? saved : r.current;
  dShow();
};
$("dsStart").onclick = () => { if (dScopeNow) dStart(dScopeNow); };

// ---------- 答题 ----------
async function startDictation() {
  $("dictBox").classList.add("hidden");
  $("dictDone").classList.add("hidden");
  const scope = dScopeRun || getSetting("dScope") || "";      // 直接刷新答题页时用上次的范围
  try {
    dict = (await api(`/api/dictation?scope=${encodeURIComponent(scope)}&${tzQuery()}`)).words;
  } catch (e) { toast(e.message); return; }
  dj = 0; dAnswers = [];
  $("dictBox").classList.remove("hidden");
  dictRender();
}
onShow.dquiz = startDictation;
$("dictAgain").onclick = startDictation;

const dictFirst = () => dict.map((w, i) => [w, dAnswers[i]]).filter(([w]) => !w.retry);

function dictRender() {
  $("dictBack").classList.toggle("hidden", dj === 0);
  const done = dj >= dict.length;
  $("dictBox").classList.toggle("hidden", done);
  $("dictDone").classList.toggle("hidden", !done);
  if (done) {
    const first = dictFirst(), wrong = first.filter(([, a]) => !a.r.ok).map(([w]) => w);
    $("dictScore").textContent = first.length ? `得分 ${first.length - wrong.length} / ${first.length}`
      : (dScopeRun === "wrong" ? "错题本是空的，换个范围继续练。" : "这个范围没有可以听写的词，换个范围试试。");
    $("dictDoneTip").classList.toggle("hidden", !wrong.length);
    const box = $("dictWrong"); box.textContent = "";
    if (wrong.length) {
      box.append("写错的词：");
      for (const w of wrong) {
        const line = document.createElement("div");
        line.textContent = `${wordText(w)} — ${w.meaning}`;
        box.appendChild(line);
      }
    } else if (first.length) box.textContent = "全部写对了";
    return;
  }
  const w = dict[dj], a = dAnswers[dj];
  const total = dictFirst().length;
  $("dictProgress").textContent = w.retry ? "再练一次" : `第 ${dict.slice(0, dj + 1).filter(x => !x.retry).length} / ${total} 个`;
  $("dictPos").textContent = w.gender ? (needArticle() ? "名词，要带冠词" : "名词") : (w.pos || "");
  $("dictIn").value = a ? a.input : "";
  $("dictIn").readOnly = !!a;          // 用“上一个”回来看的词: 只看, 不能改
  if (a) { dictShow(w, a); return; }
  $("dictAnswer").classList.add("hidden");
  $("dictCheck").classList.remove("hidden");
  $("dictIn").focus();
  dictPlay();
}

function dictPlay(rate = null) { if (dj < dict.length) speakDe(wordText(dict[dj]), false, rate); }
$("dictPlay").onclick = () => dictPlay();
$("dictSlow").onclick = () => dictPlay(0.6);

// 最长公共子序列: 返回两边各自哪些字母对得上
function dictLcs(a, b) {
  const m = a.length, n = b.length, t = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) for (let j = n - 1; j >= 0; j--)
    t[i][j] = a[i] === b[j] ? t[i + 1][j + 1] + 1 : Math.max(t[i + 1][j], t[i][j + 1]);
  const ka = new Array(m).fill(false), kb = new Array(n).fill(false);
  for (let i = 0, j = 0; i < m && j < n;) {
    if (a[i] === b[j]) { ka[i] = kb[j] = true; i++; j++; }
    else if (t[i + 1][j] >= t[i][j + 1]) i++; else j++;
  }
  return [ka, kb];
}
// 写错时: “你写的”里多出来 / 写错的字母标红, “正确”里漏掉的字母标绿
function dictDiff(input, want) {
  const box = $("dictDiff"); box.textContent = "";
  const a = input.trim().replace(/\s+/g, " "), [ka, kb] = dictLcs([...a], [...want]);
  const line = (label, chars, keep, cls) => {
    const d = document.createElement("div");
    const l = document.createElement("span"); l.className = "lbl"; l.textContent = label;
    d.appendChild(l);
    chars.forEach((ch, i) => {
      if (keep[i]) d.append(ch);
      else { const s = document.createElement("span"); s.className = cls; s.textContent = ch; d.appendChild(s); }
    });
    box.appendChild(d);
  };
  line("你写的", [...a], ka, "bad");
  line("正确", [...want], kb, "miss");
  box.classList.remove("hidden");
}

function dictShow(w, a) {
  const r = a.r;
  $("dictResult").textContent = r.msg;
  $("dictResult").className = r.ok ? "ok" : "msg";
  if (!r.ok && a.input.trim()) dictDiff(a.input, a.want);
  else $("dictDiff").classList.add("hidden");
  wordInto($("dictWord"), w);
  $("dictMeaning").textContent = w.meaning;
  exampleInto($("dictExample"), w.example);
  $("dictAnswer").classList.remove("hidden");
  $("dictCheck").classList.add("hidden");
  $("dictNext").focus({ preventScroll: true });
}

function dictCheck() {
  if (dj >= dict.length) return;
  if (dAnswers[dj]) { dj++; dictRender(); return; }   // 已经检查过: 回车 = 下一个
  const w = dict[dj];
  let input = $("dictIn").value;
  if (!input.trim()) { dictPlay(); return; }          // 空着按回车 = 再听一遍
  // 不要求冠词时, 写了冠词也算(朗读时冠词会读出来)
  const art = w.gender && needArticle();
  if (w.gender && !art) input = input.trim().replace(/^(der|die|das)\s+/i, "");
  const r = checkSpell(w, input);
  dAnswers[dj] = { input: $("dictIn").value, r, want: art ? w.gender + " " + w.german : w.german };
  if (!w.retry) api("/api/dictation/result", "POST", { word_id: w.id, ok: r.ok }).catch(() => {});
  // 写错的排到本组最后再考一次; 重练又错不再加
  if (!r.ok && !w.retry) dict.push({ ...w, retry: true });
  dictShow(w, dAnswers[dj]);
  if (!r.ok) dictPlay();                              // 写错了再读一遍正确的
}
$("dictCheck").onclick = dictCheck;
$("dictNext").onclick = dictCheck;
$("dictCard").onclick = () => { const w = dict[dj]; if (w && dAnswers[dj]) openWordId(w.id, w.german); };
$("dictBack").onclick = () => { if (dj > 0) { dj--; dictRender(); } };   // 只回看, 不能改答案

// 回车 检查 / 下一个; Ctrl+回车 再听一遍(在输入框里也有效); 答完后 D 单词卡
function dictKey(e) {
  if (e.key !== "Enter" || e.isComposing) return false;
  if (e.ctrlKey) dictPlay(); else dictCheck();
  return true;
}
$("dictIn").onkeydown = e => { if (dictKey(e)) { e.preventDefault(); e.stopPropagation(); } };
onKey.dquiz = (e, typing) => {
  if (dictKey(e)) return true;
  if (!typing && e.key.toLowerCase() === "d" && dAnswers[dj]) { $("dictCard").click(); return true; }
  return false;
};
