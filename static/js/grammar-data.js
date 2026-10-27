// 语法基础的内容(第一批)。表格和题目都在这里, 页面逻辑在 grammar.js
// 内容是 Claude 按标准德语语法整理的, 用来学习前最好对照教材或请母语者核对一遍

const CASE_NAMES = ["第一格 Nom.", "第四格 Akk.", "第三格 Dat.", "第二格 Gen."];
const GENDER_HEAD = ["", "阳性", "阴性", "中性", "复数"];

// 冠词题用的名词: [第一格, 第四格, 第三格, 第二格] 时名词本身的形式
const QUIZ_NOUNS = {
  m: ["Mann", "Mann", "Mann", "Mannes"],
  f: ["Frau", "Frau", "Frau", "Frau"],
  n: ["Kind", "Kind", "Kind", "Kindes"],
  pl: ["Kinder", "Kinder", "Kindern", "Kinder"],
};
const POSS_NOUNS = {   // 物主冠词题用家里人, 句子更自然
  m: ["Vater", "Vater", "Vater", "Vaters"],
  f: ["Mutter", "Mutter", "Mutter", "Mutter"],
  n: ["Kind", "Kind", "Kind", "Kindes"],
  pl: ["Eltern", "Eltern", "Eltern", "Eltern"],
};
// 每个格的句子框架: 单数 / 复数
const CASE_FRAMES = [
  ["Das ist ___ {n}.", "Das sind ___ {n}."],
  ["Ich sehe ___ {n}.", "Ich sehe ___ {n}."],
  ["Ich spreche mit ___ {n}.", "Ich spreche mit ___ {n}."],
  ["Das ist das Auto ___ {n}.", "Das ist das Auto ___ {n}."],
];

// 定冠词: [格][阳, 阴, 中, 复]
const DEF_ARTICLES = [
  ["der", "die", "das", "die"],
  ["den", "die", "das", "die"],
  ["dem", "der", "dem", "den"],
  ["des", "der", "des", "der"],
];
// 每个格怎么看出来(题目解释用)
const CASE_REASON = ["Das ist / sind … 后面是第一格", "sehen + 第四格", "mit + 第三格", "“…的” 用第二格"];

// kein / ein / 物主冠词的词尾: [格][阳, 阴, 中, 复]
const KEIN_ENDINGS = [
  ["", "e", "", "e"],
  ["en", "e", "", "e"],
  ["em", "er", "em", "en"],
  ["es", "er", "es", "er"],
];
const POSSESSIVES = [
  ["ich", "mein"], ["du", "dein"], ["er", "sein"], ["sie（她）", "ihr"], ["es", "sein"],
  ["wir", "unser"], ["ihr（你们）", "euer"], ["sie（他们）", "ihr"], ["Sie（您）", "Ihr"],
];
// euer 加词尾时去掉 e: eure, euren …
const possForm = (stem, ending) => (stem === "euer" && ending ? "eur" : stem) + ending;

const PERSONS6 = ["ich", "du", "er / sie / es", "wir", "ihr", "sie / Sie"];
const VERBS = {
  sein: ["bin", "bist", "ist", "sind", "seid", "sind"],
  haben: ["habe", "hast", "hat", "haben", "habt", "haben"],
  werden: ["werde", "wirst", "wird", "werden", "werdet", "werden"],
  "können": ["kann", "kannst", "kann", "können", "könnt", "können"],
  "müssen": ["muss", "musst", "muss", "müssen", "müsst", "müssen"],
  "dürfen": ["darf", "darfst", "darf", "dürfen", "dürft", "dürfen"],
  sollen: ["soll", "sollst", "soll", "sollen", "sollt", "sollen"],
  wollen: ["will", "willst", "will", "wollen", "wollt", "wollen"],
  "mögen": ["mag", "magst", "mag", "mögen", "mögt", "mögen"],
  "möchten": ["möchte", "möchtest", "möchte", "möchten", "möchtet", "möchten"],
};

const PRONOUNS = {
  head: ["", "ich", "du", "er", "sie（她）", "es", "wir", "ihr（你们）", "sie（他们）", "Sie（您）"],
  nom: ["ich", "du", "er", "sie", "es", "wir", "ihr", "sie", "Sie"],
  akk: ["mich", "dich", "ihn", "sie", "es", "uns", "euch", "sie", "Sie"],
  dat: ["mir", "dir", "ihm", "ihr", "ihm", "uns", "euch", "ihnen", "Ihnen"],
};

// 介词填空题: [句子, 答案, 解释]
const PREP_AKK_SENTENCES = [
  ["Ich kaufe ein Geschenk für ___ Vater.", "den", "für + 第四格；der Vater → den Vater"],
  ["Wir gehen durch ___ Park.", "den", "durch + 第四格；der Park → den Park"],
  ["Er fährt gegen ___ Baum.", "den", "gegen + 第四格；der Baum → den Baum"],
  ["Wir sitzen um ___ Tisch.", "den", "um + 第四格；der Tisch → den Tisch"],
  ["Das Geschenk ist für ___ Kind.", "das", "für + 第四格；das Kind 第四格还是 das"],
  ["Ich laufe durch ___ Stadt.", "die", "durch + 第四格；die Stadt 第四格还是 die"],
  ["Ohne ___ Brille sehe ich nichts.", "die", "ohne + 第四格；die Brille 第四格还是 die"],
];
const PREP_DAT_SENTENCES = [
  ["Ich fahre mit ___ Bus.", "dem", "mit + 第三格；der Bus → dem Bus"],
  ["Sie kommt aus ___ Schweiz.", "der", "aus + 第三格；die Schweiz → der Schweiz"],
  ["Er wohnt bei ___ Eltern.", "den", "bei + 第三格；复数 die Eltern → den Eltern"],
  ["Nach ___ Unterricht gehe ich nach Hause.", "dem", "nach + 第三格；der Unterricht → dem Unterricht"],
  ["Seit ___ Sommer lerne ich Deutsch.", "dem", "seit + 第三格；der Sommer → dem Sommer"],
  ["Das ist ein Brief von ___ Mutter.", "der", "von + 第三格；die Mutter → der Mutter"],
  ["Ich gehe zu ___ Ärztin.", "der", "zu + 第三格；die Ärztin → der Ärztin"],
  ["Er spielt mit ___ Kindern.", "den", "mit + 第三格；复数 die Kinder → den Kindern（名词也加 -n）"],
];
const PREP_TWOWAY_SENTENCES = [
  ["Das Buch liegt auf ___ Tisch.", "dem", "Wo?（在哪里，静止）→ 第三格：auf dem Tisch"],
  ["Ich lege das Buch auf ___ Tisch.", "den", "Wohin?（放到哪里，有方向）→ 第四格：auf den Tisch"],
  ["Die Katze schläft unter ___ Bett.", "dem", "Wo? → 第三格：unter dem Bett"],
  ["Die Katze läuft unter ___ Bett.", "das", "Wohin?（跑到床底下）→ 第四格：unter das Bett"],
  ["Wir sitzen in ___ Küche.", "der", "Wo? → 第三格：in der Küche"],
  ["Wir gehen in ___ Küche.", "die", "Wohin? → 第四格：in die Küche"],
  ["Das Bild hängt an ___ Wand.", "der", "Wo? → 第三格：an der Wand"],
  ["Ich hänge das Bild an ___ Wand.", "die", "Wohin? → 第四格：an die Wand"],
  ["Das Auto steht vor ___ Haus.", "dem", "Wo? → 第三格：vor dem Haus"],
  ["Er stellt das Fahrrad vor ___ Haus.", "das", "Wohin? → 第四格：vor das Haus"],
  ["Er sitzt neben ___ Frau.", "der", "Wo? → 第三格：neben der Frau"],
  ["Er setzt sich neben ___ Frau.", "die", "Wohin? → 第四格：neben die Frau"],
];

// 语序选择题: [正确的句子, 错误1, 错误2, 解释]
const ORDER_MAIN = [
  ["Heute gehe ich ins Kino.", "Heute ich gehe ins Kino.", "Heute ich ins Kino gehe.",
   "句首是 Heute，变位动词 gehe 还是在第二位，主语 ich 放到动词后面（倒装）"],
  ["Ich kann heute nicht kommen.", "Ich kann kommen heute nicht.", "Ich heute kann nicht kommen.",
   "情态动词 kann 在第二位，不定式 kommen 放句末（框架结构）"],
  ["Ich habe gestern Deutsch gelernt.", "Ich habe gelernt gestern Deutsch.", "Ich gestern habe Deutsch gelernt.",
   "助动词 habe 在第二位，过去分词 gelernt 放句末"],
  ["Ich stehe jeden Tag um 7 Uhr auf.", "Ich aufstehe jeden Tag um 7 Uhr.", "Ich stehe auf jeden Tag um 7 Uhr.",
   "可分动词 aufstehen：stehe 在第二位，前缀 auf 放句末"],
  ["Wann kommst du nach Hause?", "Wann du kommst nach Hause?", "Wann kommst nach Hause du?",
   "W-问句：疑问词第一位，动词第二位，然后是主语"],
  ["Kommst du morgen?", "Morgen du kommst?", "Du morgen kommst?",
   "是非问句：变位动词放第一位"],
  ["Morgen fahren wir nach Berlin.", "Morgen wir fahren nach Berlin.", "Wir morgen fahren nach Berlin.",
   "句首是 Morgen，动词 fahren 在第二位，主语 wir 跟在后面"],
];
const ORDER_SUB = [
  ["Ich bleibe zu Hause, weil ich krank bin.", "Ich bleibe zu Hause, weil ich bin krank.", "Ich bleibe zu Hause, weil bin ich krank.",
   "weil 引导从句，变位动词 bin 放最后（口语里常听到 weil ich bin…，但书面语算错）"],
  ["Ich weiß, dass er morgen kommt.", "Ich weiß, dass er kommt morgen.", "Ich weiß, dass kommt er morgen.",
   "dass 从句：变位动词 kommt 放最后"],
  ["Weil ich müde bin, gehe ich nach Hause.", "Weil ich müde bin, ich gehe nach Hause.", "Weil bin ich müde, gehe ich nach Hause.",
   "从句放在前面时，整个从句算第一位，主句的动词 gehe 紧跟在逗号后面"],
  ["Er sagt, dass er nicht kommen kann.", "Er sagt, dass er kann nicht kommen.", "Er sagt, dass er nicht kann kommen.",
   "从句里有情态动词：不定式在前，变位的 kann 在最后"],
  ["Wenn das Wetter gut ist, gehen wir spazieren.", "Wenn das Wetter ist gut, gehen wir spazieren.", "Wenn das Wetter gut ist, wir gehen spazieren.",
   "wenn 从句动词放最后；从句在前，主句动词 gehen 紧跟逗号"],
  ["Ich rufe dich an, wenn ich ankomme.", "Ich rufe dich an, wenn ich komme an.", "Ich rufe dich an, wenn ich an komme.",
   "可分动词在从句里合在一起写，放最后：ankomme"],
  ["Ich lerne Deutsch, denn ich will in Deutschland studieren.", "Ich lerne Deutsch, denn ich in Deutschland studieren will.", "Ich lerne Deutsch, denn will ich in Deutschland studieren.",
   "denn 和 und / aber / oder 一样不影响语序，后面还是正常的主句语序"],
  ["Ich weiß nicht, ob er heute kommt.", "Ich weiß nicht, ob er kommt heute.", "Ich weiß nicht, ob kommt er heute.",
   "ob（是否）也引导从句，动词放最后"],
];

