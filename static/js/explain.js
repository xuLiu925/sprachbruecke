// 句子讲解: 第一次打开时生成, 保存后所有人直接看到。没有 Key 或额度用完时复制到免费 AI
function noteBlock(box, title) {
  const h = document.createElement("div"); h.className = "nhead"; h.textContent = title;
  box.appendChild(h);
}

// 报错: 写下哪里有问题, 重新生成时会告诉 AI。返回写下的内容, 取消时返回 null
async function reportContent(kind, de) {
  const reason = (prompt("哪里有问题？比如：这里应该是第四格") || "").trim();
  if (!reason) return null;
  try { await api("/api/report", "POST", { kind, de, reason }); } catch (e) { toast(e.message); return null; }
  toast("已记录，重新生成时 AI 会改正");
  return reason;
}

function miniAction(label, fn) {
  const b = document.createElement("button"); b.className = "secondary"; b.textContent = label; b.onclick = fn;
  return b;
}

// meta = {can, ai, report}: can = 能重新生成, report = 已记录的问题
function renderNote(box, note, body, meta = {}) {
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
  const drill = document.createElement("button"); drill.textContent = "🔁 替换练习：换个情况再说一遍";
  drill.style.cssText = "width:100%;margin-top:10px";
  const drillBox = document.createElement("div");
  drill.onclick = () => openDrills(drillBox, drill, body);

  const issue = document.createElement("div"); issue.className = "lzh";
  const showIssue = t => { issue.textContent = t ? "⚠️ 已记录的问题：" + t : ""; };
  showIssue(meta.report);
  const row = document.createElement("div"); row.className = "row"; row.style.marginTop = "8px";
  const fixBox = document.createElement("div");
  row.appendChild(miniAction("⚠️ 报错", async () => {
    const reason = await reportContent("note", body.de);
    if (reason) showIssue(reason);
  }));
  if (meta.can) {
    const regen = miniAction("🔄 重新生成", async () => {
      if (!confirm("重新生成这句的讲解？成功后会替换现有内容。")) return;
      regen.disabled = true; regen.textContent = "AI 正在重写…";
      fixBox.textContent = "";
      try {
        const r = await api("/api/explain/regenerate", "POST", body);
        renderNote(box, r.note, body, { ...meta, report: null });
      } catch (e) {
        regen.disabled = false; regen.textContent = "🔄 重新生成";
        renderFallback(fixBox, body, e.message, "/api/explain", r => renderNote(box, r.note, body, { ...meta, report: null }));
      }
    });
    row.appendChild(regen);
  }
  box.append(tip, issue, row, fixBox, drill, drillBox);
  if (meta.can) {
    const redo = miniAction("🔄 重新出替换题", async () => {
      if (!confirm("重新出这句的替换练习？成功后会替换现有题目。")) return;
      redo.disabled = true; redo.textContent = "AI 正在出题…"; drillBox.textContent = "";
      try { rpOpenItems((await api("/api/drills/regenerate", "POST", body)).items); }
      catch (e) { renderFallback(drillBox, body, e.message, "/api/drills", g => rpOpenItems(g.items)); }
      finally { redo.disabled = false; redo.textContent = "🔄 重新出替换题"; }
    });
    redo.style.cssText = "width:100%;margin-top:8px";
    drill.after(redo);
  }
}

// 替换练习: 有保存的就直接开始, 没有就生成; 做题用角色扮演页面
async function openDrills(box, btn, body) {
  const label = btn.textContent;
  box.textContent = ""; btn.disabled = true;
  try {
    const r = await api("/api/drills?de=" + encodeURIComponent(body.de));
    if (r.items) return rpOpenItems(r.items);
    if (!r.can) { box.textContent = "这句还没有替换练习。"; return; }
    if (!r.ai) return renderFallback(box, body, "还没有配置 API Key。", "/api/drills", g => rpOpenItems(g.items));
    btn.textContent = "AI 正在出题…";
    rpOpenItems((await api("/api/drills/generate", "POST", body)).items);
  } catch (e) {
    renderFallback(box, body, e.message, "/api/drills", g => rpOpenItems(g.items));
  } finally { btn.disabled = false; btn.textContent = label; }
}

function renderFallback(box, body, msg, base = "/api/explain", done = r => renderNote(box, r.note, body, { can: true })) {
  box.textContent = "";
  const p = document.createElement("div"); p.className = "msg"; p.textContent = msg;
  const hint = document.createElement("div"); hint.className = "lzh";
  hint.textContent = "可以复制提示词到 Gemini、ChatGPT 或 Claude，再把回复全部粘贴到下面。";
  const copy = document.createElement("button"); copy.className = "secondary"; copy.textContent = "复制提示词";
  copy.style.cssText = "width:100%;margin-top:8px";
  copy.onclick = async () => {
    try { copyText((await api(base + "/prompt", "POST", body)).prompt); } catch (e) { toast(e.message); }
  };
  const paste = document.createElement("textarea"); paste.placeholder = "粘贴 AI 的回复"; paste.spellcheck = false;
  paste.style.cssText = "min-height:90px;margin-top:8px";
  const read = document.createElement("button"); read.className = "secondary"; read.textContent = "读取结果";
  read.style.cssText = "width:100%;margin-top:8px";
  read.onclick = async () => {
    try { done(await api(base + "/check", "POST", { ...body, text: paste.value })); }
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
  if (r.note) { box.dataset.loaded = "1"; renderNote(box, r.note, body, r); return; }
  if (!r.can) { box.textContent = "这句还没有讲解。"; return; }
  if (!r.ai) { renderFallback(box, body, "还没有配置 API Key。"); return; }
  box.textContent = "AI 正在讲解，大约要 10 秒…";
  try {
    const g = await api("/api/explain/generate", "POST", body);
    box.dataset.loaded = "1";
    renderNote(box, g.note, body, r);
  } catch (e) { renderFallback(box, body, e.message); }
}
