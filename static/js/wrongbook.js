// 错题本: 定冠词、复数、现在时、完成时、动词搭配、听写的错题放在一页。
// 每类: 错题数、前几个词、“练一组”(用这类练习的错题本范围出题)、“全部”(gnouns.js 的单词列表页)
// 数据都来自各练习现有的接口: {api}/books 的 wrong, {api}/words?scope=wrong
const WRONG_KINDS = [
  { name: "定冠词", sub: "der / die / das 和四个格", tile: { text: "die", cls: "die" }, api: "/api/grammar/nouns",
    list: () => NOUN_LIST, topic: "art-def" },
  { name: "复数", sub: "名词的复数形式", tile: { text: "-en", cls: "das" }, api: "/api/plural",
    list: () => PLURAL_LIST, plural: true },
  { name: "现在时变位", sub: "动词的人称变位", tile: { text: "-st" }, api: "/api/grammar/verbs",
    list: () => VERB_LIST, topic: "verb-praes" },
  { name: "完成时", sub: "haben / sein 和过去分词", tile: { text: "hat" }, api: "/api/grammar/perfekt",
    list: () => PERFEKT_LIST, topic: "perf-bank" },
  { name: "动词搭配", sub: "介词和格", tile: { text: "auf" }, api: "/api/grammar/usage",
    list: () => USAGE_LIST, topic: "verb-usage" },
  { name: "听写", sub: "听发音写单词", tile: { text: "听" }, api: "/api/dictation",
    list: () => DICT_LIST, dict: true },
];
const WRONG_PREVIEW = 8;   // 每类先显示几个词

// 用错题本出一组题: 只改这一次的范围, 不改各练习页记住的范围
function wrongStart(k) {
  if (k.plural) return pStart("wrong");
  if (k.dict) return dStart("wrong");
  gTopic = GRAMMAR_TOPICS.find(t => t.id === k.topic);
  gScopeNow = "wrong";
  go("gquiz");
}

// 看全部: 单词列表页要知道这类练习有哪些范围(平时是打开练习页时取的)
function wrongOpenList(k, books) {
  const items = scopeItems(books);
  if (k.plural) pScopes = items;
  else if (k.dict) dScopes = items;
  else { gScopeList = items; gTopic = GRAMMAR_TOPICS.find(t => t.id === k.topic); }   // 列表页的“练习”按钮要知道是哪类
  gnOpen("wrong", k.list());
}

onShow.wrong = async () => {
  const box = $("wrongList");
  box.textContent = "";
  const get = url => api(url).catch(() => null);
  const books = await Promise.all(WRONG_KINDS.map(k => get(k.api + "/books")));
  let total = 0;
  WRONG_KINDS.forEach((k, i) => {
    const b = books[i];
    const n = b ? b.wrong : 0;
    total += n;
    const card = document.createElement("div"); card.className = "card wrongkind";
    const head = document.createElement("div"); head.className = "wronghead";
    const tile = document.createElement("span"); tile.className = "tile44 " + (k.tile.cls || ""); tile.textContent = k.tile.text;
    const title = document.createElement("div"); title.className = "grow";
    const t = document.createElement("b"); t.textContent = k.name;
    const s = document.createElement("small"); s.textContent = k.sub;
    title.append(t, s);
    const count = document.createElement("span"); count.className = "wrongn" + (n ? "" : " zero");
    count.textContent = n;
    head.append(tile, title, count);
    card.appendChild(head);
    if (!b) {
      const p = document.createElement("p"); p.className = "meta left"; p.textContent = "暂时取不到，稍后再试。";
      card.appendChild(p);
    } else if (!n) {
      const p = document.createElement("p"); p.className = "meta left"; p.textContent = "没有错题。";
      card.appendChild(p);
    } else {
      const words = document.createElement("div"); words.className = "wrongwords";
      card.appendChild(words);
      get(`${k.api}/words?scope=wrong&page=1`).then(r => {
        if (!r) return;
        for (const w of r.words.slice(0, WRONG_PREVIEW)) {
          const chip = document.createElement("button"); chip.className = "wchip";
          wordInto(chip, w);
          chip.onclick = () => openWordSheet(w.german, { de: "" });
          words.appendChild(chip);
        }
        if (r.total > WRONG_PREVIEW) {
          const more = document.createElement("span"); more.className = "meta"; more.textContent = `等 ${r.total} 个`;
          words.appendChild(more);
        }
      });
      const row = document.createElement("div"); row.className = "row";
      const all = document.createElement("button"); all.className = "secondary"; all.textContent = "全部 / 手动加词";
      all.onclick = () => wrongOpenList(k, b);
      const go1 = document.createElement("button"); go1.textContent = "练一组";
      go1.onclick = () => wrongStart(k);
      row.append(all, go1);
      card.appendChild(row);
    }
    box.appendChild(card);
  });
  $("wrongTotal").textContent = total
    ? `共 ${total} 个。答错的词会自动加进来，连续答对几次后自动移出。`
    : "现在没有错题。答错的词会自动加进来，连续答对几次后自动移出。";
};