// ---------- 形容词词尾(第二批) ----------
// [格][阳, 阴, 中, 复]
const WEAK_END = [["e", "e", "e", "en"], ["en", "e", "e", "en"], ["en", "en", "en", "en"], ["en", "en", "en", "en"]];
const MIXED_END = [["er", "e", "es", "en"], ["en", "e", "es", "en"], ["en", "en", "en", "en"], ["en", "en", "en", "en"]];
const STRONG_END = [["er", "e", "es", "e"], ["en", "e", "es", "e"], ["em", "er", "em", "en"], ["en", "er", "en", "er"]];
const endingRows = table => table.map((r, c) => [CASE_NAMES[c], ...r.map(e => "-" + e)]);

// 弱变化 / 混合变化的题: 冠词 + ___ + 名词, 括号里给形容词原形
const ADJ_PEOPLE = ["nett", "klein", "neu", "freundlich"];   // 配 Mann / Frau / Kind 都自然的形容词
const ADJ_FRAMES = [
  ["Das ist {a} ___ {n}.", "Das sind {a} ___ {n}."],
  ["Ich sehe {a} ___ {n}.", "Ich sehe {a} ___ {n}."],
  ["Ich spreche mit {a} ___ {n}.", "Ich spreche mit {a} ___ {n}."],
  ["Das ist das Auto {a} ___ {n}.", "Das ist das Auto {a} ___ {n}."],
];
// 混合变化的冠词: 单数用 ein, 复数用 meine(ein 没有复数)
const mixedArticle = (c, gi) => gi === 3 ? possForm("mein", KEIN_ENDINGS[c][3]) : "ein" + KEIN_ENDINGS[c][gi];

// 强变化(没有冠词)的题: [格, 性, 句子, 能用的形容词]。第二格太少见, 不出题
const STRONG_ITEMS = [
  [0, "m", "Das ist ___ Wein.", ["gut", "rot"]],
  [0, "f", "Das ist ___ Milch.", ["frisch", "warm"]],
  [0, "n", "Das ist ___ Bier.", ["kalt", "gut"]],
  [0, "pl", "Das sind ___ Äpfel.", ["frisch", "rot"]],
  [1, "m", "Ich trinke gern ___ Wein.", ["rot", "gut"]],
  [1, "m", "Ich habe ___ Hunger.", ["groß"]],
  [1, "f", "Ich trinke gern ___ Milch.", ["warm", "kalt"]],
  [1, "n", "Ich trinke gern ___ Bier.", ["kalt"]],
  [1, "pl", "Ich kaufe ___ Äpfel.", ["frisch", "grün"]],
  [2, "m", "Ich koche mit ___ Wein.", ["rot"]],
  [2, "f", "Ich trinke Kaffee mit ___ Milch.", ["warm", "kalt"]],
  [2, "n", "Ich wasche mich mit ___ Wasser.", ["kalt", "warm"]],
  [2, "pl", "Ich backe einen Kuchen mit ___ Äpfeln.", ["frisch"]],
];
const ADJ_TYPE_NAME = { weak: "定冠词后（弱变化）", mixed: "ein / kein / mein 后（混合变化）", strong: "没有冠词（强变化）" };

// ---------- 比较级(第二批) ----------
// [原级, 比较级, 最高级, 比较级的常见错法, 最高级的常见错法, 规则说明]
// 错误选项是手写的, 避开了其实也对的写法(瑞士的 grössten、也能用的 neusten 等)
// 也不用 größerer 这种: 它是「比较级 + 形容词词尾」(ein größerer Mann), 是真实存在的形式
const COMPARISON = [
  ["schnell", "schneller", "am schnellsten", ["schnellster", "mehr schnell"], ["am schnellesten", "am schneller"], "一般规则：-er / am -sten"],
  ["klein", "kleiner", "am kleinsten", ["kleinster", "mehr klein"], ["am kleinesten", "am kleiner"], "一般规则：-er / am -sten"],
  ["schwer", "schwerer", "am schwersten", ["schwerster", "mehr schwer"], ["am schweresten", "am schwerer"], "一般规则：-er / am -sten"],
  ["alt", "älter", "am ältesten", ["alter", "ältest"], ["am ältsten", "am altesten"], "单音节变音 a → ä；以 -t 结尾，最高级加 -esten"],
  ["jung", "jünger", "am jüngsten", ["junger", "jüngest"], ["am jungsten", "am jüngesten"], "单音节变音 u → ü"],
  ["lang", "länger", "am längsten", ["langer", "lenger"], ["am langsten", "am längesten"], "单音节变音 a → ä"],
  ["kurz", "kürzer", "am kürzesten", ["kurzer", "mehr kurz"], ["am kürzsten", "am kurzesten"], "变音 u → ü；以 -z 结尾，最高级加 -esten"],
  ["warm", "wärmer", "am wärmsten", ["warmer", "mehr warm"], ["am warmsten", "am wärmesten"], "单音节变音 a → ä"],
  ["kalt", "kälter", "am kältesten", ["kalter", "mehr kalt"], ["am kältsten", "am kaltesten"], "变音 a → ä；以 -t 结尾，最高级加 -esten"],
  ["stark", "stärker", "am stärksten", ["starker", "mehr stark"], ["am starksten", "am stärkesten"], "单音节变音 a → ä"],
  ["klug", "klüger", "am klügsten", ["kluger", "mehr klug"], ["am klugsten", "am klügesten"], "单音节变音 u → ü"],
  ["arm", "ärmer", "am ärmsten", ["armer", "mehr arm"], ["am armsten", "am ärmesten"], "单音节变音 a → ä"],
  ["laut", "lauter", "am lautesten", ["läuter", "mehr laut"], ["am lautsten", "am läutesten"], "au 不变音；以 -t 结尾，最高级加 -esten"],
  ["heiß", "heißer", "am heißesten", ["mehr heiß", "häßer"], ["am heißsten", "am heißten"], "以 -ß 结尾，最高级加 -esten"],
  ["süß", "süßer", "am süßesten", ["mehr süß", "sußer"], ["am süßten", "am süßsten"], "以 -ß 结尾，最高级加 -esten"],
  ["interessant", "interessanter", "am interessantesten", ["mehr interessant", "interessantester"], ["am interessantsten", "am meisten interessant"], "长的形容词也直接加 -er，不用 mehr；以 -t 结尾加 -esten"],
  ["dunkel", "dunkler", "am dunkelsten", ["dunkeler", "dunkelster"], ["am dunklesten", "am dunkelesten"], "-el 结尾：比较级去掉 e"],
  ["teuer", "teurer", "am teuersten", ["teuerster", "mehr teuer"], ["am teursten", "am teurersten"], "-er 结尾：比较级去掉 e（teurer）"],
  ["groß", "größer", "am größten", ["großer", "mehr groß"], ["am größesten", "am großten"], "变音 o → ö；最高级例外：am größten（不加 -e-）"],
  ["gut", "besser", "am besten", ["guter", "güter"], ["am gutesten", "am bessersten"], "不规则"],
  ["viel", "mehr", "am meisten", ["vieler", "mehrer"], ["am vielsten", "am mehrsten"], "不规则"],
  ["gern", "lieber", "am liebsten", ["gerner", "mehr gern"], ["am gernsten", "am liebesten"], "不规则"],
  ["hoch", "höher", "am höchsten", ["hocher", "höcher"], ["am hochsten", "am höhesten"], "不规则：比较级去掉 c（höher）"],
  ["nah", "näher", "am nächsten", ["naher", "nächer"], ["am nähesten", "am nahsten"], "不规则：最高级 am nächsten"],
];

// 比较句填空: [句子, 答案, 选项, 解释]
const COMPARE_SENTENCES = [
  ["Mein Bruder ist drei Jahre ___ als ich.", "älter", ["älter", "alter", "am ältesten", "ältesten"], "比较“更…”：比较级 + als；alt → älter"],
  ["Berlin ist größer ___ München.", "als", ["als", "wie", "dann", "so"], "比较级后面用 als"],
  ["Ich bin so groß ___ mein Vater.", "wie", ["wie", "als", "so", "dann"], "“一样…”：so + 原级 + wie"],
  ["Mein Handy ist nicht so neu ___ deins.", "wie", ["wie", "als", "so", "dann"], "nicht so … wie：没有…那么…"],
  ["Im Sommer ist es ___ als im Winter.", "wärmer", ["wärmer", "warmer", "am wärmsten", "mehr warm"], "warm → wärmer（变音）"],
  ["Anna läuft ___ von allen.", "am schnellsten", ["am schnellsten", "schneller", "schnellste", "am schneller"], "单独用（修饰动词）的最高级：am …sten"],
  ["Das ist der ___ Berg in Deutschland.", "höchste", ["höchste", "höchsten", "am höchsten", "hohe"], "名词前的最高级：der …ste + 名词，词尾跟定冠词后的形容词一样（第一格阳性 -e）"],
  ["Ich trinke ___ Tee als Kaffee.", "lieber", ["lieber", "gerner", "am liebsten", "mehr"], "gern 的比较级是 lieber（不规则）"],
  ["Heute ist das Wetter ___ als gestern.", "besser", ["besser", "guter", "am besten", "mehr gut"], "gut 的比较级是 besser（不规则）"],
  ["Er hat ___ Geld als ich.", "mehr", ["mehr", "vieler", "am meisten", "viele"], "viel 的比较级是 mehr（不规则，不加词尾）"],
  ["Das ist ein ___ Auto als meins.", "teureres", ["teureres", "teurer", "teureren", "teuerer"], "比较级放在名词前也要加形容词词尾：ein + 中性第一格 → -es，teurer + es = teureres"],
  ["Je mehr ich lerne, ___ besser spreche ich.", "desto", ["desto", "als", "wie", "so"], "je + 比较级 …, desto + 比较级 …：越…越…"],
  ["Es wird immer ___.", "kälter", ["kälter", "kalter", "am kältesten", "mehr kalt"], "immer + 比较级：越来越…"],
  ["Sie ist die ___ Schülerin in der Klasse.", "klügste", ["klügste", "klügsten", "am klügsten", "klugste"], "名词前的最高级：die …ste + 名词（第一格阴性 -e）；klug → klügst-"],
];

