// 新建情景对话: 描述场景(可以点场景按钮填一个例子) → AI 生成草稿(或复制提示词到免费 AI, 再粘贴回来) → 修改 → 保存成课程
let lnDraft = null;

function lnMsg(text, ok) {
  $("lnMsg").textContent = text || "";
  $("lnMsg").className = ok ? "ok" : "msg";
}
function lnBody() {
  const want = $("lnWant").value.trim();
  if (want.length < 4) { lnMsg("请先写一下想练的场景"); return null; }
  return { level: $("lnLevel").value, request: want };
}

// 场景按钮: 点了把例子填进描述框, 用户再改
const LN_SCENES = [
  ["工作", "上班第一天，同事带我熟悉工作，我问清楚工作时间、休息和要注意的事"],
  ["Ausbildung", "和培训企业的带教师傅谈这个月的学习计划，还有职业学校的课"],
  ["租房", "给房东打电话，约时间看房，问租金、押金和什么时候能搬进去"],
  ["看医生", "在诊所前台挂号，然后向医生说明哪里不舒服、持续了几天"],
  ["办手续", "在外管局（Ausländerbehörde）办居留许可，问需要带哪些材料"],
  ["大学", "去学生办公室问注册、选课和学期费用"],
  ["购物", "在超市找不到东西，问店员；在收银台付款，问能不能刷卡"],
  ["仓库", "司机来提货，发现少了一托，我要核对提货单并联系主管"],
];
function lnScenes() {
  const box = $("lnScenes");
  if (box.childElementCount) return;
  for (const [name, text] of LN_SCENES) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = name;
    b.onclick = () => {
      $("lnWant").value = text; $("lnWant").focus();
      for (const x of box.children) x.classList.toggle("on", x === b);
    };
    box.append(b);
  }
}

onShow.lnew = async () => {
  lnScenes();
  lnMsg("");
  try { await loadLessons(); } catch (e) { return toast(e.message); }
  $("lnGen").disabled = !lessonAi;
  $("lnGen").textContent = !lessonAi ? "还没有配置 API Key" : lessonMember ? "AI 生成对话" : "AI 生成对话（会员功能）";
  $("lnManual").open = !lessonAi;
};

async function lnGenerate() {
  const body = lnBody();
  if (!body) return;
  lnMsg(""); $("lnGen").disabled = true; $("lnRegen").disabled = true;
  const label = $("lnGen").textContent;
  $("lnGen").textContent = "AI 正在写，大约要 20 秒…";
  try { lnPreview((await api("/api/custom_lessons/generate", "POST", body)).lesson); }
  catch (e) { lnMsg(e.message); if (e.status === 429 || e.status === 503) $("lnManual").open = true; }
  $("lnGen").disabled = !lessonAi; $("lnRegen").disabled = false; $("lnGen").textContent = label;
}
$("lnGen").onclick = lnGenerate;
$("lnRegen").onclick = lnGenerate;

$("lnCopy").onclick = async () => {
  const body = lnBody();
  if (!body) return;
  try { copyText((await api("/api/custom_lessons/prompt", "POST", body)).prompt); }
  catch (e) { lnMsg(e.message); }
};
$("lnCheck").onclick = async () => {
  lnMsg("");
  try {
    const r = await api("/api/custom_lessons/check", "POST", { level: $("lnLevel").value, text: $("lnPaste").value });
    lnPreview(r.lesson);
    $("lnPaste").value = "";
  } catch (e) { lnMsg(e.message); }
};

function lnField(tag, value, cls) {
  const el = document.createElement(tag);
  el.value = value; el.className = cls;
  el.spellcheck = false;
  return el;
}

// 预览: 句子可以直接改, 保存时后端会去掉对不上的填空题
function lnPreview(lesson) {
  lnDraft = lesson;
  $("lnTitle").value = lesson.title;
  $("lnScene").value = lesson.scene;
  const box = $("lnLines"); box.textContent = "";
  for (const line of lesson.lines) {
    const row = document.createElement("div"); row.className = "lline";
    const who = document.createElement("div"); who.className = "lwho"; who.textContent = line.who;
    const de = lnField("textarea", line.de, "lnedit"), zh = lnField("textarea", line.zh, "lnedit");
    de.oninput = () => { line.de = de.value; };
    zh.oninput = () => { line.zh = zh.value; };
    row.append(who, de, zh);
    box.appendChild(row);
  }
  $("lnPreview").classList.remove("hidden");
  $("lnPreview").scrollIntoView({ behavior: "smooth" });
}

$("lnSave").onclick = async () => {
  if (!lnDraft) return;
  const body = { ...lnDraft, level: $("lnLevel").value, title: $("lnTitle").value, scene: $("lnScene").value };
  let r;
  try { r = await api("/api/custom_lessons", "POST", body); } catch (e) { return lnMsg(e.message); }
  lessons = null; lessonShown = null; lnDraft = null;
  $("lnPreview").classList.add("hidden");
  $("lnWant").value = "";
  try { await loadLessons(); } catch (e) { return toast(e.message); }
  lessonNow = lessons.find(x => x.id === r.lesson.id) || null;
  toast("已保存");
  location.replace("#lesson");
};
