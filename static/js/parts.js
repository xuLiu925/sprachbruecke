// 构词解释: 已保存的直接显示; 没有的, 管理员点按钮才调用 AI, 保存后不再调用
const PARTS_CLARITY = {
  clear: "看字面就能猜到词义",
  partial: "字面有关，要联想一下",
  memo: "词义已经转变，拆开只帮助记忆",
};

const partLabel = p => (p.type === "prefix" ? p.text + "-"
  : p.type === "suffix" ? "-" + p.text
  : p.type === "link" ? "-" + p.text + "-" : p.text);

function renderPartStep(step) {
  const row = document.createElement("div");
  row.append(step.word + " = ");
  step.parts.forEach((p, i) => {
    if (i) row.append(" + ");
    if (p.type === "word") {                     // 只有独立的词能点开, 词缀查不到
      const b = document.createElement("button"); b.className = "tok"; b.textContent = p.text;
      b.onclick = () => openWordSheet(p.base, { de: "" });
      row.append(b);
    } else row.append(partLabel(p));
    row.append(`（${p.base !== p.text && p.type === "word" ? p.base + "，" : ""}${p.zh}）`);
  });
  return row;
}

async function wordParts(el, german, meaning = "") {
  el.textContent = "";
  el.dataset.word = german || "";
  if (!german) return;
  let r;
  try { r = await api("/api/parts?german=" + encodeURIComponent(german)); }
  catch (e) { return; }
  if (el.dataset.word !== german) return;
  const canMake = parts => r.ai && (parts ? r.can : r.gen);   // 重新解释只有管理员能用
  const show = (parts, report) => {
    el.textContent = "";
    if (parts && parts.split) {
      const title = document.createElement("div"); title.textContent = "构词";
      const literal = document.createElement("div"); literal.textContent = "字面：" + parts.literal;
      const tip = document.createElement("div"); tip.className = "lzh";
      tip.textContent = `${PARTS_CLARITY[parts.clarity]} · AI 生成，未核对`;
      el.append(title, ...parts.steps.map(renderPartStep), literal, tip);
    } else if (parts) {
      const none = document.createElement("div"); none.textContent = "构词：这个词不用拆";
      el.appendChild(none);
    }
    if (report) {
      const note = document.createElement("div"); note.className = "lzh"; note.textContent = "已报错：" + report;
      el.appendChild(note);
    }
    if (canMake(parts)) {
      const b = document.createElement("button"); b.className = "mini";
      b.textContent = parts ? "重新解释" : "AI 构词解释";
      b.onclick = async () => {
        b.disabled = true; b.textContent = "AI 正在拆词…";
        try {
          const made = (await api("/api/parts/generate", "POST", { german, meaning, again: !!parts })).parts;
          if (el.dataset.word === german) show(made, null);
        } catch (e) { toast(e.message); if (el.dataset.word === german) show(parts, report); }
      };
      el.appendChild(b);
    }
    if (parts) {
      const b = document.createElement("button"); b.className = "mini"; b.textContent = "报错";
      b.onclick = async () => {
        const reason = (prompt("哪里有问题？比如：这个前缀的意思不对") || "").trim();
        if (!reason) return;
        try { await api("/api/parts/report", "POST", { german, reason }); }
        catch (e) { return toast(e.message); }
        toast("已记录");
        if (el.dataset.word === german) show(parts, reason);
      };
      el.appendChild(b);
    }
  };
  show(r.parts, r.report);
}
