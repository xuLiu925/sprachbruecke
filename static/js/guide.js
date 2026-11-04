// 功能引导(文档 docs/features/guide.md)
// 1. 第一次登录后的导览: 在真实页面上把要介绍的按钮周围调亮、其他地方调暗, 配一句说明, 随时能跳过
// 2. 用到时才出现的小提示 tipOnce(key, 文字): 每条只出现一次, 点“知道了”关掉
// 看过哪些记在服务器(/api/guide), 换设备也不重复弹。游客不弹, 注册后第一次进来再弹

// 导览步骤: page = 要去的页面; open() = 自己打开(示范词详情页); el = 元素 id, 或 find() 找元素(可以是异步的);
// ready() = 内容加载好了没有; demo = 说明框里放一道示范题; fallback = el 看不见时改介绍的元素
// where = 说明框顶上的位置标签(这个功能平时从哪里进); 换到另一块功能前先停一步, 亮出它的入口
const tabBtn = name => () => document.querySelector(`#tabbar button[data-tab="${name}"]`);
const TOUR = [
  { page: "learn", el: "lWords", where: "学习 → 全部单词", showcase: true,
    text: "单词卡在这里：「学习」标签 → 全部单词，点任意一个词就能打开（也可以用顶上的搜索框查词）。下面用示范词 der Anruf 看看单词卡里有什么。" },
  { page: "view", open: () => openView(guideShow.id), ready: () => $("vWord").textContent.includes(guideShow.german),
    el: "vSpellBtn", where: "单词卡", text: "拼读：一个字母一个字母读给你听，再读整个词。看到生词也能跟着拼出来。" },
  { page: "view", el: "vGender", ready: () => $("vGender").textContent.length > 4, where: "单词卡",
    text: "词性解释：有规律的告诉你规律；没有规律的，AI 帮你编一句好记的联想，不再死记 der / die / das。" },
  { page: "view", el: "vParts", ready: () => $("vParts").textContent.includes("构词"), where: "单词卡",
    text: "AI 构词解释：长词拆开看，每部分什么意思、合起来为什么是这个词。" },
  { page: "view", find: showcaseNote, where: "单词卡 → 例句旁的“讲解”",
    text: "句子讲解：每个词是第几格、为什么这样变，语序和固定搭配都讲清楚，还有同样结构的例句。情景课、练习里的句子也能点“讲解”。" },
  { page: "practice", find: tabBtn("practice"), where: "底部「练习」标签",
    text: "单词卡就看到这里。接下来是练习：所有练习都在底部的「练习」标签里，按名词、动词、句子分好了组。" },
  { page: "practice", find: () => [...document.querySelectorAll("#pGroups button")].find(b => b.textContent.includes("der / die / das")),
    where: "练习 → 名词", text: "定冠词练习：在句子里练 der / die / das 和四个格，做错的自动进错题本。比如：",
    demo: { q: "Ich helfe ___ Frau.（die Frau）", opts: "die · der · den", a: "der", why: "helfen 后面用第三格，阴性第三格是 der" } },
  { page: "learn", el: "lNewLesson", where: "学习 → 情景课",
    text: "情景对话在「学习」标签往下翻的「情景课」里：点这里写下你想练的场景（租房、看医生、上班……），AI 写成课文，还能听、做练习、角色扮演。" },
  { page: "me", find: tabBtn("me"), where: "底部「我的」标签",
    text: "最后是「我的」标签：每日学习量、发音设置、会员、意见反馈都在这里。" },
  { page: "me", el: "installBox", fallback: "btnTour", where: "我的",
    text: "把通德装到手机桌面，像 App 一样一点就开。以后想再看这些介绍，在这页最下面点“重新看功能介绍”。",
    fallbackText: "这些介绍以后想再看，点这里。祝学习顺利！" },
];
const TAB_PAGES = ["home", "learn", "practice", "me"];

let guideSeen = null;      // 看过的引导; null = 还没取到
let guideShow = null;      // 示范词 {id, german, de}
let tourOn = false;
let tourStep = 0, tourSteps = [], tourEl = null;

async function guideLoad() {
  if (guideSeen) return guideSeen;
  try { const r = await api("/api/guide"); guideSeen = r.seen; guideShow = r.showcase; } catch (e) { guideSeen = null; }
  return guideSeen;
}
function guideMark(key) {
  if (guideSeen && !guideSeen.includes(key)) guideSeen.push(key);
  api("/api/guide", "POST", { key }).catch(() => {});
}

// 登录后调用(core.js 的 boot): 没看过导览就等安装引导页关掉、回到“今天”页再开始
async function maybeTour() {
  if (!user) return;
  const seen = await guideLoad();
  if (!seen || seen.includes("tour")) return;
  const wait = () => {
    if (!user || tourOn) return;
    if (!$("gate").classList.contains("hidden") || current !== "home") return setTimeout(wait, 800);
    startTour();
  };
  setTimeout(wait, 600);
}

