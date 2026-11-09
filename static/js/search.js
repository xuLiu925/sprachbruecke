// 全局搜索: 顶栏的放大镜(电脑上按 /), 打开一层搜索, 结果用底部单词卡显示, 不离开当前页面
// 打开时多一条浏览器历史, 所以手机返回键能关闭; 从单词卡进详情页再返回, 搜索结果还在
const SEARCH_RECENT = 10;
// 做题的页面: [题目区, 答完才出现的区域], 题目显示着而答案没出现 = 正在答题, 不能搜索
const SEARCH_LOCKS = {
  review: ["cardBox", "answer"], drill: ["drillBtns", "drillInfo"], dquiz: ["dictBox", "dictAnswer"],
  squiz: ["sqBox", "sqAnswer"], gquiz: ["gqBox", "gqFeedback"], roleplay: ["rpBox", "rpReveal"],
};
const isShown = id => !$(id).classList.contains("hidden");
const searchIsOpen = () => isShown("search");

function searchLocked() {
  const lock = SEARCH_LOCKS[current];
  return !user || (!!lock && isShown(lock[0]) && !isShown(lock[1]));   // 游客不能搜索(要登录)
}
const searchRefresh = () => $("btnSearch").classList.toggle("hidden", searchLocked());
// 各练习页显示答案时都会改 class, 在这里统一监听, 不用每个页面都写
new MutationObserver(searchRefresh).observe(document.querySelector("main"),
  { subtree: true, attributes: true, attributeFilter: ["class"] });

function openSearch() {
  if (searchLocked()) return;
  history.pushState({ search: true }, "");
  $("seInput").value = "";
  searchRun();
  $("search").classList.remove("hidden");
  $("seInput").focus();
}
function closeSearch() {
  if (!searchIsOpen()) return;
  $("search").classList.add("hidden");
  history.back();
}
function searchSync() {   // 返回键、进出详情页时, 按当前这条历史决定显示不显示
  const open = !!(history.state && history.state.search);
  if (searchIsOpen() && !open) wsHide();
  $("search").classList.toggle("hidden", !open);
}
window.addEventListener("popstate", searchSync);
window.addEventListener("hashchange", searchSync);

function searchRemember(w) {
  const old = getSetting("recentSearch").filter(x => x.german !== w.german || x.id !== w.id);
  setSetting("recentSearch", [{ german: w.german, id: w.id }, ...old].slice(0, SEARCH_RECENT));
}
function searchOpenWord(w) {
  searchRemember(w);
  if (!w.id) return openGlossaryWord(w);
  openWordId(w.id, w.german);
  if (getSetting("autoWord")) speakDe(wordText(w));
}

function searchRecent() {
  const recent = getSetting("recentSearch"), box = $("seRecent");
  box.textContent = "";
  $("seMsg").textContent = recent.length ? "最近查过" : "输入德语、变化形式（ging）或中文";
  for (const r of recent) {
    const b = document.createElement("button"); b.className = "mini"; b.textContent = r.german;
    b.onclick = () => {
      if (r.id) return openWordId(r.id, r.german);
      $("seInput").value = r.german; searchRun();
    };
    box.appendChild(b);
  }
}

let seTimer, seSeq = 0;
async function searchRun() {
  const seq = ++seSeq, q = $("seInput").value.trim(), list = $("seList"), ai = $("seAi");
  $("seRecent").textContent = ""; ai.classList.add("hidden");
  if (!q) { list.classList.add("hidden"); return searchRecent(); }
  let r;
  try { r = await api("/api/dict?q=" + encodeURIComponent(q)); }
  catch (e) { if (seq === seSeq) toast(e.message); return; }
  if (seq !== seSeq) return;                 // 只显示最后一次搜索的结果
  list.textContent = "";
  list.classList.toggle("hidden", !r.words.length);
  $("seMsg").textContent = r.words.length ? "" : `没有找到“${q}”`;
  r.words.forEach(w => list.appendChild(wordRow(w, () => searchOpenWord(w))));
  if (!r.words.length && r.gen && r.ai) {    // 查不到: 用户点了才调用 AI
    ai.dataset.q = q; ai.disabled = false; ai.textContent = `用 AI 查询“${q}”`;
    ai.classList.remove("hidden");
  }
}

$("seAi").onclick = async () => {
  const btn = $("seAi"), q = btn.dataset.q;
  btn.disabled = true; btn.textContent = "AI 正在查询…";
  let r;
  try { r = await api("/api/dict/ai", "POST", { q }); }
  catch (e) { toast(e.message); btn.disabled = false; btn.textContent = `用 AI 查询“${q}”`; return; }
  if ($("seInput").value.trim() !== q) return;   // 查询期间已经换了别的词
  if (!r.word) { btn.classList.add("hidden"); $("seMsg").textContent = `AI 也没有查到“${q}”`; return; }
  await searchRun();
  searchOpenWord(r.word);
};

$("btnSearch").onclick = openSearch;
$("seClose").onclick = closeSearch;
$("search").onclick = e => { if (e.target.id === "seBody") closeSearch(); };
$("seInput").oninput = () => { clearTimeout(seTimer); seTimer = setTimeout(searchRun, 250); };
