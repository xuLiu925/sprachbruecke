"""示例词和它们的变格 / 变位(自己整理的常见词, 可随时删改)"""
import json

SEED_WORDS = [
    ("Tisch", "名词", "der", "Tische", "桌子", "Der Tisch ist groß."),
    ("Lampe", "名词", "die", "Lampen", "灯", "Die Lampe steht auf dem Tisch."),
    ("Buch", "名词", "das", "Bücher", "书", "Ich lese ein Buch."),
    ("Apfel", "名词", "der", "Äpfel", "苹果", "Der Apfel ist rot."),
    ("Straße", "名词", "die", "Straßen", "街道", "Die Straße ist lang."),
    ("Haus", "名词", "das", "Häuser", "房子", "Das Haus ist alt."),
    ("Hund", "名词", "der", "Hunde", "狗", "Der Hund schläft."),
    ("Katze", "名词", "die", "Katzen", "猫", "Die Katze trinkt Milch."),
    ("Wasser", "名词", "das", "", "水(通常无复数)", "Ich trinke Wasser."),
    ("Freund", "名词", "der", "Freunde", "朋友(男)", "Er ist mein Freund."),
    ("Kind", "名词", "das", "Kinder", "孩子", "Das Kind spielt."),
    ("Arbeit", "名词", "die", "Arbeiten", "工作", "Die Arbeit macht Spaß."),
    ("gehen", "动词", "", "", "走, 去 (ging, ist gegangen)", "Ich gehe nach Hause."),
    ("lernen", "动词", "", "", "学习 (lernte, hat gelernt)", "Wir lernen Deutsch."),
    ("schnell", "形容词", "", "", "快的", "Der Zug ist schnell."),
]


# 示例词的单数第二格(阳性/中性; 阴性第二格不变, 不用写)
SEED_GENITIVE = {
    "Tisch": "Tisches", "Buch": "Buches", "Apfel": "Apfels", "Haus": "Hauses",
    "Hund": "Hundes", "Wasser": "Wassers", "Freund": "Freundes", "Kind": "Kindes",
}
SEED_PRAESENS = {
    "gehen": ["gehe", "gehst", "geht", "gehen", "geht", "gehen"],
    "lernen": ["lerne", "lernst", "lernt", "lernen", "lernt", "lernen"],
}

# 一、二、三、四格的冠词
ARTICLES_SG = {"der": ("der", "des", "dem", "den"),
               "die": ("die", "der", "der", "die"),
               "das": ("das", "des", "dem", "das")}
ARTICLES_PL = ("die", "der", "den", "die")


def noun_cases(gender, word, genitive, plural):
    """只适用于普通名词(不适用于 der Student → den Studenten 这类弱变化名词)"""
    a = ARTICLES_SG[gender]
    sg = [f"{a[0]} {word}", f"{a[1]} {genitive}", f"{a[2]} {word}", f"{a[3]} {word}"]
    pl = ["", "", "", ""]
    if plural:
        dat = plural if plural.endswith(("n", "s")) else plural + "n"
        pl = [f"{ARTICLES_PL[0]} {plural}", f"{ARTICLES_PL[1]} {plural}",
              f"{ARTICLES_PL[2]} {dat}", f"{ARTICLES_PL[3]} {plural}"]
    return {"cases": {"sg": sg, "pl": pl}}


def seed_forms():
    for german, _pos, gender, plural, *_ in SEED_WORDS:
        if gender:
            forms = noun_cases(gender, german, SEED_GENITIVE.get(german, german), plural)
        elif german in SEED_PRAESENS:
            forms = {"praesens": SEED_PRAESENS[german]}
        else:
            continue
        yield json.dumps(forms, ensure_ascii=False), german, gender