// ---------- 完成时(第二批) ----------
// [不定式, 过去分词, 常见错法(手写), 规则]
const PARTICIPLES = [
  ["machen", "gemacht", ["gemachen", "gemachtet", "machte"], "规则动词：ge- + 词干 + -t"],
  ["kaufen", "gekauft", ["gekaufen", "gekauftet", "kaufte"], "规则动词：ge- + 词干 + -t"],
  ["lernen", "gelernt", ["gelernen", "gelerntet", "lernte"], "规则动词：ge- + 词干 + -t"],
  ["wohnen", "gewohnt", ["gewohnen", "gewohntet", "wohnte"], "规则动词：ge- + 词干 + -t"],
  ["arbeiten", "gearbeitet", ["gearbeitt", "gearbeiten", "arbeitete"], "词干以 -t 结尾：加 -et"],
  ["warten", "gewartet", ["gewartt", "gewarten", "wartete"], "词干以 -t 结尾：加 -et"],
  ["fahren", "gefahren", ["gefahrt", "gefuhren", "fuhr"], "不规则：ge- + 词干 + -en"],
  ["sehen", "gesehen", ["gesieht", "gesehet", "gesahen"], "不规则：ge- + 词干 + -en"],
  ["schreiben", "geschrieben", ["geschreibt", "geschreiben", "geschriebt"], "不规则：ei → ie"],
  ["trinken", "getrunken", ["getrinkt", "getrinken", "getrank"], "不规则：i → u"],
  ["finden", "gefunden", ["gefindet", "gefinden", "gefanden"], "不规则：i → u"],
  ["sprechen", "gesprochen", ["gesprecht", "gesprechen", "gesprachen"], "不规则：e → o"],
  ["nehmen", "genommen", ["genehmt", "genehmen", "genahmen"], "不规则：e → o，还多一个 m"],
  ["gehen", "gegangen", ["gegeht", "gegehen", "gegingen"], "不规则（要单独记）"],
  ["kommen", "gekommen", ["gekommt", "gekamen", "gekammen"], "不规则：ge- + kommen"],
  ["schlafen", "geschlafen", ["geschlaft", "geschliefen", "geschläft"], "不规则：ge- + 词干 + -en"],
  ["essen", "gegessen", ["geesst", "geessen", "gegesst"], "不规则（特殊：gegessen）"],
  ["sein", "gewesen", ["gesein", "geseint", "gesind"], "不规则（要单独记）"],
  ["haben", "gehabt", ["gehaben", "gehat", "gehabtet"], "haben 是规则的：ge- + hab + -t"],
  ["werden", "geworden", ["gewerdet", "gewurden", "gewordet"], "不规则：e → o"],
  ["bringen", "gebracht", ["gebringt", "gebrungen", "gebringen"], "混合动词：换元音，但词尾是 -t"],
  ["denken", "gedacht", ["gedenkt", "gedunken", "gedanken"], "混合动词：换元音，但词尾是 -t"],
  ["wissen", "gewusst", ["gewisst", "gewussen", "gewiesst"], "混合动词：换元音，但词尾是 -t"],
  ["kennen", "gekannt", ["gekennt", "gekonnen", "gekannen"], "混合动词：换元音，但词尾是 -t"],
  ["aufstehen", "aufgestanden", ["geaufstanden", "aufstanden", "aufgesteht"], "可分动词：ge 放在前缀和词干中间"],
  ["einkaufen", "eingekauft", ["geeinkauft", "einkauft", "eingekaufen"], "可分动词：ge 放在前缀和词干中间"],
  ["anrufen", "angerufen", ["geanrufen", "angeruft", "angerief"], "可分动词：ge 放在中间（rufen → gerufen）"],
  ["fernsehen", "ferngesehen", ["gefernsehen", "ferngesieht", "ferngesehet"], "可分动词：ge 放在中间"],
  ["besuchen", "besucht", ["gebesucht", "besuchet", "gebesuchen"], "不可分前缀 be-：不加 ge-"],
  ["verstehen", "verstanden", ["geverstanden", "verstandet", "verstehet"], "不可分前缀 ver-：不加 ge-"],
  ["erzählen", "erzählt", ["geerzählt", "erzahlt", "geerzählen"], "不可分前缀 er-：不加 ge-"],
  ["vergessen", "vergessen", ["gevergessen", "vergesst", "vergessent"], "不可分前缀 ver-：不加 ge-（正好和不定式一样）"],
  ["bekommen", "bekommen", ["gebekommen", "bekommt", "bekamen"], "不可分前缀 be-：不加 ge-"],
  ["studieren", "studiert", ["gestudiert", "studieret", "gestudieren"], "-ieren 结尾：不加 ge-"],
  ["telefonieren", "telefoniert", ["getelefoniert", "telefonieret", "getelefonieren"], "-ieren 结尾：不加 ge-"],
];

// 完成时句子: 两个空(助动词 … 过去分词)一起选。[句子, 动词, 答案, 选项, 解释]
const PERFEKT_SENTENCES = [
  ["Ich ___ gestern nach Berlin ___.", "fahren", "bin … gefahren",
   ["bin … gefahren", "habe … gefahren", "bin … gefahrt", "habe … gefahrt"], "fahren 表示位置移动 → sein"],
  ["Ich ___ das Auto in die Garage ___.", "fahren", "habe … gefahren",
   ["habe … gefahren", "bin … gefahren", "habe … gefahrt", "bin … gefahrt"], "fahren 后面有第四格宾语（das Auto）→ 用 haben"],
  ["Wir ___ einen Film ___.", "sehen", "haben … gesehen",
   ["haben … gesehen", "sind … gesehen", "haben … gesieht", "sind … gesieht"], "有第四格宾语，不是移动 → haben"],
  ["Er ___ heute um 6 Uhr ___.", "aufstehen", "ist … aufgestanden",
   ["ist … aufgestanden", "hat … aufgestanden", "ist … geaufstanden", "hat … aufgesteht"], "aufstehen 是状态改变（从躺着到站起来）→ sein；可分动词 ge 在中间"],
  ["Was ___ du am Wochenende ___?", "machen", "hast … gemacht",
   ["hast … gemacht", "bist … gemacht", "hast … gemachen", "bist … gemachen"], "machen 不是移动 → haben；规则动词 ge-…-t"],
  ["Das Kind ___ schnell ___.", "einschlafen", "ist … eingeschlafen",
   ["ist … eingeschlafen", "hat … eingeschlafen", "ist … eingeschlaft", "hat … geeinschlafen"], "einschlafen（睡着）是状态改变 → sein"],
  ["Ich ___ drei Jahre in München ___.", "wohnen", "habe … gewohnt",
   ["habe … gewohnt", "bin … gewohnt", "habe … gewohnen", "bin … gewohnen"], "wohnen 不是移动 → haben"],
  ["Wo ___ ihr im Urlaub ___?", "sein", "seid … gewesen",
   ["seid … gewesen", "habt … gewesen", "seid … gesein", "habt … gehabt"], "sein 的完成时也用 sein：ist gewesen"],
  ["Sie ___ zu Hause ___.", "bleiben", "ist … geblieben",
   ["ist … geblieben", "hat … geblieben", "ist … gebleibt", "hat … gebleibt"], "bleiben 虽然没有移动，完成时也用 sein（要单独记）"],
  ["Was ___ denn ___?", "passieren", "ist … passiert",
   ["ist … passiert", "hat … passiert", "ist … gepassiert", "hat … gepassiert"], "passieren 用 sein；-ieren 结尾不加 ge-"],
  ["Ich ___ meinen Freund ___.", "besuchen", "habe … besucht",
   ["habe … besucht", "bin … besucht", "habe … gebesucht", "bin … gebesucht"], "有宾语 → haben；be- 开头不加 ge-"],
  ["Er ___ Arzt ___.", "werden", "ist … geworden",
   ["ist … geworden", "hat … geworden", "ist … gewordet", "hat … gewerdet"], "werden（变成）是状态改变 → sein"],
  ["Wir ___ lange auf den Bus ___.", "warten", "haben … gewartet",
   ["haben … gewartet", "sind … gewartet", "haben … gewartt", "sind … gewarten"], "warten 不是移动 → haben；词干以 -t 结尾加 -et"],
  ["Mein Opa ___ letztes Jahr ___.", "sterben", "ist … gestorben",
   ["ist … gestorben", "hat … gestorben", "ist … gesterbt", "hat … gestirbt"], "sterben 是状态改变 → sein"],
  ["Wann ___ du nach Deutschland ___?", "kommen", "bist … gekommen",
   ["bist … gekommen", "hast … gekommen", "bist … gekommt", "hast … gekamen"], "kommen 表示位置移动 → sein"],
  ["Ich ___ dir eine E-Mail ___.", "schreiben", "habe … geschrieben",
   ["habe … geschrieben", "bin … geschrieben", "habe … geschreibt", "bin … geschreibt"], "有宾语 → haben；schreiben → geschrieben（ei → ie）"],
];

