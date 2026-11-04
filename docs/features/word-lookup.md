# 点词查词

## 功能介绍

课文、例句、答题后的答案里，德语词都能点。点了从底部弹出单词卡：原形、冠词、复数、释义、发音、加入学习。

- 点的是变化形式（`regnet`、`Häuser`、`ging`）时，卡片显示原形，并写“文中是 regnet”。
- 一个词形能对上几个原形时（`regnet` 可以是 `regnen` 下雨，也可以是 `regen` 动），自动选单词书里更常用的那个，卡片下面写“不是这个词？ regen”，点一下换成另一个，左上角能返回。
- 词库里没有、德语词典里有的词，也弹卡片，写“词典里的词，还没进词库”。词典有中文释义就显示；没有就写“暂无释义”，加入学习时要自己写释义（只对自己显示）。
- 词库和词典都没有：显示“词库里没有这个词”，管理员可以用 AI 查。

## 详细设计

接口 GET `/api/lookup?w=词形` → `{word, alts}`，在 `lessons.py`：

1. `find_in_words(词形, strict=True)`：先按词库自己的数据找：原形、复数、变格 / 变位表（`word_forms`）、形容词词尾。**点词区分大小写**：文中的 `gefahren` 是 `fahren` 的完成时，不是 `Gefahr` 的复数 `Gefahren`。SQL 先不分大小写取最多 30 个候选，再在 Python 里按 `exact_match()` 挑出大小写完全一致的。查词搜索框（`/api/dict` 用的 `find_word()`）不区分大小写，用户输入 `haus` 也能查到。句首大写的 `Öffnen` 会再试一次小写。
2. 找不到时查德语词典 `data/lexicon.db`：`lexicon.lemmas_of(词形)` 返回所有可能的原形（本身是原形的在前，再加 `forms` 表“变化形式 → 原形”的对照）。词库里有 `word_forms` 的词不多（两千多个词没有变格 / 变位表，比如 `regnen`），这一步把它们补上。
3. 原形候选里词库有的：`lexicon_rows()` 按单词书词频排序，取第一个；其余候选放 `alts`（最多 3 个）。
4. 候选都不在词库里：取第一个在词典里有词条的，返回词典词条（`id` 为 null，`lexicon` / `glossary` 为 true，没有释义时 `needs_meaning`），字段和 `/api/dict` 的词典结果一样（`dictionary.glossary_row`）。

第 1 步就找到的词不给 `alts`：词库自己的数据对得上，比较可靠；词典的对照有噪音（如 `gegangen` 也对到 `hingehen`）。

`find_word()`（查词搜索框、名词 / 动词错题本手动加词在用）也加了第 2–3 步，搜 `regnet` 能搜到 `regnen`。

游客只能查试学的词：词典词条没有编号，游客点到返回 401，`alts` 不给。

前端在 `static/js/lessons.js` 的 `openWordSheet()`：`word.id` 为空时用 `openGlossaryWord()` 显示词典词条（“加入学习”沿用原来的逻辑：没有释义时先让用户写）；`alts` 用 `wsAltsShow()` 显示在 `#wsAlts`，点了调 `openWordSheet(原形)`，进单词卡的返回栈。课文词表（仓储词）里有的词优先用词表，不用词典词条。

已知限制：

- 几个原形都在词库里时按词频选，不看句子，`regnet` 这种大多数时候对，不保证每次都对。
- 词典 `forms` 来自维基词典和第三方 App 数据，没有逐条核对。
- 词典只有约 7% 的原形有中文释义。

## 变更记录

- 2026-11-04：新增词典反查原形（`regnet` → `regnen`，原来显示“词库里没有这个词”）、“不是这个词？”、词典词条卡片；点词改成区分大小写（`gefahren` 不再查到 `Gefahr`）。接口测试通过；本地浏览器按手机尺寸看过 `regnet`、换成 `regen`、返回、词典词 `Abschleppwagens`。同日已部署，服务器数据库上查过 regnet → regnen、gefahren → fahren、Abschleppwagens → 词典词条；没在真手机上看过。
