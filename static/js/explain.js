// 句子讲解: 第一次打开时生成, 保存后所有人直接看到。没有 Key 或额度用完时复制到免费 AI
function noteBlock(box, title) {
  const h = document.createElement("div"); h.className = "nhead"; h.textContent = title;
  box.appendChild(h);
}

function renderNote(box, note) {
  box.textContent = "";
  noteBlock(box, "词形和用法");
  for (const w of note.words) {
    const row = document.createElement("div"); row.className = "nword";
    const head = document.createElement("div"); head.className = "nwordhead";
    const word = document.createElement("b"); word.textContent = w.word;
    const say = document.createElement("button"); say.className = "mini"; say.textContent = "🔊";
    say.onclick = () => speakDe(w.word);
    head.append(word, say);
    const form = document.createElement("div"); form.className = "lzh";
    form.textContent = [w.base && w.base !== w.word ? "原形 " + w.base : "", w.form].filter(Boolean).join(" · ");
    const why = document.createElement("div"); why.textContent = w.why;
    row.append(head, form, why);
    box.appendChild(row);
  }
  if (note.order) {
    noteBlock(box, "语序");
    const p = document.createElement("div"); p.textContent = note.order; box.appendChild(p);
  }
  if (note.point) {
    noteBlock(box, "记住这一点");
    const p = document.createElement("div"); p.textContent = note.point; box.appendChild(p);
  }
  noteBlock(box, "类似用法");
  for (const s of note.similar) {
    const b = document.createElement("button"); b.className = "lmodel"; b.textContent = "🔊 " + s.de;
    b.onclick = () => speakDe(s.de);
    const zh = document.createElement("div"); zh.className = "lzh"; zh.textContent = s.zh;
    box.append(b, zh);
  }
  const tip = document.createElement("div"); tip.className = "lzh nfoot"; tip.textContent = "AI 生成，未核对，语法以教材或老师为准。";
  box.appendChild(tip);
}

function renderFallback(box, body, msg) {
  box.textContent = "";
  const p = document.createElement("div"); p.className = "msg"; p.textContent = msg;
  const hint = document.createElement("div"); hint.className = "lzh";
  hint.textContent = "可以复制提示词到 Gemini、ChatGPT 或 Claude，再把回复全部粘贴到下面。";
  const copy = document.createElement("button"); copy.className = "secondary"; copy.textContent = "复制提示词";
  copy.style.cssText = "width:100%;margin-top:8px";
  copy.onclick = async () => {
    try { copyText((await api("/api/explain/prompt", "POST", body)).prompt); } catch (e) { toast(e.message); }
  };
  const paste = document.createElement("textarea"); paste.placeholder = "粘贴 AI 的回复"; paste.spellcheck = false;
  paste.style.cssText = "min-height:90px;margin-top:8px";
  const read = document.createElement("button"); read.className = "secondary"; read.textContent = "读取结果";
  read.style.cssText = "width:100%;margin-top:8px";
  read.onclick = async () => {
    try { renderNote(box, (await api("/api/explain/check", "POST", { ...body, text: paste.value })).note); }
    catch (e) { p.textContent = e.message; }
  };
  box.append(p, hint, copy, paste, read);
}

async function openExplain(box, line, level) {
  if (box.dataset.loaded) { box.classList.toggle("hidden"); return; }
  box.classList.remove("hidden");
  box.textContent = "查询中…";
  const body = { de: line.de, zh: line.zh, level };
  let r;
  try { r = await api("/api/explain?de=" + encodeURIComponent(line.de)); }
  catch (e) { box.textContent = e.message; return; }
  if (r.note) { box.dataset.loaded = "1"; renderNote(box, r.note); return; }
  if (!r.can) { box.textContent = "这句还没有讲解。"; return; }
  if (!r.ai) { renderFallback(box, body, "还没有配置 API Key。"); return; }
  box.textContent = "AI 正在讲解，大约要 10 秒…";
  try {
    const g = await api("/api/explain/generate", "POST", body);
    box.dataset.loaded = "1";
    renderNote(box, g.note);
  } catch (e) { renderFallback(box, body, e.message); }
}