function visible(el) {
  return el && !el.classList.contains("hidden") && el.offsetParent !== null;
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(fn, ms) {
  for (let t = 0; t < ms; t += 150) { try { if (fn()) return true; } catch (e) {} await sleep(150); }
  return false;
}

// 示范词例句的讲解: 点开“讲解”, 等内容出来(示范例句打开讲解不算 AI 次数)
async function showcaseNote() {
  const row = $("vExample").closest(".exrow"), box = row && row.nextElementSibling;
  const btn = box && box.querySelector("button"), note = box && box.querySelector(".lnote");
  if (!btn || !note) return null;
  if (note.classList.contains("hidden")) btn.click();
  await waitFor(() => note.dataset.loaded || /还没有|不能|错误|失败/.test(note.textContent), 6000);
  return note.dataset.loaded ? note : null;
}

async function startTour() {
  if (tourOn) return;
  tourOn = true;
  closeTip();
  await guideLoad();
  tourSteps = TOUR.filter(s => (s.page !== "view" && !s.showcase) || guideShow);   // 没有示范词就跳过单词卡这几步
  tourStep = 0;
  $("tour").classList.remove("hidden");
  showTourStep();
}

function endTour() {
  tourOn = false;
  tourEl = null;
  $("tour").classList.add("hidden");
  guideMark("tour");
  switchTab("home");
}

async function showTourStep() {
  if (!tourOn) return;
  if (tourStep >= tourSteps.length) return endTour();
  const s = tourSteps[tourStep], n = tourStep;
  $("tourBox").style.visibility = $("tourHole").style.visibility = "hidden";   // 放好位置再显示, 不闪
  if (current !== s.page) {
    if (s.open) s.open();
    else if (TAB_PAGES.includes(s.page)) switchTab(s.page);
    else go(s.page);
  }
  await sleep(300);
  if (s.ready) await waitFor(s.ready, 4000);
  let el = s.find ? await s.find() : $(s.el), text = s.text;
  if (!visible(el) && s.fallback) { el = $(s.fallback); text = s.fallbackText; }   // 已经装到桌面了, 没有安装卡片
  if (!tourOn || tourStep !== n) return;
  if (!visible(el)) { tourSteps.splice(tourStep, 1); return showTourStep(); }       // 内容没有就跳过这一步
  tourEl = el; s.shown = text;
  s.tall = el.getBoundingClientRect().height > innerHeight * 0.5;   // 很高的内容(讲解): 从开头看, 说明框放屏幕底下
  const scroll = () => {
    if (!s.tall) return el.scrollIntoView({ block: "center" });
    el.scrollIntoView({ block: "start" });
    document.scrollingElement.scrollTop -= 70;   // 让开顶栏
  };
  scroll();
  // 页面内容是异步加载的, 加载完元素会被挤到别处: 隔一会儿再对一次位置
  for (const ms of [200, 700, 1500]) setTimeout(() => {
    if (tourOn && tourStep === n) { if (ms > 200) scroll(); placeTour(el, s); }
  }, ms);
}
function replaceTour() {
  if (tourOn && visible(tourEl) && $("tourBox").style.visibility === "visible") placeTour(tourEl, tourSteps[tourStep]);
}

function placeTour(el, s) {
  const r = el.getBoundingClientRect(), pad = 6;
  const hole = $("tourHole"), box = $("tourBox");
  $("tourText").textContent = s.shown || s.text;
  $("tourWhere").textContent = s.where ? "位置：" + s.where : "";
  $("tourWhere").classList.toggle("hidden", !s.where);
  const demo = $("tourDemo");
  demo.textContent = "";
  demo.classList.toggle("hidden", !s.demo);
  if (s.demo) {
    const q = document.createElement("b"); q.textContent = s.demo.q;
    const o = document.createElement("div"); o.className = "meta left"; o.textContent = "选项：" + s.demo.opts;
    const a = document.createElement("div"); a.textContent = `答案：${s.demo.a} —— ${s.demo.why}`;
    demo.append(q, o, a);
  }
  $("tourNum").textContent = `${tourStep + 1} / ${tourSteps.length}`;
  $("tourNext").textContent = tourStep === tourSteps.length - 1 ? "开始使用" : "下一步";
  const h = box.offsetHeight || 160;
  let top = r.top - pad, bottom = r.bottom + pad, boxTop;
  if (s.tall) {                                  // 只亮能看到的那一段, 说明框贴底
    boxTop = innerHeight - h - 8;
    top = Math.max(top, 60);
    bottom = Math.min(bottom, boxTop - 8);
  } else {
    const below = r.bottom + 12, above = r.top - h - 12;
    boxTop = below + h < innerHeight - 8 ? below : above > 8 ? above : innerHeight - h - 8;
  }
  Object.assign(hole.style, { left: r.left - pad + "px", top: top + "px", width: r.width + pad * 2 + "px",
                              height: Math.max(0, bottom - top) + "px" });
  box.style.top = boxTop + "px";
  box.style.visibility = hole.style.visibility = "visible";
}

$("tourNext").onclick = () => { tourStep++; showTourStep(); };
$("tourSkip").onclick = endTour;
addEventListener("resize", replaceTour);
addEventListener("scroll", replaceTour, true);
$("btnTour").onclick = () => { if (!tourOn) startTour(); };

// ---------- 用到时的小提示 ----------
let tipKey = null;
async function tipOnce(key, text) {
  if (!user || tourOn || tipKey) return;
  const seen = await guideLoad();
  if (!seen || seen.includes(key) || tipKey || tourOn) return;
  tipKey = key;
  guideMark(key);           // 出现过就算看过, 下次不再出现
  $("tipText").textContent = text;
  $("tip").classList.remove("hidden");
}
function closeTip() {
  tipKey = null;
  $("tip").classList.add("hidden");
}
$("tipOk").onclick = closeTip;
