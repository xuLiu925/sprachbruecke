// 功能引导(文档 docs/features/guide.md)
// 1. 第一次登录后的导览: 在真实页面上把要介绍的按钮周围调亮、其他地方调暗, 配一句说明, 随时能跳过
// 2. 用到时才出现的小提示 tipOnce(key, 文字): 每条只出现一次, 点“知道了”关掉
// 看过哪些记在服务器(/api/guide), 换设备也不重复弹。游客不弹, 注册后第一次进来再弹

const TOUR = [
  { tab: "home", el: "hStart", text: "每天点这里就够了：先复习快忘的词，再学新词。学多少可以在这页调。" },
  { tab: "home", el: "btnSearch", text: "随时查德语或中文，查到的词能直接加进学习。电脑上按 / 也能打开。" },
  { tab: "learn", el: "lBookSwitch", text: "选 A1–C1 或专题单词书，按你的水平来。下面还有语法知识点和情景课。" },
  { tab: "practice", el: "pWrongCard", text: "冠词、复数、动词、句子都在练习页。做错的题自动进错题本，在这里专门练。" },
  { tab: "me", el: "installBox", text: "装到手机桌面，像 App 一样打开，不用每次找网址。" },
  { tab: "me", el: "btnTour", text: "这些介绍以后想再看，点这里。祝学习顺利！" },
];

let guideSeen = null;      // 看过的引导; null = 还没取到
let tourOn = false;
let tourStep = 0, tourSteps = [];

async function guideLoad() {
  if (guideSeen) return guideSeen;
  try { guideSeen = (await api("/api/guide")).seen; } catch (e) { guideSeen = null; }
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

function startTour() {
  if (tourOn) return;
  tourOn = true;
  closeTip();
  tourSteps = TOUR.slice();
  tourStep = 0;
  $("tour").classList.remove("hidden");
  showTourStep();
}

function endTour() {
  tourOn = false;
  $("tour").classList.add("hidden");
  guideMark("tour");
  switchTab("home");
}

function showTourStep() {
  if (!tourOn) return;
  if (tourStep >= tourSteps.length) return endTour();
  const s = tourSteps[tourStep];
  $("tourBox").style.visibility = $("tourHole").style.visibility = "hidden";   // 放好位置再显示, 不闪
  if (current !== s.tab) switchTab(s.tab);
  setTimeout(() => {               // 等页面切换、内容出来
    const el = $(s.el);
    if (!visible(el)) { tourSteps.splice(tourStep, 1); return showTourStep(); }   // 比如已经装到桌面了, 没有安装卡片
    el.scrollIntoView({ block: "center" });
    const n = tourStep;
    // 页面内容是异步加载的, 加载完按钮会被挤到别处: 隔一会儿再对一次位置
    for (const ms of [250, 700, 1500]) setTimeout(() => {
      if (tourOn && tourStep === n) { if (ms > 250) el.scrollIntoView({ block: "center" }); placeTour(el, s.text); }
    }, ms);
  }, 250);
}
function replaceTour() {
  const s = tourOn && tourSteps[tourStep], el = s && $(s.el);
  if (visible(el) && $("tourBox").style.visibility === "visible") placeTour(el, s.text);
}

function placeTour(el, text) {
  const r = el.getBoundingClientRect(), pad = 6;
  const hole = $("tourHole");
  Object.assign(hole.style, { left: r.left - pad + "px", top: r.top - pad + "px",
                              width: r.width + pad * 2 + "px", height: r.height + pad * 2 + "px" });
  $("tourText").textContent = text;
  $("tourNum").textContent = `${tourStep + 1} / ${tourSteps.length}`;
  $("tourNext").textContent = tourStep === tourSteps.length - 1 ? "开始使用" : "下一步";
  const box = $("tourBox"), below = r.bottom + 12, h = box.offsetHeight || 140;
  box.style.top = (below + h < innerHeight - 8 ? below : Math.max(8, r.top - h - 12)) + "px";
  box.style.visibility = hole.style.visibility = "visible";
}

$("tourNext").onclick = () => { tourStep++; showTourStep(); };
$("tourSkip").onclick = endTour;
addEventListener("resize", replaceTour);
addEventListener("scroll", replaceTour, true);
$("btnTour").onclick = () => { if (!tourOn) { guideLoad(); startTour(); } };

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
