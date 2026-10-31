"""语法题库的初始题目。启动时导入数据库 grammar_questions, 已有的不重复, 也不覆盖后来的修改
内容是 Claude 写的, 要提醒用户请老师或母语者抽查。
不用单复数同形的词(Scanner、Artikel、Hubwagen)考第四格、第三格: 填 den 和 die 都说得通, 这种题不公平
"""

# 定冠词的海外仓题: [句子, 答案, 提示, 解释, 中文]
WAREHOUSE_DEF = [
      ["___ Palette steht an Rampe zwei.", "die", "die Palette · 阴性", "主语用第一格，阴性 → die", "托盘在二号月台。"],
      ["___ Lieferschein liegt auf dem Tisch.", "der", "der Lieferschein · 阳性", "主语用第一格，阳性 → der", "送货单在桌子上。"],
      ["___ Scanner funktioniert nicht.", "der", "der Scanner · 阳性", "主语用第一格，动词是单数，阳性 → der", "这把扫描枪不能用。"],
      ["___ Etikett ist beschädigt.", "das", "das Etikett · 中性", "主语用第一格，中性 → das", "标签破损了。"],
      ["___ Fahrer wartet an Tor drei.", "der", "der Fahrer · 阳性", "主语用第一格，动词 wartet 是单数 → der", "司机在三号门等着。"],
      ["___ Kartons stehen im Regal.", "die", "der Karton · 这里是复数", "主语用第一格，复数 → die", "纸箱放在货架上。"],
      ["___ Lager ist heute voll.", "das", "das Lager · 中性", "主语用第一格，中性 → das", "仓库今天满了。"],
      ["___ Sendung ist schon fertig.", "die", "die Sendung · 阴性", "主语用第一格，阴性 → die", "这批货已经准备好了。"],
      ["___ Retouren kommen aus Frankreich.", "die", "die Retoure · 这里是复数", "主语用第一格，复数 → die", "这些退货来自法国。"],
      ["Ich scanne ___ Etikett.", "das", "das Etikett · 中性", "scannen + 第四格；中性第四格还是 das", "我扫描标签。"],
      ["Der Fahrer unterschreibt ___ Frachtbrief.", "den", "der Frachtbrief · 阳性", "unterschreiben + 第四格；阳性第四格 → den", "司机在运单上签字。"],
      ["Bitte öffnen Sie ___ Tor.", "das", "das Tor · 中性", "öffnen + 第四格；中性第四格还是 das", "请打开大门。"],
      ["Wir packen ___ Bestellung.", "die", "die Bestellung · 阴性", "packen + 第四格；阴性第四格还是 die", "我们打包这个订单。"],
      ["Ich hole ___ Karton aus dem Regal.", "den", "der Karton · 单数阳性", "holen + 第四格；阳性第四格 → den", "我从货架上取下这个纸箱。"],
      ["Ich kontrolliere ___ Ware.", "die", "die Ware · 阴性", "kontrollieren + 第四格；阴性第四格还是 die", "我检查货物。"],
      ["Er lädt ___ Paletten auf den LKW.", "die", "die Palette · 这里是复数", "laden + 第四格；复数第四格 → die", "他把托盘装上卡车。"],
      ["Hast du ___ Lieferschein?", "den", "der Lieferschein · 阳性", "haben + 第四格；阳性第四格 → den", "你有送货单吗？"],
      ["Bitte prüfen Sie ___ Anzahl.", "die", "die Anzahl · 阴性", "prüfen + 第四格；阴性第四格还是 die", "请核对数量。"],
      ["Wir brauchen ___ Rampe.", "die", "die Rampe · 阴性", "brauchen + 第四格；阴性第四格还是 die", "我们需要这个月台。"],
      ["Ich spreche mit ___ Fahrer.", "dem", "der Fahrer · 单数阳性", "mit + 第三格；阳性第三格 → dem", "我和司机谈话。"],
      ["Der Karton liegt auf ___ Palette.", "der", "die Palette · 阴性", "auf 表示位置（在哪里）+ 第三格；阴性第三格 → der", "纸箱在托盘上。"],
      ["Die Ware steht in ___ Halle.", "der", "die Halle · 阴性", "in 表示位置 + 第三格；阴性第三格 → der", "货物放在库房里。"],
      ["Das Etikett klebt auf ___ Karton.", "dem", "der Karton · 单数阳性", "auf 表示位置 + 第三格；阳性第三格 → dem", "标签贴在纸箱上。"],
      ["Der Lieferschein liegt in ___ Fach.", "dem", "das Fach · 中性", "in 表示位置 + 第三格；中性第三格 → dem", "送货单在货格里。"],
      ["Wir helfen ___ Fahrern.", "den", "der Fahrer · 这里是复数", "helfen + 第三格；复数第三格 → den，名词加 -n", "我们帮助司机们。"],
      ["Ich arbeite in ___ Lager.", "dem", "das Lager · 单数中性", "in 表示位置 + 第三格；中性第三格 → dem", "我在这个仓库工作。"],
      ["Mein Kollege spricht mit ___ Kundin.", "der", "die Kundin · 阴性", "mit + 第三格；阴性第三格 → der", "我的同事和女客户谈话。"],
      ["Die Palette steht an ___ Rampe.", "der", "die Rampe · 阴性", "an 表示位置 + 第三格；阴性第三格 → der", "托盘在月台旁。"],
      ["Der Fahrer wartet an ___ Tor.", "dem", "das Tor · 中性", "an 表示位置 + 第三格；中性第三格 → dem", "司机在大门旁等着。"],
      ["Das ist die Nummer ___ Sendung.", "der", "die Sendung · 阴性", "“……的”用第二格；阴性第二格 → der", "这是这批货的编号。"],
      ["Das ist der Name ___ Fahrers.", "des", "der Fahrer · 阳性", "“……的”用第二格；阳性第二格 → des，名词加 -s", "这是司机的名字。"],
      ["Wo ist der Schlüssel ___ Lagers?", "des", "das Lager · 中性", "“……的”用第二格；中性第二格 → des，名词加 -s", "仓库的钥匙在哪里？"],
      ["Die Farbe ___ Etiketts ist weiß.", "des", "das Etikett · 中性", "“……的”用第二格；中性第二格 → des，名词加 -s", "标签的颜色是白色。"],
      ["Das ist die Adresse ___ Kundin.", "der", "die Kundin · 阴性", "“……的”用第二格；阴性第二格 → der", "这是女客户的地址。"],
]

SEED_QUESTIONS = {"art-def": WAREHOUSE_DEF}
