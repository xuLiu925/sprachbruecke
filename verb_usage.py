"""动词搭配填空题: 这个动词要什么介词、支配第几格。接口在 verb_quiz.py, 这里是搭配表和出题。Claude 写的, 要请人抽查

USAGES = {动词原形: [(介词, 第几格, 词义, 错误的介词, [(句子, 正确的词, 错误的词, 翻译)])]}
- 有介词: 两个空 = 介词 + 冠词或代词, 选项是 正确 / 格错 / 介词错两个。没有介词: 一个空, 考格。
- 第几格: 2 = 第三格, 3 = 第四格(和 noun_quiz.CASE_NAMES 的下标一样)。
- 错误的词要和正确的词同性同数, 这样选错说明格错了, 不是不知道名词的词性。
- 干扰项必须真的是错的。写之前想一下: 换成干扰项后这句话还对不对。例如:
  sich freuen über 不能用 auf 当干扰项(另一个正确说法); mit dem Kollegen 不能用 den 当错误的词(mit den Kollegen 是对的复数);
  错误的介词要接不了这个格, 或这个动词不这样用(Es geht an die Arbeit、über den Kunden schicken 都是对的, 不能当干扰项);
  第三格的搭配用 für、um 最稳: 它们只接第四格, 配上第三格的冠词一定是错的。
  名词复数和单数同形时不能考 dem / den: folgt den Wagen 是对的复数。
- 介词 + dem 要避开能缩写的搭配(vom, zum, beim, am, im): 选项写不出缩写。用阴性、复数或 mein 这类词。
记忆按动词算, 一个动词有几个搭配时随机出一个。
"""
import random

import verb_quiz as vq
from noun_quiz import CASE_NAMES

REFLEXIVE = {"freuen", "interessieren", "kümmern", "ärgern", "erinnern", "gewöhnen", "bewerben", "entschuldigen", "bedanken",
             "beschweren", "unterhalten", "vorbereiten", "verlassen"}

