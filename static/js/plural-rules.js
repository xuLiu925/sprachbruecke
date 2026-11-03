// 复数练习的入口页: 规律速查表 + 练习范围, 答题用句子填空页。规律是 Claude 整理的, 要提醒用户对照教材核对
// 每个词符合哪条规律由后端判断(plural_quiz.py 的 RULES), 改规律时两边一起改
const PLURAL_RULES = {
  endings: [
    ["-ung -heit -keit -schaft -ion -tät（阴性）", "加 -en", "die Zeitung → Zeitungen"],
    ["-e（阴性）", "加 -n", "die Lampe → Lampen"],
    ["-el -er（阴性）", "加 -n", "die Regel → Regeln"],
    ["-in（阴性）", "变 -innen", "die Lehrerin → Lehrerinnen"],
    ["-chen -lein", "不变", "das Mädchen → Mädchen"],
    ["-er -el -en（阳性、中性）", "不变，部分变音", "der Lehrer → Lehrer\nder Vater → Väter"],
    ["-e（阳性的人或动物）", "加 -n", "der Kollege → Kollegen"],
    ["-ent -ant -ist -or（阳性，多指人）", "大多加 -en", "der Student → Studenten\nder Doktor → Doktoren"],
    ["-nis", "变 -nisse", "das Ergebnis → Ergebnisse"],
    ["-um（外来词）", "变 -en", "das Museum → Museen"],
    ["-i -o -u 结尾、缩写词", "大多加 -s", "das Auto → Autos\nder LKW → LKWs"],
  ],
  genders: [
    "阴性：大多加 -(e)n。单音节词常加 -e 并变音，如 die Stadt → Städte。",
    "阳性：大多加 -e，常变音，如 der Tag → Tage、der Stuhl → Stühle。",
    "中性：常加 -e，如 das Jahr → Jahre、das Paket → Pakete。",
    "中性的短词：很多加 -er 并变音，如 das Kind → Kinder、das Buch → Bücher。",
  ],
  general: [
    "复数的定冠词一律是 die。",
    "加 -er 时，能变音的词一定变音，如 der Mann → Männer。",
    "只有 a、o、u、au 能变音，分别变成 ä、ö、ü、äu。",
    "复合词看最后一个词，如 der Lieferschein → Lieferscheine。",
    "第三格复数再加 -n，如 mit den Kindern；复数已以 -n 或 -s 结尾时不加，如 mit den Autos。",
  ],
  exceptions: [
    "die Mutter → Mütter、die Tochter → Töchter：阴性，但只变音。",
    "der Park → Parks：辅音结尾，但加 -s。",
    "das Thema → Themen、die Firma → Firmen：-a 结尾的词没有统一规律，要单独记。",
  ],
};

function renderPluralRules(box) {
  if (box.childElementCount) return;
  const section = title => {
    const d = document.createElement("div");
    d.className = "rulehead"; d.textContent = title;
    box.appendChild(d);
  };
  const list = items => {
    const ul = document.createElement("ul");
    ul.className = "rulelist";
    for (const text of items) ul.appendChild(document.createElement("li")).textContent = text;
    box.appendChild(ul);
  };
  const note = document.createElement("div");
  note.className = "meta left";
  note.textContent = "这些大多是倾向，不是绝对规则。阳性、中性的单音节词规律较弱，要把冠词和复数一起记。";
  box.appendChild(note);
  section("按词尾判断（比较可靠）");
  const t = table(["词尾", "复数", "例子"], PLURAL_RULES.endings);
  t.querySelector("table").classList.add("gtable");
  box.appendChild(t);
  section("其他词按词性看倾向");
  list(PLURAL_RULES.genders);
  section("通用规律");
  list(PLURAL_RULES.general);
  section("常见例外");
  list(PLURAL_RULES.exceptions);
}

// ---------- 练习范围和答题 ----------
let pScopeNow = "", pScopes = [];

function pStart(scope) {
  sPreset = {
    mode: "cloze", name: "复数练习", url: "/api/plural?scope=" + scope, rules: true,
    empty: scope === "wrong" ? "错题本是空的，换个范围继续练。" : "这个范围没有带复数的名词，换个范围试试。",
    onAnswer(q, ok) {
      if (!ok) sq.push({ ...q, retry: true });          // 错题排到本组最后再练一次
      api("/api/plural/result?" + tzQuery(), "POST", { word_id: q.word_id, ok }).catch(() => {});
    },
  };
  go("squiz");
}

const PLURAL_LIST = {
  api: "/api/plural", scopes: () => pScopes,
  start(scope) { pPick(scope); pStart(scope); },
};
function pPick(id) { pScopeNow = id; setSetting("pScope", id); }

function pShow() {
  scopeInto($("pScope"), pScopes, pScopeNow, id => { pPick(id); pShow(); }, id => gnOpen(id, PLURAL_LIST));
}

onShow.plural = async () => {
  renderPluralRules($("pRules"));
  let r;
  try { r = await api("/api/plural/books"); } catch (e) { return toast(e.message); }
  pScopes = scopeItems(r);
  const saved = getSetting("pScope");
  pScopeNow = pScopes.some(x => x.id === saved) ? saved : r.current;
  pShow();
};
$("pStart").onclick = () => { if (pScopeNow) pStart(pScopeNow); };

$("sqReport").onclick = async () => {
  const reason = (prompt("这题哪里有问题？") || "").trim();
  if (!reason) return;
  const q = sq[si];
  try {
    await api("/api/grammar/nouns/report", "POST", { word_id: q.word_id, prompt: `复数 ${q.de}`, reason });
    toast("已记录");
  } catch (e) { toast(e.message); }
};
