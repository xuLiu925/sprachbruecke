// 单词卡的显示: 今日学习翻面后的答案(前缀 a)、单词详情页(v)、底部单词卡(ws)共用。
// 元素按「前缀 + 名字」找, 页面里没有的就跳过:
//   Word 标题(带颜色的冠词) / Pos 词性 / Plural 复数 / Meaning 释义 / Gender 词性解释 / Parts 构词 /
//   Spell + SpellBtn 拼读 / Example 例句 / Forms 变格变位 / Details 详情
// 给单词卡加内容时改这里, 三处一起生效。按钮(加入学习、发音等)和页面自己的状态还在各自的文件里

function wordInto(el, c) {
  el.textContent = "";
  if (c.gender) {
    const a = document.createElement("span");
    a.className = "art " + c.gender; a.textContent = c.gender;
    el.appendChild(a);
  }
  el.appendChild(document.createTextNode(c.german));
}

// opt: pos = false 不显示词性(题目上已经有); note = 复数后面的补充(如“文中是 ging”);
//      forms = false 先不放变格表和详情(底部单词卡点“详情”才展开); example = false 例句由页面自己放;
//      level = 例句讲解的级别(默认按词的级别, 没有就 B1)
// 返回词性解释和构词的加载(底部单词卡返回上一张时要等它们加载完再恢复滚动位置)
function fillWordCard(prefix, w, opt = {}) {
  const el = name => $(prefix + name);
  const set = (name, text) => { if (el(name)) el(name).textContent = text; };
  wordInto(el("Word"), w);
  set("Pos", w.pos || "");
  const pos = el("Pos") || opt.pos === false ? "" : w.pos;   // 没有单独放词性的地方, 就放在复数前面
  const inTable = opt.forms !== false && w.forms && w.forms.cases;   // 有变格表时复数在表里
  set("Plural", [pos, w.plural && !inTable ? "复数：" + w.plural : "", opt.note].filter(Boolean).join(" · "));
  set("Meaning", w.meaning);
  if (el("Example") && opt.example !== false) exampleInto(el("Example"), w.example, opt.level || w.level || "B1");
  if (opt.forms !== false) fillWordMore(prefix, w);
  if (el("Spell")) spellReset(el("Spell"));
  if (el("SpellBtn")) spellTitle(el("Word"), el("SpellBtn"));
  return Promise.all([el("Gender") && genderReason(el("Gender"), w.german, w.gender, w.meaning),
                      el("Parts") && wordParts(el("Parts"), w.german, w.meaning)]);
}

// 变格变位表和详情
function fillWordMore(prefix, w) {
  if ($(prefix + "Forms")) renderForms(w.forms, $(prefix + "Forms"));
  if ($(prefix + "Details")) renderDetails(w.details, $(prefix + "Details"));
}

function table(head, rows) {
  const t = document.createElement("table"); t.className = "forms";
  const tr = t.insertRow();
  for (const h of head) { const th = document.createElement("th"); th.textContent = h; tr.appendChild(th); }
  for (const r of rows) { const row = t.insertRow(); for (const x of r) row.insertCell().textContent = x; }
  return scrollBox(t);   // 名词很长时(如 Geschwindigkeitsbegrenzungen)在卡片里左右滑
}

function renderForms(f, box) {
  box.textContent = "";
  if (!f) return;
  if (f.cases) {
    const hasPl = f.cases.pl.some(x => x);
    box.appendChild(table(hasPl ? ["", "单数", "复数"] : ["", "单数（无复数）"],
      CASES.map((n, i) => hasPl ? [n, f.cases.sg[i], f.cases.pl[i]] : [n, f.cases.sg[i]])));
  }
  if (f.praesens) box.appendChild(table(["人称", "现在时"], PERSONS.map((p, i) => [p, f.praesens[i]])));
  if (f.past) {
    const p = document.createElement("div"); p.className = "pastline";
    p.textContent = `过去式 ${f.past[0]} · 完成时 ${f.past[1]}`;
    box.appendChild(p);
  }
}

// 单词书的详细内容: 音标、词根、用法、更多例句、词组、近反义词、相关词、提示
const DETAIL_SECTIONS = [["root", "词根"], ["usage", "用法"], ["examples", "更多例句"], ["phrases", "常用词组"],
                         ["synonyms", "近义词"], ["antonyms", "反义词"], ["related", "相关词"], ["notes", "提示"]];
function renderDetails(d, box) {
  box.textContent = "";
  if (!d) return;
  if (d.machine) {
    const p = document.createElement("p"); p.className = "meta"; p.textContent = "提示：这个释义是机器翻译，可能不准";
    box.appendChild(p);
  }
  if (d.ipa) {
    const p = document.createElement("p"); p.className = "meta"; p.textContent = `[${d.ipa}]`;
    box.appendChild(p);
  }
  for (const [key, title] of DETAIL_SECTIONS) {
    if (!d[key] || !d[key].length) continue;
    const h = document.createElement("h4"); h.className = "detail-title"; h.textContent = title;
    box.appendChild(h);
    for (const line of [].concat(d[key])) {
      const p = document.createElement("p"); p.className = "detail-line"; p.textContent = line;
      box.appendChild(p);
    }
  }
}