// ---------- 可分动词(第二批) ----------
// 选出正确的句子: [正确, 错误1, 错误2, 解释]
const SEP_SENTENCES = [
  ["Der Zug fährt um 8 Uhr ab.", "Der Zug abfährt um 8 Uhr.", "Der Zug fährt ab um 8 Uhr.",
   "主句：fährt 在第二位，前缀 ab 放到句末"],
  ["Ich rufe dich morgen an.", "Ich anrufe dich morgen.", "Ich rufe an dich morgen.",
   "主句：rufe 在第二位，前缀 an 放到句末"],
  ["Kannst du mich morgen anrufen?", "Kannst du mich morgen rufen an?", "Kannst du anrufen mich morgen?",
   "有情态动词时，可分动词用不定式，合在一起放句末：anrufen"],
  ["Ich weiß nicht, wann der Film anfängt.", "Ich weiß nicht, wann der Film fängt an.", "Ich weiß nicht, wann fängt der Film an.",
   "从句里动词在最后，可分动词合在一起写：anfängt"],
  ["Wir kaufen am Samstag ein.", "Wir einkaufen am Samstag.", "Wir kaufen ein am Samstag.",
   "前缀 ein 放在句子的最后"],
  ["Ich habe gestern lange ferngesehen.", "Ich habe gestern lange gefernsehen.", "Ich habe gestern lange fern gesehen.",
   "完成时：ge 放在前缀和词干中间，连写：ferngesehen"],
  ["Er versteht die Frage nicht.", "Er steht die Frage nicht ver.", "Er verstehen die Frage nicht.",
   "ver- 是不可分前缀，永远不分开"],
  ["Ich besuche morgen meine Oma.", "Ich suche morgen meine Oma be.", "Ich besuchen morgen meine Oma.",
   "be- 是不可分前缀，永远不分开"],
  ["Mach bitte das Fenster zu!", "Zumach bitte das Fenster!", "Mach zu bitte das Fenster!",
   "命令式：动词在第一位，前缀 zu 放句末"],
  ["Ich habe vergessen, das Licht auszumachen.", "Ich habe vergessen, das Licht zu ausmachen.", "Ich habe vergessen, das Licht auszu machen.",
   "zu + 不定式：zu 插在前缀和词干中间，连写：auszumachen"],
  ["Wann kommst du zurück?", "Wann zurückkommst du?", "Wann kommst zurück du?",
   "W-问句：动词 kommst 在第二位，前缀 zurück 放句末"],
];
// 可分还是不可分: [动词, 答案, 解释]
const SEP_CLASSIFY = [
  ["anrufen", "可分", "an- 是可分前缀：Ich rufe dich an."],
  ["verstehen", "不可分", "ver- 是不可分前缀：Ich verstehe das."],
  ["aufmachen", "可分", "auf- 是可分前缀：Mach die Tür auf!"],
  ["bekommen", "不可分", "be- 是不可分前缀：Ich bekomme ein Geschenk.（bekommen 是“得到”，不是 become！）"],
  ["einladen", "可分", "ein- 是可分前缀：Ich lade dich ein."],
  ["erklären", "不可分", "er- 是不可分前缀：Er erklärt die Regel."],
  ["mitnehmen", "可分", "mit- 是可分前缀：Nimm einen Schirm mit!"],
  ["verkaufen", "不可分", "ver- 是不可分前缀：Er verkauft sein Auto."],
  ["zumachen", "可分", "zu- 是可分前缀：Mach das Fenster zu!"],
  ["entschuldigen", "不可分", "ent- 是不可分前缀：Ich entschuldige mich."],
  ["zurückgeben", "可分", "zurück- 是可分前缀：Ich gebe dir das Buch zurück."],
  ["gefallen", "不可分", "ge- 是不可分前缀：Das gefällt mir."],
  ["fernsehen", "可分", "fern- 是可分前缀：Wir sehen fern."],
  ["besuchen", "不可分", "be- 是不可分前缀：Ich besuche dich."],
];

// ---------- nicht / kein(第二批) ----------
// 填空: [句子, 答案, 解释]; 选项统一是 nicht / kein / keine / keinen
const NEG_SENTENCES = [
  ["Ich habe ___ Zeit.", "keine", "die Zeit，前面没有冠词 → kein，阴性第四格 keine"],
  ["Ich komme heute ___.", "nicht", "否定动词（komme）→ nicht"],
  ["Das ist ___ gute Idee.", "keine", "否定 eine gute Idee → keine"],
  ["Er hat ___ Bruder.", "keinen", "否定 einen Bruder（阳性第四格）→ keinen"],
  ["Das Essen ist ___ gut.", "nicht", "否定形容词（gut）→ nicht"],
  ["Ich kenne den Mann ___.", "nicht", "名词带定冠词 den → 用 nicht，放在句末"],
  ["Wir haben ___ Auto.", "kein", "否定 ein Auto（中性第四格）→ kein"],
  ["Das ist ___ mein Handy.", "nicht", "名词带物主冠词 mein → 用 nicht"],
  ["Sie trinkt ___ Kaffee.", "keinen", "der Kaffee，前面没有冠词 → kein，阳性第四格 keinen"],
  ["Er wohnt ___ in Berlin.", "nicht", "否定地点（in Berlin）→ nicht"],
  ["Heute habe ich ___ Lust.", "keine", "die Lust，前面没有冠词 → keine"],
  ["Das Kind hat ___ Geschwister.", "keine", "复数，前面没有冠词 → keine"],
  ["Warum hast du mich ___ angerufen?", "nicht", "否定动词 → nicht，放在过去分词前面"],
  ["Ich habe ___ Hunger.", "keinen", "der Hunger，前面没有冠词 → keinen"],
];
// nicht 的位置: [正确, 错误1, 错误2, 解释]
const NEG_ORDER = [
  ["Ich habe das Buch nicht gelesen.", "Ich habe das Buch gelesen nicht.", "Ich nicht habe das Buch gelesen.",
   "nicht 放在句末，但要在过去分词 gelesen 前面"],
  ["Wir gehen heute nicht ins Kino.", "Wir gehen heute ins Kino nicht.", "Wir nicht gehen heute ins Kino.",
   "nicht 放在表示方向的 ins Kino 前面"],
  ["Ich kann heute nicht kommen.", "Ich kann heute kommen nicht.", "Ich nicht kann heute kommen.",
   "nicht 放在句末的不定式 kommen 前面"],
  ["Ich rufe dich morgen nicht an.", "Ich rufe dich morgen an nicht.", "Ich nicht rufe dich morgen an.",
   "nicht 放在可分前缀 an 前面"],
  ["Das Wetter ist heute nicht schön.", "Das Wetter ist heute schön nicht.", "Das Wetter nicht ist heute schön.",
   "nicht 放在形容词 schön 前面"],
  ["Er kommt heute nicht.", "Er nicht kommt heute.", "Er nicht heute kommt.",
   "否定整句，nicht 放在句末；动词永远在第二位"],
];

// ---------- 数字(第二批) ----------
const ONES = ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf",
              "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn", "neunzehn"];
const TENS = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig", "siebzig", "achtzig", "neunzig"];
function numWord(n) {   // 0–999 的德语写法(数字表和练习用)
  if (n < 20) return ONES[n];
  if (n < 100) {
    const t = Math.floor(n / 10), u = n % 10;
    return u ? (u === 1 ? "ein" : ONES[u]) + "und" + TENS[t] : TENS[t];
  }
  const h = Math.floor(n / 100), r = n % 100;
  return (h === 1 ? "hundert" : ONES[h] + "hundert") + (r ? numWord(r) : "");
}
// 容易拼错的: [数字, 正确, 错误1, 错误2, 解释]
const NUMBER_SPELLING = [
  ["16", "sechzehn", "sechszehn", "sechtzehn", "16、60 去掉 sechs 的 s：sechzehn, sechzig"],
  ["17", "siebzehn", "siebenzehn", "siebzen", "17、70 去掉 sieben 的 en：siebzehn, siebzig"],
  ["30", "dreißig", "dreizig", "dreizehn", "30 是 dreißig，用 ß（其他整十都是 -zig）"],
  ["60", "sechzig", "sechszig", "sechsig", "60 去掉 s：sechzig"],
  ["70", "siebzig", "siebenzig", "siebzehn", "70 去掉 en：siebzig"],
  ["21", "einundzwanzig", "einsundzwanzig", "zwanzigeins", "个位在前：ein + und + zwanzig（eins 变成 ein）"],
  ["345", "dreihundertfünfundvierzig", "dreihundertvierzigfünf", "dreihundertvierundfünfzig", "百位 + 个位 + und + 十位，连成一个词"],
  ["1990（年份）", "neunzehnhundertneunzig", "neunzehnneunzig", "eintausendneunzehnneunzig", "1100–1999 年读成“几十几 hundert …”：neunzehnhundert + neunzig"],
  ["2024（年份）", "zweitausendvierundzwanzig", "zwanzigvierundzwanzig", "zweitausendzwanzigvier", "2000 年以后直接读数字：zweitausend + vierundzwanzig"],
];

// ---------- 钟点和日期(第二批) ----------
// 日期和时间介词填空: [句子, 提示, 答案, 选项, 解释]
const DATE_ITEMS = [
  ["Heute ist der ___ Mai.", "（1.）", "erste", ["erste", "einste", "ersten", "eins"], "日期用序数词：1. = der erste（不规则）"],
  ["Ich habe am ___ Juli Geburtstag.", "（7.）", "siebten", ["siebten", "siebte", "siebzehnten", "siebtem"], "am + 序数词 + -en：am siebten（7. 是 siebt-，去掉 en）"],
  ["Am ___ Oktober ist ein Feiertag.", "（3.）", "dritten", ["dritten", "dreiten", "dritte", "dreißigsten"], "3. = dritt-（不规则）；am dritten"],
  ["Heute ist der ___ Dezember.", "（24.）", "vierundzwanzigste", ["vierundzwanzigste", "vierundzwanzigte", "vierundzwanzigsten", "zwanzigvierste"], "20 以上加 -ste：der vierundzwanzigste"],
  ["Wir treffen uns ___ Montag.", "", "am", ["am", "im", "um", "an"], "星期几用 am"],
  ["Ich habe ___ Juni Urlaub.", "", "im", ["im", "am", "um", "in"], "月份用 im"],
  ["Der Kurs beginnt ___ neun Uhr.", "", "um", ["um", "am", "im", "an"], "几点钟用 um"],
  ["___ Winter ist es kalt.", "", "Im", ["Im", "Am", "Um", "In"], "季节用 im"],
];