USAGES = {
    # 介词 + 第四格
    "warten": [("auf", 3, "等", ("für", "an"), [
        ("Ich warte ___ ___ Bus.", "den", "dem", "我在等公交车。"),
        ("Der Fahrer wartet ___ ___ Papiere.", "die", "den", "司机在等文件。"),
        ("Wir warten ___ ___ Antwort.", "die", "der", "我们在等答复。")])],
    "denken": [("an", 3, "想到", ("für", "mit"), [
        ("Ich denke oft ___ ___ Urlaub.", "den", "dem", "我常常想着假期。"),
        ("Denkst du ___ ___ Termin?", "den", "dem", "你记得那个约定吗？"),
        ("Wir denken ___ ___ Lieferung.", "die", "der", "我们记着这批货。")])],
    "freuen": [("auf", 3, "期待（还没发生的事）", ("für", "an"), [
        ("Ich freue mich ___ ___ Wochenende.", "das", "dem", "我期待周末。"),
        ("Wir freuen uns ___ ___ Feier.", "die", "der", "我们期待这次聚会。")]),
               ("über", 3, "因为…高兴（已经发生的事）", ("für", "mit"), [
        ("Der Kunde freut sich ___ ___ Geschenk.", "das", "dem", "客户因为礼物很高兴。"),
        ("Ich freue mich ___ ___ Bonus.", "den", "dem", "我因为奖金很高兴。")])],
    "interessieren": [("für", 3, "对…感兴趣", ("an", "über"), [
        ("Ich interessiere mich ___ ___ Stelle.", "die", "der", "我对这个职位感兴趣。"),
        ("Interessierst du dich ___ ___ Job?", "den", "dem", "你对这份工作感兴趣吗？")])],
    "kümmern": [("um", 3, "照料，负责", ("für", "an"), [
        ("Ich kümmere mich ___ ___ Lieferung.", "die", "der", "我来负责这批货。"),
        ("Der Kollege kümmert sich ___ ___ Kunden.", "den", "dem", "同事负责这位客户。")])],
    "ärgern": [("über", 3, "因为…生气", ("auf", "an"), [
        ("Der Chef ärgert sich ___ ___ Fehler.", "den", "dem", "老板因为这个错误生气。"),
        ("Ich ärgere mich ___ ___ Verspätung.", "die", "der", "我因为晚点生气。")])],
    "erinnern": [("an", 3, "想起，记得", ("über", "für"), [
        ("Ich erinnere mich ___ ___ Termin.", "den", "dem", "我记得这个约定。"),
        ("Erinnerst du dich ___ ___ Kollegen?", "den", "dem", "你记得那位同事吗？")])],
    "gewöhnen": [("an", 3, "习惯于", ("auf", "mit"), [
        ("Ich gewöhne mich ___ ___ Arbeit.", "die", "der", "我在慢慢习惯这份工作。"),
        ("Wir gewöhnen uns ___ ___ Nachtschicht.", "die", "der", "我们在慢慢习惯夜班。")])],
    "vorbereiten": [("auf", 3, "为…做准备", ("an", "mit"), [
        ("Ich bereite mich ___ ___ Prüfung vor.", "die", "der", "我在准备考试。"),
        ("Wir bereiten uns ___ ___ Inventur vor.", "die", "der", "我们在为盘点做准备。")])],
    "bewerben": [("um", 3, "申请（职位）", ("mit", "an"), [
        ("Ich bewerbe mich ___ ___ Stelle.", "die", "der", "我申请这个职位。")]),
                 ("bei", 2, "向（公司）申请", ("für", "um"), [
        ("Er bewirbt sich ___ ___ Firma.", "der", "die", "他向这家公司申请工作。")])],
    "entschuldigen": [("für", 3, "为…道歉", ("an", "über"), [
        ("Ich entschuldige mich ___ ___ Fehler.", "den", "dem", "我为这个错误道歉。")]),
                      ("bei", 2, "向（某人）道歉", ("für", "um"), [
        ("Ich entschuldige mich ___ ___ Kundin.", "der", "die", "我向这位女客户道歉。")])],
    "bedanken": [("für", 3, "为…道谢", ("über", "an"), [
        ("Wir bedanken uns ___ ___ Hilfe.", "die", "der", "我们为这次帮助道谢。")]),
                 ("bei", 2, "向（某人）道谢", ("für", "um"), [
        ("Ich bedanke mich ___ ___ Kollegin.", "der", "die", "我向这位女同事道谢。")])],
    "beschweren": [("über", 3, "投诉（某事）", ("an", "für"), [
        ("Der Kunde beschwert sich ___ ___ Lieferung.", "die", "der", "客户投诉这批货。"),
        ("Ich beschwere mich ___ ___ Lärm.", "den", "dem", "我投诉噪音。")]),
                   ("bei", 2, "向（某人）投诉", ("für", "um"), [
        ("Er beschwert sich ___ ___ Chefin.", "der", "die", "他向女老板投诉。")])],
    "unterhalten": [("über", 3, "聊（某事）", ("mit", "an"), [
        ("Wir unterhalten uns ___ ___ Arbeit.", "die", "der", "我们聊工作。")]),
                    ("mit", 2, "和（某人）聊", ("für", "an"), [
        ("Ich unterhalte mich ___ ___ Fahrer.", "dem", "den", "我和司机聊天。")])],
    "hoffen": [("auf", 3, "希望得到", ("für", "an"), [
        ("Wir hoffen ___ ___ Antwort.", "eine", "einer", "我们希望得到答复。")])],
    "bitten": [("um", 3, "请求", ("nach", "mit"), [
        ("Ich bitte dich ___ ___ Liste.", "die", "der", "我请你给我这份清单。"),
        ("Wir bitten ___ ___ Bestätigung.", "eine", "einer", "我们请求一份确认。")])],
    "lachen": [("über", 3, "笑（某事）", ("mit", "von"), [
        ("Alle lachen ___ ___ Witz.", "den", "dem", "大家都被这个笑话逗笑了。")])],
    "achten": [("auf", 3, "注意", ("für", "an"), [
        ("Bitte achte ___ ___ Etiketten.", "die", "den", "请注意标签。"),
        ("Der Fahrer achtet ___ ___ Ladung.", "die", "der", "司机注意货物。")])],
    "aufpassen": [("auf", 3, "当心，看管", ("für", "an"), [
        ("Pass bitte ___ ___ Karton auf!", "den", "dem", "请当心这个纸箱！"),
        ("Der Kollege passt ___ ___ Ware auf.", "die", "der", "同事看管这批货。")])],
    "sorgen": [("für", 3, "负责，确保", ("um", "an"), [
        ("Der Chef sorgt ___ ___ Sicherheit.", "die", "der", "老板负责安全。")])],
    "verlassen": [("auf", 3, "依靠，信赖", ("an", "für"), [
        ("Ich verlasse mich ___ ___ Kollegen.", "den", "dem", "我信赖这位同事。"),
        ("Du kannst dich ___ ___ Fahrer verlassen.", "den", "dem", "你可以信赖这位司机。")])],
    "berichten": [("über", 3, "报告", ("für", "an"), [
        ("Der Kollege berichtet ___ ___ Unfall.", "den", "dem", "同事报告这次事故。")])],
    "informieren": [("über", 3, "告知（某事）", ("für", "an"), [
        ("Wir informieren den Kunden ___ ___ Lieferung.", "die", "der", "我们把这批货的情况告知客户。")])],
    "gehen": [("um", 3, "涉及（Es geht um …）", ("mit", "zu"), [
        ("Es geht ___ ___ Lieferung.", "die", "der", "这件事关于这批货。"),
        ("Worum geht es? Es geht ___ ___ Vertrag.", "den", "dem", "什么事？是关于合同的。")])],
    "einsteigen": [("in", 3, "上（车）", ("bei", "aus"), [
        ("Ich steige ___ ___ Bus ein.", "den", "dem", "我上公交车。")])],
    "schicken": [("an", 3, "寄给", ("bei", "mit"), [
        ("Ich schicke die Rechnung ___ ___ Kunden.", "den", "dem", "我把发票寄给客户。")])],
    "schreiben": [("an", 3, "写给", ("bei", "mit"), [
        ("Ich schreibe eine E-Mail ___ ___ Chef.", "den", "dem", "我给老板写一封邮件。")])],
    "liefern": [("an", 3, "送到，供货给", ("bei", "mit"), [
        ("Wir liefern die Ware ___ ___ Kunden.", "den", "dem", "我们把货送给客户。")])],
    "antworten": [("auf", 3, "回答（问题）", ("mit", "zu"), [
        ("Ich antworte ___ ___ Frage.", "die", "der", "我回答这个问题。")]),
                  ("", 2, "回答（某人）", (), [
        ("Ich antworte ___ Kundin.", "der", ("die",), "我回复这位女客户。"),
        ("Warum antwortest du ___ nicht?", "mir", ("mich", "ich"), "你为什么不回复我？")])],
    # 介词 + 第三格
    "sprechen": [("mit", 2, "和（某人）说话", ("für", "um"), [
        ("Ich spreche ___ ___ Fahrer.", "dem", "den", "我和司机说话。")]),
                 ("über", 3, "谈论（某事）", ("mit", "bei"), [
        ("Wir sprechen ___ ___ Problem.", "das", "dem", "我们谈论这个问题。")])],
    "reden": [("mit", 2, "和（某人）说话", ("für", "um"), [
        ("Ich rede ___ ___ Kundin.", "der", "die", "我和这位女客户说话。")]),
              ("über", 3, "谈论（某事）", ("mit", "bei"), [
        ("Wir reden ___ ___ Schicht.", "die", "der", "我们谈论这一班。")])],
    "telefonieren": [("mit", 2, "和（某人）打电话", ("für", "um"), [
        ("Ich telefoniere ___ ___ Kundin.", "der", "die", "我和这位女客户打电话。")])],
    "fragen": [("nach", 2, "询问（某事）", ("für", "um"), [
        ("Der Kunde fragt ___ ___ Lieferung.", "der", "die", "客户询问这批货。"),
        ("Der Fahrer fragt ___ ___ Weg.", "dem", "den", "司机问路。")]),
               ("", 3, "问（某人）", (), [
        ("Ich frage ___ Chef.", "den", ("dem", "des"), "我问老板。"),
        ("Ich frage ___ morgen.", "dich", ("dir", "du"), "我明天问你。")])],
    "träumen": [("von", 2, "梦想", ("für", "um"), [
        ("Ich träume ___ ___ Reise.", "einer", "eine", "我梦想一次旅行。")])],
    "anfangen": [("mit", 2, "开始做（某事）", ("für", "um"), [
        ("Wir fangen ___ ___ Inventur an.", "der", "die", "我们开始盘点。"),
        ("Ich fange ___ ___ Arbeit an.", "der", "die", "我开始工作。")])],
    "aufhören": [("mit", 2, "停止（某事）", ("für", "um"), [
        ("Ich höre ___ ___ Arbeit auf.", "der", "die", "我停下工作。")])],
    "beginnen": [("mit", 2, "开始做（某事）", ("für", "um"), [
        ("Wir beginnen ___ ___ Kontrolle.", "der", "die", "我们开始检查。")])],
    "abhängen": [("von", 2, "取决于", ("für", "um"), [
        ("Das hängt ___ ___ Lieferung ab.", "der", "die", "这取决于这批货。"),
        ("Das hängt ___ ___ Kosten ab.", "den", "die", "这取决于费用。")])],
    "arbeiten": [("bei", 2, "在（公司）工作", ("für", "um"), [
        ("Ich arbeite ___ ___ Firma.", "einer", "eine", "我在一家公司工作。")]),
                 ("an", 2, "做（某项工作）", ("für", "um"), [
        ("Ich arbeite ___ ___ Liste.", "der", "die", "我在做这份清单。")])],
    "teilnehmen": [("an", 2, "参加", ("für", "um"), [
        ("Ich nehme ___ ___ Schulung teil.", "der", "die", "我参加培训。"),
        ("Wir nehmen ___ ___ Besprechung teil.", "der", "die", "我们参加会议。")])],
    "fahren": [("mit", 2, "乘坐", ("für", "um"), [
        ("Ich fahre ___ ___ Bus zur Arbeit.", "dem", "den", "我坐公交车去上班。")])],
    "aussteigen": [("aus", 2, "下（车）", ("für", "um"), [
        ("Ich steige ___ ___ Bus aus.", "dem", "den", "我下公交车。")])],
    # 不带介词: 支配第三格
    "helfen": [("", 2, "帮助", (), [
        ("Der Kollege hilft ___ Fahrer.", "dem", ("den", "des"), "同事帮助司机。"),
        ("Ich helfe ___ gern.", "dir", ("dich", "du"), "我很乐意帮你。"),
        ("Wir helfen ___ Kundin.", "der", ("die",), "我们帮助这位女客户。")])],
    "danken": [("", 2, "感谢", (), [
        ("Ich danke ___ für die Hilfe.", "dir", ("dich", "du"), "我感谢你的帮助。"),
        ("Wir danken ___ Kollegin.", "der", ("die",), "我们感谢这位女同事。")])],
    "gefallen": [("", 2, "让…喜欢", (), [
        ("Die Arbeit gefällt ___.", "mir", ("mich", "ich"), "我喜欢这份工作。"),
        ("Das Lager gefällt ___ Chef.", "dem", ("den", "des"), "老板喜欢这个仓库。")])],
    "gehören": [("", 2, "属于", (), [
        ("Der Scanner gehört ___ Firma.", "der", ("die",), "扫描枪是公司的。"),
        ("Das Auto gehört ___.", "mir", ("mich", "ich"), "这辆车是我的。")])],
    "glauben": [("", 2, "相信（某人）", (), [
        ("Ich glaube ___.", "dir", ("dich", "du"), "我相信你。"),
        ("Der Chef glaubt ___ Fahrer nicht.", "dem", ("den", "des"), "老板不相信司机。")])],
    "passen": [("", 2, "（时间等）合适", (), [
        ("Der Termin passt ___ nicht.", "mir", ("mich", "ich"), "这个时间我不合适。"),
        ("Passt ___ das?", "dir", ("dich", "du"), "这样你合适吗？")])],
    "fehlen": [("", 2, "缺少", (), [
        ("Ein Karton fehlt ___.", "mir", ("mich", "ich"), "我少了一个纸箱。")])],
    "schmecken": [("", 2, "（对某人）好吃", (), [
        ("Der Kaffee schmeckt ___.", "mir", ("mich", "ich"), "我觉得咖啡好喝。"),
        ("Schmeckt ___ das Essen?", "dir", ("dich", "du"), "你觉得饭好吃吗？")])],
    "gratulieren": [("", 2, "祝贺", (), [
        ("Ich gratuliere ___.", "dir", ("dich", "du"), "我祝贺你。"),
        ("Wir gratulieren ___ Kollegin.", "der", ("die",), "我们祝贺这位女同事。")])],
    "zuhören": [("", 2, "听（某人说话）", (), [
        ("Hör ___ bitte zu!", "mir", ("mich", "ich"), "请听我说！"),
        ("Der Kollege hört ___ Chef zu.", "dem", ("den", "des"), "同事听老板说话。")])],
    "folgen": [("", 2, "跟随", (), [
        ("Der Lkw folgt ___ Transporter.", "dem", ("den", "des"), "卡车跟着这辆厢式货车。"),
        ("Folgen Sie ___!", "mir", ("mich", "ich"), "请跟我来！")])],
    "begegnen": [("", 2, "遇见", (), [
        ("Ich bin ___ Chef begegnet.", "dem", ("den", "des"), "我遇见了老板。")])],
    # 第三格 + 第四格: 这里考“给谁”
    "geben": [("", 2, "给（某人）", (), [
        ("Der Fahrer gibt ___ den Lieferschein.", "mir", ("mich", "ich"), "司机把送货单给我。")])],
    "erklären": [("", 2, "给（某人）解释", (), [
        ("Der Kollege erklärt ___ den Scanner.", "mir", ("mich", "ich"), "同事给我讲扫描枪怎么用。")])],
    "zeigen": [("", 2, "给（某人）看", (), [
        ("Ich zeige ___ das Lager.", "dir", ("dich", "du"), "我带你看看仓库。")])],
    # 不带介词: 中文母语者容易以为是第三格
    "anrufen": [("", 3, "给（某人）打电话", (), [
        ("Ich rufe ___ morgen an.", "dich", ("dir", "du"), "我明天给你打电话。"),
        ("Ich rufe ___ Kunden an.", "den", ("dem", "des"), "我给客户打电话。")])],
}
WORDS = ", ".join(f"'{g}'" for g in USAGES)
WHERE = f"w.gender = '' AND w.german IN ({WORDS})"


