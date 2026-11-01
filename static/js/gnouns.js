// 查看练习范围里的名词: 单词书只看, 错题本还能手动加词和移除。定冠词和复数练习共用, 差别都在 gnKind 里
const NOUN_LIST = {
  api: "/api/grammar/nouns", scopes: () => gScopeList,
  start(scope) { gScopeNow = scope; setSetting("gScope", scope); go("gquiz"); },
};
const VERB_LIST = { ...NOUN_LIST, api: "/api/grammar/verbs", unit: "动词", sample: "例如：fahren, geben, abholen" };
const PERFEKT_LIST = { ...VERB_LIST, api: "/api/grammar/perfekt" };
let gnScope = "", gnPage = 1, gnKind = NOUN_LIST;

function gnOpen(scope, kind = NOUN_LIST) {
  gnScope = scope; gnPage = 1; gnKind = kind;
  go("gnouns");
}
onShow.gnouns = gnLoad;

async function gnLoad() {
  if (!gnScope) return location.replace("#grammar");       // 直接刷新这一页时不知道要看哪本
  const name = gnKind.scopes().find(s => s.id === gnScope).name, wrong = gnScope === "wrong";
  $("title").textContent = name;
  $("gnAddBox").classList.toggle("hidden", !wrong);
  $("gnStart").textContent = "练习" + name;
  const unit = gnKind.unit || "名词";
  $("gnAddTip").textContent = `写下想练的${unit}，用逗号或空格分开。变化形式也能找到原形。手动加的词要自己移除。`;
  $("gnText").placeholder = gnKind.sample || "例如：Palette, Karton, Tor";
  let r;
  try { r = await api(`${gnKind.api}/words?scope=${gnScope}&page=${gnPage}`); } catch (e) { return toast(e.message); }
  $("gnCount").textContent = `共 ${r.total} 个${unit}`;
  const box = $("gnList"); box.textContent = "";
  box.classList.toggle("hidden", !r.words.length);
  for (const w of r.words) {
    const row = document.createElement("div"); row.className = "lline nwordhead";
    const t = document.createElement("span"); t.className = "gnword";
    const head = document.createElement("b"); wordInto(head, w);
    t.append(head, (w.plural ? " · die " + w.plural : "") + "  " + w.meaning);
    t.onclick = () => openWordSheet(w.german, { de: "" });
    if (wrong) {
      const note = document.createElement("div"); note.className = "lzh";
      note.textContent = [w.wrong ? `错过 ${w.wrong} 次 · 已连续答对 ${w.streak} 次` : "", w.manual ? "手动加的" : ""]
        .filter(Boolean).join(" · ");
      t.appendChild(note);
    }
    row.appendChild(t);
    if (wrong) {
      const del = document.createElement("button"); del.className = "mini"; del.textContent = "移除";
      del.onclick = async () => {
        try { await api(`${gnKind.api}/list/${w.id}`, "DELETE"); } catch (e) { return toast(e.message); }
        gnLoad();
      };
      row.appendChild(del);
    }
    box.appendChild(row);
  }
  $("gnPager").classList.toggle("hidden", r.pages <= 1);
  $("gnPageNo").textContent = `${r.page} / ${r.pages}`;
  $("gnPrev").disabled = r.page <= 1;
  $("gnNext").disabled = r.page >= r.pages;
}

const gnTurn = step => { gnPage += step; gnLoad(); window.scrollTo(0, 0); };
$("gnPrev").onclick = () => gnTurn(-1);
$("gnNext").onclick = () => gnTurn(1);

$("gnAdd").onclick = async () => {
  const text = $("gnText").value.trim();
  if (!text) return;
  let r;
  try { r = await api(gnKind.api + "/list", "POST", { text }); }
  catch (e) { return toast(e.message); }
  $("gnMsg").textContent = `加入 ${r.added} 个` + (r.skipped ? `，已有 ${r.skipped} 个` : "")
    + (r.missing.length ? `，没找到：${r.missing.join("、")}` : "");
  if (!r.missing.length) $("gnText").value = "";
  gnLoad();
};

$("gnStart").onclick = () => gnKind.start(gnScope);
