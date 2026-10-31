// 我的词性本: 用户自己挑的名词, 在定冠词练习里选“我的词性本”时出题
onShow.gnouns = gnLoad;

async function gnLoad() {
  let r;
  try { r = await api("/api/grammar/nouns/list"); } catch (e) { return toast(e.message); }
  $("gnCount").textContent = `共 ${r.words.length} 个词`;
  const box = $("gnList"); box.textContent = "";
  box.classList.toggle("hidden", !r.words.length);
  for (const w of r.words) {
    const row = document.createElement("div"); row.className = "lline nwordhead";
    const t = document.createElement("span");
    const name = document.createElement("b"); wordInto(name, w);
    t.append(name, "  " + w.meaning);
    const del = document.createElement("button"); del.className = "mini"; del.textContent = "移除";
    del.onclick = async () => {
      try { await api("/api/grammar/nouns/list/" + w.id, "DELETE"); } catch (e) { return toast(e.message); }
      gnLoad();
    };
    row.append(t, del); box.appendChild(row);
  }
}

$("gnAdd").onclick = async () => {
  const text = $("gnText").value.trim();
  if (!text) return;
  let r;
  try { r = await api("/api/grammar/nouns/list", "POST", { text }); }
  catch (e) { return toast(e.message); }
  $("gnMsg").textContent = `加入 ${r.added} 个` + (r.skipped ? `，已有 ${r.skipped} 个` : "")
    + (r.missing.length ? `，没找到：${r.missing.join("、")}` : "");
  if (!r.missing.length) $("gnText").value = "";
  gnLoad();
};

$("gnStart").onclick = () => {
  setSetting("gScope", "mine");
  go("gquiz");
};