def label(german):
    return "sich " + german if german in REFLEXIVE else german


def question(row, usage, item):
    prep, case_no, meaning, wrong_preps, _items = usage
    prompt, right, wrong, zh = item
    name, case_name = label(row["german"]), CASE_NAMES[case_no]
    if prep:
        answer = f"{prep} … {right}"
        kinds = {f"{prep} … {wrong}": "case"}
        kinds.update({f"{p} … {right}": "prep" for p in wrong_preps})
        explain = f"{name} {prep} + {case_name}（{meaning}）：这里 {prep} 固定接{case_name} → {right}"
        pattern = f"{name} {prep} + {case_name}"
    else:
        answer = right
        kinds = {w: "case" for w in wrong}
        explain = f"{name} + {case_name}（{meaning}） → {right}"
        pattern = f"{name} + {case_name}"
    return {"word_id": row["id"], "german": row["german"], "meaning": row["meaning"], "prompt": prompt, "answer": answer,
            "fill": answer, "options": [answer, *kinds], "kinds": kinds, "skip_kind": "case", "explain": explain, "zh": zh,
            "source": "written", "must": f"（{name}）", "hint": f"{pattern} · {meaning}", "person": None, "verb": True,
            "stem_picks": [], "short": False}


def make_question(row, _weights):
    usages = USAGES.get(row["german"])
    if not usages:
        return None
    usage = random.choice(usages)
    return question(row, usage, random.choice(usage[4]))


vq.KINDS["usage"] = {"tense": "usage", "practice": "usage_practice", "list": "usage_list", "kinds": ("prep", "case"),
                     "make": make_question, "where": WHERE}
