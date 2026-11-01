// 拼读: 逐个字母读字母名, 读到哪个高亮哪个, 最后读一遍整词。再点一次停止
const SPELL_GAP = 120;              // 字母之间停一下, 毫秒
const SPELL_WAIT = 5000;            // 朗读没有回调时最多等这么久, 不让拼读卡住
let spellUtter = null;              // 留住引用: 有的浏览器会回收朗读对象, 读完不通知

const spellName = ch => (ch === "ß" ? "Eszett" : ch.toUpperCase());

function speakOne(text, rate) {
  return new Promise(done => {
    const timer = setTimeout(done, SPELL_WAIT);
    const finish = () => { clearTimeout(timer); done(); };
    if (useOnlineVoice()) {         // 同一个 Audio 反复用: 手机浏览器只放行点击时开始播放的那个
      const a = spellAudio || (spellAudio = new Audio());
      a.onended = finish;
      a.onerror = () => { spellUtter = speakSystem(text, false, rate, finish); };   // 取不到就退回系统语音
      a.src = "/api/tts?q=" + encodeURIComponent(text);
      a.defaultPlaybackRate = rate; a.playbackRate = rate;
      a.play().catch(finish);
    } else if ("speechSynthesis" in window) {
      spellUtter = speakSystem(text, false, rate, finish);
    } else finish();
  });
}

function spellStop() { if (spellOn) stopSpeak(); }
function spellReset(box) { spellStop(); box.textContent = ""; }

async function spellWord(word, box) {
  const wasOn = spellOn;
  stopSpeak();
  if (wasOn) return;
  box.textContent = "";
  const spans = [...word].map(ch => {
    const s = document.createElement("span"); s.textContent = ch;
    box.appendChild(s);
    return s;
  });
  const run = spellRun, rate = getSetting("rate");
  spellOn = true;
  for (const s of spans) {
    if (!/\p{L}/u.test(s.textContent)) continue;      // 空格和连字符不读
    s.className = "on";
    await speakOne(spellName(s.textContent), rate);
    s.className = "";
    if (run !== spellRun) return;
    await new Promise(r => setTimeout(r, SPELL_GAP));
    if (run !== spellRun) return;
  }
  await speakOne(word, rate);
  if (run === spellRun) spellOn = false;
}