// ---------- 知识点 ----------
// tables: [{head, rows}], rows 第一列是说明, 其余是德语(点了能读)
// quiz(): 返回题目 [{prompt, options, answer, explain, wide?}]
const GRAMMAR_TOPICS = [
  {
    id: "art-def", group: "冠词", level: "A1", title: "定冠词 der / die / das",
    intro: ["定冠词相当于“这个 / 那个”，指已经知道的、特定的东西。",
            "冠词要跟着名词的性（阳 / 阴 / 中）、数（单 / 复）和格（一到四格）变。",
            "规律：阴性和复数的第一、四格一样；阳性只有第四格变成 den；第三格复数名词本身也要加 -n。"],
    tables: [{ head: GENDER_HEAD, rows: DEF_ARTICLES.map((r, c) => [CASE_NAMES[c], ...r]) }],
    examples: ["Der Mann trinkt Kaffee.", "Ich sehe den Mann.", "Ich helfe dem Mann.", "Das ist das Auto des Mannes."],
    quiz: () => articleQuiz((c, g) => DEF_ARTICLES[c][g], QUIZ_NOUNS, [0, 1, 2, 3], ["m", "f", "n", "pl"]),
  },
  {
    id: "art-indef", group: "冠词", level: "A1", title: "不定冠词 ein / eine",
    intro: ["不定冠词相当于“一个”，指第一次提到的、不特定的东西。",
            "复数没有不定冠词：ein Kind → Kinder（前面什么都不加）。",
            "注意阳性第一格 ein 和中性第一、四格 ein 都没有词尾，这是它和定冠词最不一样的地方。"],
    tables: [{ head: GENDER_HEAD, rows: [
      [CASE_NAMES[0], "ein", "eine", "ein", "—"],
      [CASE_NAMES[1], "einen", "eine", "ein", "—"],
      [CASE_NAMES[2], "einem", "einer", "einem", "—"],
      [CASE_NAMES[3], "eines", "einer", "eines", "—"],
    ] }],
    examples: ["Das ist ein Hund.", "Ich habe einen Bruder.", "Er wohnt in einer Wohnung.", "Ich sehe Kinder."],
    quiz: () => articleQuiz((c, g) => "ein" + KEIN_ENDINGS[c][g], QUIZ_NOUNS, [0, 1, 2, 3], ["m", "f", "n"]),
  },
  {
    id: "art-kein", group: "冠词", level: "A1", title: "否定冠词 kein",
    intro: ["kein 用来否定名词，相当于“没有 / 不是一个”：Ich habe kein Auto.（我没有车）",
            "单数的词尾和 ein 完全一样，只是前面多了 k；而且 kein 有复数：keine Kinder。",
            "否定带不定冠词或不带冠词的名词用 kein；否定动词、形容词等用 nicht。"],
    tables: [{ head: GENDER_HEAD, rows: KEIN_ENDINGS.map((r, c) => [CASE_NAMES[c], ...r.map(e => "kein" + e)]) }],
    examples: ["Ich habe keinen Hunger.", "Das ist keine gute Idee.", "Wir haben keine Kinder.", "Er hat kein Geld."],
    quiz: () => articleQuiz((c, g) => "kein" + KEIN_ENDINGS[c][g], QUIZ_NOUNS, [0, 1, 2], ["m", "f", "n", "pl"]),
  },
  {
    id: "art-poss", group: "冠词", level: "A1–A2", title: "物主冠词 mein / dein / sein …",
    intro: ["物主冠词表示“谁的”。先按“人”选词干（我的 → mein，他们的 → ihr），再按后面名词的性、数、格加词尾。",
            "词尾和 kein 完全一样：mein Vater, meine Mutter, meinen Vater, meinem Kind …",
            "euer 加词尾时去掉中间的 e：eure, euren, eurem；ihr 既可以是“她的”也可以是“他们的”，大写 Ihr 是“您的”。"],
    tables: [
      { title: "第一步：按“人”选词干", head: ["人", "物主冠词词干"], rows: POSSESSIVES.map(([p, s]) => [p, s]) },
      { title: "第二步：按名词加词尾（以 mein 为例）", head: GENDER_HEAD,
        rows: KEIN_ENDINGS.map((r, c) => [CASE_NAMES[c], ...r.map(e => possForm("mein", e))]) },
    ],
    examples: ["Das ist mein Bruder.", "Ich besuche meine Eltern.", "Hast du deinen Schlüssel?", "Wir wohnen bei unserer Tante."],
    quiz: () => {
      const qs = [];
      for (const [person, stem] of POSSESSIVES) {
        const c = rand([0, 1, 2, 3]), g = rand(["m", "f", "n", "pl"]);
        const gi = ["m", "f", "n", "pl"].indexOf(g);
        const answer = possForm(stem, KEIN_ENDINGS[c][gi]);
        const options = [...new Set(KEIN_ENDINGS.flat().map(e => possForm(stem, e)))];
        qs.push({
          prompt: fillFrame(c, g, POSS_NOUNS), hint: `${person} 的 → ${stem} · ${CASE_NAMES[c]}`,
          options, answer, explain: `${stem} + ${CASE_NAMES[c]}${["阳性", "阴性", "中性", "复数"][gi]}词尾 -${KEIN_ENDINGS[c][gi] || "（无）"} → ${answer}`,
        });
      }
      return qs;
    },
  },
  {
    id: "pron", group: "代词", level: "A1–A2", title: "人称代词四格",
    intro: ["人称代词代替名词，也要变格：我 = ich（主语）/ mich（宾语，第四格）/ mir（第三格）。",
            "哪个格由动词或介词决定：sehen, haben, lieben + 第四格；helfen, danken, gefallen, gehören + 第三格；mit / bei / zu + 第三格。",
            "第二格（meiner, deiner …）现代德语很少用，先不用记。"],
    // 每个人称一行(9 行 × 4 列), 手机上不用左右滑
    tables: [{ head: ["人称", "第一格", "第四格", "第三格"], rows: PRONOUNS.nom.map((_, i) =>
      [PRONOUNS.head[i + 1], PRONOUNS.nom[i], PRONOUNS.akk[i], PRONOUNS.dat[i]]) }],
    examples: ["Ich liebe dich.", "Kannst du mir helfen?", "Das Buch gefällt ihm.", "Ich rufe Sie morgen an."],
    quiz: () => {
      const qs = [];
      PRONOUNS.nom.forEach((_, i) => {
        const who = PRONOUNS.head[i + 1];
        for (const [frame, col, cname, why] of [
          ["Er sieht ___.", PRONOUNS.akk, "第四格", "sehen + 第四格"],
          ["Er hilft ___.", PRONOUNS.dat, "第三格", "helfen + 第三格"],
        ]) {
          qs.push({ prompt: frame, hint: `（${who}）`, options: [...new Set(col)], answer: col[i],
                    explain: `${why}：${who} → ${col[i]}` });
        }
      });
      return shuffle(qs).slice(0, 12);
    },
  },
  {
    id: "prep-akk", group: "介词", level: "A1", title: "支配第四格的介词",
    intro: ["这些介词后面的名词永远用第四格：durch（穿过）、für（为了）、gegen（反对 / 撞向）、ohne（没有）、um（围绕 / 在…点钟）。",
            "记法：首字母 D-O-G-F-U（durch, ohne, gegen, für, um）。",
            "第四格只有阳性会变（der → den, ein → einen），阴性、中性、复数和第一格一样。"],
    tables: [{ head: ["介词", "意思", "例子"], rows: [
      ["durch", "穿过、通过", "durch den Park"],
      ["für", "为了、给", "für meinen Vater"],
      ["gegen", "反对、撞向、大约", "gegen den Baum"],
      ["ohne", "没有", "ohne die Brille"],
      ["um", "围绕、（几点）", "um den Tisch / um 8 Uhr"],
    ] }],
    examples: ["Das Geschenk ist für dich.", "Wir gehen durch den Park.", "Ich trinke Kaffee ohne Zucker."],
    quiz: () => prepQuiz(PREP_AKK_SENTENCES),
  },
  {
    id: "prep-dat", group: "介词", level: "A1", title: "支配第三格的介词",
    intro: ["这些介词后面的名词永远用第三格：aus, bei, mit, nach, seit, von, zu（还有 gegenüber）。",
            "第三格：der → dem，die → der，das → dem，复数 die → den（而且复数名词加 -n：den Kindern）。",
            "常见缩写：zu dem → zum，zu der → zur，bei dem → beim，von dem → vom。"],
    tables: [{ head: ["介词", "意思", "例子"], rows: [
      ["aus", "从…里出来、来自", "aus der Schweiz"],
      ["bei", "在…那里、在…时候", "bei meinen Eltern"],
      ["mit", "和、乘坐", "mit dem Bus"],
      ["nach", "在…之后、去（城市 / 国家）", "nach dem Essen"],
      ["seit", "自从", "seit einem Jahr"],
      ["von", "从、…的", "von der Arbeit"],
      ["zu", "去（某人 / 某处）", "zum Arzt / zur Schule"],
    ] }],
    examples: ["Ich fahre mit dem Bus.", "Er kommt aus der Türkei.", "Ich gehe zum Arzt.", "Seit einem Jahr lerne ich Deutsch."],
    quiz: () => prepQuiz(PREP_DAT_SENTENCES),
  },
  {
    id: "prep-wechsel", group: "介词", level: "A2", title: "双向介词（第三格还是第四格）",
    intro: ["an, auf, hinter, in, neben, über, unter, vor, zwischen 这 9 个介词，有时用第三格，有时用第四格。",
            "问 Wo?（在哪里，位置不变）→ 第三格；问 Wohin?（到哪里去，有方向、位置改变）→ 第四格。",
            "常和成对的动词一起出现：liegen / legen，stehen / stellen，sitzen / setzen，hängen（在挂着 / 挂上去）。"],
    tables: [
      { title: "9 个双向介词", head: ["介词", "意思"], rows: [
        ["an", "在…旁边（贴着）"], ["auf", "在…上面（接触）"], ["hinter", "在…后面"],
        ["in", "在…里面"], ["neben", "在…旁边"], ["über", "在…上方（不接触）"],
        ["unter", "在…下面"], ["vor", "在…前面"], ["zwischen", "在…之间"],
      ] },
      { title: "Wo? 还是 Wohin?", head: ["问", "例子"], rows: [
        ["Wo? → 第三格", "Ich bin im Haus."],
        ["Wohin? → 第四格", "Ich gehe ins Haus."],
        ["Wo? → 第三格", "Das Buch liegt auf dem Tisch."],
        ["Wohin? → 第四格", "Ich lege das Buch auf den Tisch."],
      ] },
      { title: "常见缩写", head: ["缩写", "等于"], rows: [
        ["im", "in dem"], ["ins", "in das"], ["am", "an dem"], ["ans", "an das"],
      ] },
    ],
    examples: ["Die Katze schläft unter dem Bett.", "Die Katze läuft unter das Bett.", "Wir sind im Kino.", "Wir gehen ins Kino."],
    quiz: () => prepQuiz(PREP_TWOWAY_SENTENCES),
  },
  {
    id: "verb-sein", group: "动词", level: "A1", title: "sein / haben / werden",
    intro: ["这三个是最常用、也最不规则的动词，必须背熟。",
            "sein（是）、haben（有）还用来构成完成时：Ich bin gefahren / Ich habe gegessen。",
            "werden（变成）还用来构成将来时和被动态：Ich werde kommen。"],
    tables: [{ head: ["", "sein", "haben", "werden"], rows: PERSONS6.map((p, i) => [p, VERBS.sein[i], VERBS.haben[i], VERBS.werden[i]]) }],
    examples: ["Ich bin müde.", "Hast du Zeit?", "Er wird Arzt.", "Wir sind Studenten."],
    quiz: () => verbQuiz(["sein", "haben", "werden"], 12),
  },
  {
    id: "verb-modal", group: "动词", level: "A1", title: "情态动词",
    intro: ["können（能、会）、müssen（必须）、dürfen（允许）、sollen（应该）、wollen（想要）、mögen（喜欢）、möchten（想要，礼貌）。",
            "规律：ich 和 er / sie / es 的形式一样，而且没有词尾 -t（ich kann, er kann）；单数大多换元音（können → kann）。",
            "情态动词在第二位，另一个动词用不定式放在句末：Ich kann heute nicht kommen."],
    tables: [
      { head: ["", "können", "müssen", "dürfen", "sollen"], rows: PERSONS6.map((p, i) => [p, ...["können", "müssen", "dürfen", "sollen"].map(v => VERBS[v][i])]) },
      { head: ["", "wollen", "mögen", "möchten"], rows: PERSONS6.map((p, i) => [p, ...["wollen", "mögen", "möchten"].map(v => VERBS[v][i])]) },
    ],
    examples: ["Ich kann gut schwimmen.", "Du musst jetzt gehen.", "Darf ich hier rauchen?", "Ich möchte einen Kaffee."],
    quiz: () => verbQuiz(["können", "müssen", "dürfen", "sollen", "wollen", "mögen", "möchten"], 14),
  },
  {
    id: "order-main", group: "语序", level: "A1", title: "主句语序：动词在第二位",
    intro: ["陈述句里，变位动词永远在第二位。第一位可以是主语，也可以是时间、地点等；主语不在第一位时就放到动词后面。",
            "框架结构：有情态动词、助动词时，它们在第二位，另一个动词（不定式 / 过去分词）放到句末；可分动词的前缀也放句末。",
            "问句：W-问句 疑问词 + 动词 + 主语；是非问句 动词放第一位。"],
    tables: [{ head: ["第一位", "第二位（动词）", "其他", "句末"], rows: [
      ["Ich", "lerne", "heute Deutsch.", ""],
      ["Heute", "lerne", "ich Deutsch.", ""],
      ["Ich", "kann", "heute nicht", "kommen."],
      ["Ich", "habe", "gestern Deutsch", "gelernt."],
      ["Ich", "stehe", "um 7 Uhr", "auf."],
    ] }],
    examples: ["Heute lerne ich Deutsch.", "Ich kann heute nicht kommen.", "Wann kommst du nach Hause?"],
    quiz: () => orderQuiz(ORDER_MAIN),
  },
  {
    id: "order-sub", group: "语序", level: "A2", title: "从句语序：动词在最后",
    intro: ["weil（因为）、dass（…这件事）、wenn（如果 / 每当）、ob（是否）、als（当…时，过去）等引导的从句里，变位动词放在最后。",
            "从句放在前面时，整个从句算“第一位”，主句的动词要紧跟在逗号后面：Weil ich müde bin, gehe ich nach Hause.",
            "und, aber, oder, denn, sondern 不算从句连词，后面还是正常语序。"],
    tables: [{ head: ["连词", "例句（变位动词在最后）"], rows: [
      ["weil 因为", "Ich bleibe zu Hause, weil ich krank bin."],
      ["dass", "Ich weiß, dass er morgen kommt."],
      ["dass + 情态动词", "Er sagt, dass er nicht kommen kann."],
      ["wenn + 可分动词", "Ich rufe dich an, wenn ich ankomme."],
      ["从句放在前面", "Weil ich müde bin, gehe ich nach Hause."],
    ] }],
    examples: ["Ich bleibe zu Hause, weil ich krank bin.", "Weil ich müde bin, gehe ich nach Hause.", "Ich weiß nicht, ob er heute kommt."],
    quiz: () => orderQuiz(ORDER_SUB),
  },
  {
    id: "adj-weak", group: "形容词词尾", level: "A2", title: "形容词词尾①：定冠词后（弱变化）",
    intro: ["形容词放在名词前面时要加词尾；放在 sein 等动词后面不加：Der Mann ist alt.",
            "前面是 der / die / das（还有 dieser、jeder、welcher、alle）时，冠词已经表明了性和格，形容词只需要 -e 或 -en。",
            "只有 5 个位置是 -e：三个单数第一格 + 阴性、中性第四格；其余全部是 -en。"],
    tables: [
      { title: "词尾", head: GENDER_HEAD, rows: endingRows(WEAK_END) },
      { title: "完整例子", head: GENDER_HEAD, rows: DEF_ARTICLES.map((r, c) => [CASE_NAMES[c],
          ...["m", "f", "n", "pl"].map((g, gi) => `${r[gi]} nett${WEAK_END[c][gi]} ${QUIZ_NOUNS[g][c]}`)]) },
    ],
    examples: ["Der alte Mann wohnt hier.", "Ich kenne die junge Frau.", "Wir helfen dem kleinen Kind.", "Die neuen Schuhe sind schön."],
    quiz: () => adjQuiz("weak", 10),
  },
  {
    id: "adj-mixed", group: "形容词词尾", level: "A2", title: "形容词词尾②：ein / kein / mein 后（混合变化）",
    intro: ["前面是 ein、kein 或物主冠词（mein、dein、unser …）时用这一套。",
            "和弱变化几乎一样，只有三个位置不同：阳性第一格 -er（ein alter Mann），中性第一、四格 -es（ein altes Kind）。因为这三个位置 ein 没有词尾，要由形容词来表明性别。",
            "复数：kein / mein 后面是 -en（meine alten Freunde）；ein 没有复数，复数不带冠词时用强变化（alte Freunde）。"],
    tables: [
      { title: "词尾", head: GENDER_HEAD, rows: endingRows(MIXED_END) },
      { title: "完整例子", head: GENDER_HEAD, rows: [0, 1, 2, 3].map(c => [CASE_NAMES[c],
          ...["m", "f", "n", "pl"].map((g, gi) => `${mixedArticle(c, gi)} nett${MIXED_END[c][gi]} ${QUIZ_NOUNS[g][c]}`)]) },
    ],
    examples: ["Das ist ein alter Freund.", "Ich habe einen kleinen Hund.", "Sie wohnt in einer schönen Wohnung.", "Das ist kein gutes Zeichen."],
    quiz: () => adjQuiz("mixed", 10),
  },
  {
    id: "adj-strong", group: "形容词词尾", level: "B1", title: "形容词词尾③：没有冠词（强变化）",
    intro: ["前面没有冠词时（常见于吃的喝的、复数和固定说法：Guten Appetit! Mit freundlichen Grüßen），形容词自己要表明性和格。",
            "词尾基本就是定冠词的最后一个字母：der → -er，die → -e，das → -es，dem → -em，den → -en。",
            "例外：阳性、中性第二格是 -en（不是 -es），因为名词自己已经加了 -(e)s：trotz schlechten Wetters。"],
    tables: [
      { title: "词尾", head: GENDER_HEAD, rows: endingRows(STRONG_END) },
      { title: "完整例子", head: GENDER_HEAD, rows: [
        [CASE_NAMES[0], "guter Wein", "frische Milch", "kaltes Bier", "frische Äpfel"],
        [CASE_NAMES[1], "guten Wein", "frische Milch", "kaltes Bier", "frische Äpfel"],
        [CASE_NAMES[2], "gutem Wein", "frischer Milch", "kaltem Bier", "frischen Äpfeln"],
        [CASE_NAMES[3], "guten Weins", "frischer Milch", "kalten Biers", "frischer Äpfel"],
      ] },
    ],
    examples: ["Guten Morgen!", "Ich trinke gern kalte Milch.", "Mit freundlichen Grüßen", "Sie hat lange Haare."],
    quiz: () => adjQuiz("strong", 10),
  },
  {
    id: "adj-mix", group: "形容词词尾", level: "B1", title: "形容词词尾④：怎么判断（综合）",
    intro: ["第一步：名词前面有没有冠词？没有 → 强变化（形容词词尾像定冠词：-er / -e / -es / -em …）。",
            "第二步：是 der / die / das 这一类 → 弱变化（只有 -e 和 -en）。",
            "第三步：是 ein / kein / mein 这一类 → 混合变化：阳性第一格 -er，中性第一、四格 -es，其余和弱变化一样。",
            "小窍门：只要前面有冠词，第三格和复数一律是 -en。有些形容词加词尾时会变形：hoch → hohe，dunkel → dunkle，teuer → teure。"],
    tables: [{ head: ["", "定冠词后", "ein / mein 后", "没有冠词"], rows: [
      ["阳性 第一格", "der gute Wein", "ein guter Wein", "guter Wein"],
      ["中性 第一格", "das kalte Bier", "ein kaltes Bier", "kaltes Bier"],
      ["阴性 第一格", "die frische Milch", "eine frische Milch", "frische Milch"],
      ["阳性 第四格", "den guten Wein", "einen guten Wein", "guten Wein"],
      ["阳性 第三格", "dem guten Wein", "einem guten Wein", "gutem Wein"],
      ["复数 第一格", "die frischen Äpfel", "meine frischen Äpfel", "frische Äpfel"],
    ] }],
    examples: ["Der neue Lehrer ist nett.", "Ein neuer Lehrer kommt morgen.", "Neue Lehrer sind oft nervös."],
    quiz: () => shuffle([...adjQuiz("weak", 4), ...adjQuiz("mixed", 4), ...adjQuiz("strong", 4)]),
  },
  {
    id: "comp-form", group: "比较级", level: "A2", title: "比较级和最高级的构成",
    intro: ["比较级：原级 + -er（schnell → schneller）；最高级：am + 原级 + -sten（am schnellsten）。德语不用 mehr / am meisten 来构成，长的词也一样：interessanter。",
            "很多单音节形容词要变音：alt → älter，jung → jünger，groß → größer（但 au 不变：laut → lauter）。",
            "以 -d、-t、-s、-ß、-z、-sch 结尾的，最高级加 -esten：am ältesten，am kürzesten，am heißesten（例外：am größten）。",
            "以 -el、-er 结尾的，比较级去掉 e：dunkel → dunkler，teuer → teurer。几个最常用的词是不规则的，要单独记。"],
    tables: [
      { title: "规则变化", head: ["规则", "原级", "比较级", "最高级"], rows: [
        ["一般：-er / am -sten", "schnell", "schneller", "am schnellsten"],
        ["单音节常变音", "alt", "älter", "am ältesten"],
        ["-t / -z / -ß 结尾：-esten", "kurz", "kürzer", "am kürzesten"],
        ["-el 结尾：比较级去 e", "dunkel", "dunkler", "am dunkelsten"],
        ["-er 结尾：比较级去 e", "teuer", "teurer", "am teuersten"],
      ] },
      { title: "不规则变化（要单独记）", head: ["意思", "原级", "比较级", "最高级"], rows: [
        ["好", "gut", "besser", "am besten"],
        ["多", "viel", "mehr", "am meisten"],
        ["喜欢", "gern", "lieber", "am liebsten"],
        ["高", "hoch", "höher", "am höchsten"],
        ["近", "nah", "näher", "am nächsten"],
        ["大", "groß", "größer", "am größten"],
      ] },
    ],
    examples: ["Mein Bruder ist älter als ich.", "Ich trinke lieber Tee.", "Im Winter ist es am kältesten.", "Das ist am besten."],
    quiz: () => compFormQuiz(12),
  },
  {
    id: "comp-sentence", group: "比较级", level: "A2–B1", title: "比较句：als / wie / am …sten",
    intro: ["“一样…”用 so + 原级 + wie；“比…更…”用 比较级 + als。口语里常听到 größer wie，但书面语算错。",
            "最高级有两种用法：单独用（在 sein 后面、修饰动词）→ am …sten：Er läuft am schnellsten。放在名词前面 → der / die / das …ste + 名词，要加形容词词尾：der schnellste Läufer。",
            "比较级放在名词前面也要加形容词词尾：ein teureres Auto，mit einem schnelleren Zug。",
            "越来越…：immer + 比较级；越…越…：je + 比较级 …, desto + 比较级 …（je 引导的部分动词在最后）。"],
    tables: [{ head: ["用法", "例子", "意思"], rows: [
      ["so + 原级 + wie", "Er ist so groß wie ich.", "他和我一样高"],
      ["nicht so + 原级 + wie", "Er ist nicht so groß wie ich.", "他没有我高"],
      ["比较级 + als", "Er ist größer als ich.", "他比我高"],
      ["am + -sten", "Er ist am größten.", "他最高"],
      ["der / die / das + -ste + 名词", "Er ist der größte Schüler.", "他是最高的学生"],
      ["immer + 比较级", "Es wird immer kälter.", "天越来越冷"],
      ["je …, desto …", "Je mehr ich lerne, desto besser spreche ich.", "我学得越多，说得越好"],
    ] }],
    examples: ["Berlin ist größer als München.", "Ich bin so alt wie du.", "Das ist der beste Kaffee der Stadt.", "Es wird immer besser."],
    quiz: () => shuffle(COMPARE_SENTENCES).map(([prompt, answer, options, explain]) => ({ prompt, answer, options, explain })),
  },
  {
    id: "perf-part", group: "完成时", level: "A1–A2", title: "完成时①：过去分词怎么构成",
    intro: ["完成时 = haben / sein 的变位（第二位）+ 过去分词（句末）：Ich habe Deutsch gelernt。说过去的事，口语里基本都用完成时。",
            "规则动词：ge- + 词干 + -t（machen → gemacht）；词干以 -t / -d 结尾加 -et（arbeiten → gearbeitet）。",
            "不规则动词：ge- + 词干 + -en，词干常换元音（schreiben → geschrieben，trinken → getrunken），只能背；还有少数“混合”的：换元音但词尾是 -t（bringen → gebracht）。",
            "可分动词 ge 放在中间（aufstehen → aufgestanden）；不可分前缀 be- / ver- / er- / ent- / emp- / zer- 和 -ieren 结尾的动词不加 ge-（besuchen → besucht，studieren → studiert）。"],
    tables: [
      { title: "过去分词的几种类型", head: ["类型", "不定式", "过去分词"], rows: [
        ["规则：ge-…-t", "machen", "gemacht"],
        ["词干 -t / -d：ge-…-et", "arbeiten", "gearbeitet"],
        ["不规则：ge-…-en", "fahren", "gefahren"],
        ["不规则 + 换元音", "trinken", "getrunken"],
        ["混合：换元音 + -t", "bringen", "gebracht"],
        ["可分动词：ge 在中间", "aufstehen", "aufgestanden"],
        ["不可分前缀：不加 ge-", "besuchen", "besucht"],
        ["-ieren：不加 ge-", "studieren", "studiert"],
      ] },
      { title: "最常用的动词", head: ["意思", "不定式", "过去分词", "助动词"], rows: [
        ["是", "sein", "gewesen", "ist"], ["有", "haben", "gehabt", "hat"], ["变成", "werden", "geworden", "ist"],
        ["去", "gehen", "gegangen", "ist"], ["来", "kommen", "gekommen", "ist"], ["吃", "essen", "gegessen", "hat"],
        ["喝", "trinken", "getrunken", "hat"], ["看", "sehen", "gesehen", "hat"], ["说", "sprechen", "gesprochen", "hat"],
        ["拿", "nehmen", "genommen", "hat"], ["找到", "finden", "gefunden", "hat"], ["睡", "schlafen", "geschlafen", "hat"],
      ] },
    ],
    examples: ["Ich habe Deutsch gelernt.", "Wir haben lange gearbeitet.", "Hast du das Buch gelesen?", "Er hat mich gestern angerufen."],
    quiz: () => shuffle(PARTICIPLES).slice(0, 12).map(([inf, part, wrong, rule]) => ({
      prompt: `${inf} → ___`, hint: "过去分词", answer: part, options: [part, ...wrong], explain: `${inf} → ${part}（${rule}）`,
    })),
  },
  {
    id: "perf-aux", group: "完成时", level: "A2", title: "完成时②：用 haben 还是 sein",
    intro: ["大多数动词用 haben：所有带第四格宾语的、反身动词、情态动词，以及大部分其他动词。",
            "用 sein 的：① 位置移动（gehen, fahren, kommen, fliegen, laufen）；② 状态改变（aufstehen, einschlafen, aufwachen, sterben, werden）；③ 单独记：sein, bleiben, passieren。",
            "注意：移动动词带了第四格宾语就用 haben：Ich bin nach Hause gefahren，但 Ich habe das Auto in die Garage gefahren。",
            "南德、奥地利、瑞士常说 Ich bin gesessen / gestanden / gelegen，标准德语（北部）用 habe。考试按标准德语。"],
    tables: [
      { title: "什么时候用 sein / haben", head: ["", "例子"], rows: [
        ["sein：位置移动", "Ich bin nach Hause gegangen."],
        ["sein：状态改变", "Er ist früh eingeschlafen."],
        ["sein：单独记", "Ich bin zu Hause geblieben."],
        ["haben：有宾语", "Ich habe einen Kaffee getrunken."],
        ["haben：大多数动词", "Wir haben viel gelacht."],
      ] },
      { title: "句子结构：haben / sein 第二位，过去分词放句末", head: ["例句", "助动词 … 过去分词"], rows: [
        ["Ich habe gestern Deutsch gelernt.", "habe … gelernt"],
        ["Gestern bin ich ins Kino gegangen.", "bin … gegangen"],
        ["Wann bist du aufgestanden?", "bist … aufgestanden"],
      ] },
    ],
    examples: ["Ich bin gestern nach Berlin gefahren.", "Wir haben einen Film gesehen.", "Was ist passiert?", "Ich bin zu Hause geblieben."],
    quiz: () => shuffle(PERFEKT_SENTENCES).slice(0, 12).map(([prompt, verb, answer, options, explain]) => ({
      prompt, hint: `（${verb}）`, answer, options, explain,
    })),
  },
  {
    id: "sep-verbs", group: "可分动词", level: "A1–A2", title: "可分动词和不可分动词",
    intro: ["可分前缀（重读）：ab-, an-, auf-, aus-, ein-, mit-, nach-, vor-, weg-, zu-, zurück-, fern- …；不可分前缀（不重读）：be-, emp-, ent-, er-, ge-, miss-, ver-, zer-。",
            "主句和问句里，可分前缀和动词分开，前缀放到句末：Ich stehe um 7 Uhr auf。",
            "动词放在句末时就合在一起写：情态动词句 Ich muss früh aufstehen；从句 …, weil ich früh aufstehe。",
            "完成时 ge 在中间（aufgestanden），zu + 不定式 zu 也在中间（aufzustehen）。über-, unter-, um-, durch-, wieder- 有时可分有时不可分，以后再学。"],
    tables: [
      { title: "可分前缀（会分开）", head: ["前缀", "动词", "例子"], rows: [
        ["ab-", "abfahren", "Der Zug fährt um 8 Uhr ab."],
        ["an-", "anrufen", "Ich rufe dich morgen an."],
        ["auf-", "aufstehen", "Ich stehe um 7 Uhr auf."],
        ["ein-", "einkaufen", "Wir kaufen am Samstag ein."],
        ["mit-", "mitkommen", "Kommst du mit?"],
        ["zu-", "zumachen", "Mach bitte die Tür zu!"],
        ["zurück-", "zurückkommen", "Wann kommst du zurück?"],
        ["fern-", "fernsehen", "Wir sehen am Abend fern."],
      ] },
      { title: "不可分前缀（永远不分开）", head: ["前缀", "动词", "例子"], rows: [
        ["be-", "besuchen", "Ich besuche meine Oma."],
        ["er-", "erklären", "Kannst du das erklären?"],
        ["ver-", "verstehen", "Ich verstehe das nicht."],
        ["ent-", "entschuldigen", "Entschuldigen Sie bitte!"],
        ["emp-", "empfehlen", "Ich empfehle dir das Buch."],
        ["ge-", "gefallen", "Das gefällt mir."],
      ] },
      { title: "前缀放在哪（以 aufstehen 为例）", head: ["句型", "例子"], rows: [
        ["主句", "Ich stehe um 7 Uhr auf."],
        ["情态动词", "Ich muss um 7 Uhr aufstehen."],
        ["从句", "Ich bin müde, weil ich um 5 Uhr aufstehe."],
        ["完成时", "Ich bin um 7 Uhr aufgestanden."],
        ["zu + 不定式", "Es ist schwer, früh aufzustehen."],
        ["命令式", "Steh endlich auf!"],
      ] },
    ],
    examples: ["Ich rufe dich morgen an.", "Kommst du mit?", "Ich muss heute einkaufen.", "Er hat mich nicht verstanden."],
    quiz: () => shuffle([
      ...orderQuiz(SEP_SENTENCES).slice(0, 8),
      ...shuffle(SEP_CLASSIFY).slice(0, 4).map(([verb, answer, explain]) =>
        ({ prompt: verb, hint: "可分还是不可分？", answer, options: ["可分", "不可分"], explain, wide: false, plain: true })),
    ]),
  },
  {
    id: "neg", group: "否定", level: "A1", title: "nicht 还是 kein",
    intro: ["kein 否定名词：带不定冠词 ein 的名词（ein Auto → kein Auto）和不带冠词的名词（Zeit → keine Zeit，复数 Kinder → keine Kinder）。kein 的变化见“否定冠词 kein”。",
            "nicht 否定其他的一切：动词、形容词、副词，还有带定冠词或物主冠词的名词（den Mann → den Mann nicht，mein Handy → nicht mein Handy）。",
            "nicht 的位置：否定整句时放在句末，但要放在句末那些“第二部分”前面：过去分词、不定式、可分前缀、形容词、方向和地点。",
            "回答否定的问题，想说“不，是的”要用 doch：Hast du keine Zeit? — Doch, ich habe Zeit!"],
    tables: [
      { title: "什么时候用 kein", head: ["名词前面是", "例子"], rows: [
        ["ein + 名词", "Ich habe kein Auto."],
        ["没有冠词的名词", "Ich habe keine Zeit."],
        ["复数（没有冠词）", "Wir haben keine Kinder."],
      ] },
      { title: "什么时候用 nicht", head: ["否定的是", "例子"], rows: [
        ["动词", "Ich komme nicht."],
        ["形容词 / 副词", "Das ist nicht gut."],
        ["带定冠词的名词", "Ich kenne den Mann nicht."],
        ["带物主冠词的名词", "Das ist nicht mein Handy."],
        ["地点 / 方向", "Er wohnt nicht in Berlin."],
      ] },
      { title: "nicht 放在哪", head: ["放在…前面", "例子"], rows: [
        ["（句末）", "Ich verstehe dich nicht."],
        ["过去分词", "Ich habe das nicht gemacht."],
        ["不定式", "Ich kann heute nicht kommen."],
        ["可分前缀", "Ich rufe dich nicht an."],
        ["形容词", "Er ist nicht krank."],
        ["方向 / 地点", "Ich gehe heute nicht ins Kino."],
      ] },
    ],
    examples: ["Ich habe keine Zeit.", "Ich habe das nicht gewusst.", "Das ist nicht mein Problem.", "Hast du keinen Hunger? — Doch!"],
    quiz: () => shuffle([
      ...shuffle(NEG_SENTENCES).slice(0, 9).map(([prompt, answer, explain]) =>
        ({ prompt, answer, options: ["nicht", "kein", "keine", "keinen"], explain })),
      ...orderQuiz(NEG_ORDER).slice(0, 3),
    ]),
  },
  {
    id: "numbers", group: "数字和时间", level: "A1", title: "数字",
    intro: ["0–12 要背；13–19 是 个位 + zehn（sechzehn、siebzehn 要去掉 s / en）；整十是 -zig，只有 30 是 dreißig。",
            "21–99 是倒着说的：个位 + und + 十位（einundzwanzig，eins 变成 ein）。听的时候先听到个位，最容易把 25 写成 52。",
            "大的数字连成一个词：345 = dreihundertfünfundvierzig；1.000 = tausend，1.000.000 = eine Million。",
            "年份：1100–1999 读成 neunzehnhundertneunzig（1990），2000 年以后是 zweitausendvierundzwanzig（2024）。"],
    tables: [
      { title: "0–19", head: ["数字", "德语", "数字", "德语"], rows: Array.from({ length: 10 }, (_, i) =>
        [String(i), numWord(i), String(i + 10), numWord(i + 10)]) },
      { title: "整十和更大的数", head: ["数字", "德语", "数字", "德语"], rows: [
        ["20", "zwanzig", "70", "siebzig"], ["30", "dreißig", "80", "achtzig"], ["40", "vierzig", "90", "neunzig"],
        ["50", "fünfzig", "100", "hundert"], ["60", "sechzig", "1000", "tausend"],
      ] },
      { title: "组合起来", head: ["数字", "德语"], rows: [
        ["21", "einundzwanzig"], ["32", "zweiunddreißig"], ["47", "siebenundvierzig"], ["99", "neunundneunzig"],
        ["101", "hunderteins"], ["345", "dreihundertfünfundvierzig"],
        ["1990（年份）", "neunzehnhundertneunzig"], ["2024（年份）", "zweitausendvierundzwanzig"],
      ] },
    ],
    examples: ["Ich bin dreiundzwanzig Jahre alt.", "Das kostet neunzehn Euro neunundneunzig.", "Meine Telefonnummer ist null eins fünf neun …", "Ich bin neunzehnhundertneunundneunzig geboren."],
    quiz: () => numberQuiz(),
  },
  {
    id: "time", group: "数字和时间", level: "A1", title: "钟点和日期",
    intro: ["问时间：Wie spät ist es? / Wie viel Uhr ist es? 正式说法（广播、车站）用 24 小时：15:30 = fünfzehn Uhr dreißig。",
            "口语用 12 小时：Viertel nach（过一刻）、Viertel vor（差一刻）、halb（半）。注意 halb 是“到下一个钟点还差半小时”：halb vier = 3:30，不是 4:30！",
            "几点钟用 um，星期 / 日期 / 一天中的时段用 am，月份 / 季节用 im：um drei Uhr, am Montag, am Abend, im Mai, im Sommer。",
            "日期用序数词：1.–19. 加 -te（erste, zweite, dritte, siebte 不规则），20. 以上加 -ste；“在几号”是 am + 序数词 + -en：am dritten Oktober。"],
    tables: [
      { title: "几点了", head: ["钟表", "口语（12 小时）", "正式（下午 24 小时）"], rows: [
        ["3:00", "drei Uhr", "fünfzehn Uhr"],
        ["3:05", "fünf nach drei", "fünfzehn Uhr fünf"],
        ["3:15", "Viertel nach drei", "fünfzehn Uhr fünfzehn"],
        ["3:25", "fünf vor halb vier", "fünfzehn Uhr fünfundzwanzig"],
        ["3:30", "halb vier", "fünfzehn Uhr dreißig"],
        ["3:35", "fünf nach halb vier", "fünfzehn Uhr fünfunddreißig"],
        ["3:45", "Viertel vor vier", "fünfzehn Uhr fünfundvierzig"],
        ["3:55", "fünf vor vier", "fünfzehn Uhr fünfundfünfzig"],
      ] },
      { title: "星期", head: ["星期", "德语", "星期", "德语"], rows: [
        ["一", "Montag", "五", "Freitag"], ["二", "Dienstag", "六", "Samstag"],
        ["三", "Mittwoch", "日", "Sonntag"], ["四", "Donnerstag", "", ""],
      ] },
      { title: "月份", head: ["月", "德语", "月", "德语"], rows: [
        ["1", "Januar", "7", "Juli"], ["2", "Februar", "8", "August"], ["3", "März", "9", "September"],
        ["4", "April", "10", "Oktober"], ["5", "Mai", "11", "November"], ["6", "Juni", "12", "Dezember"],
      ] },
      { title: "时间介词", head: ["什么时候", "介词", "例子"], rows: [
        ["几点钟", "um", "um drei Uhr"],
        ["星期 / 日期 / 时段", "am", "am Montag, am dritten Oktober, am Abend"],
        ["月份 / 季节", "im", "im Mai, im Sommer"],
      ] },
      { title: "日期（序数词）", head: ["日期", "德语"], rows: [
        ["1.", "der erste"], ["2.", "der zweite"], ["3.", "der dritte"], ["7.", "der siebte"],
        ["8.", "der achte"], ["20.", "der zwanzigste"], ["31.", "der einunddreißigste"],
      ] },
    ],
    examples: ["Wie spät ist es? — Es ist halb vier.", "Der Zug fährt um vierzehn Uhr zwölf.", "Am Montag habe ich frei.", "Ich habe am dritten Mai Geburtstag."],
    quiz: () => timeQuiz(),
  },
];
