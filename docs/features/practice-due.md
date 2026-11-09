# 今天还要练

## 功能介绍

今日学习只管单词的记忆。定冠词、动词变位、完成时、动词搭配、听写、句子练习各有自己的复习排期，以前要自己记得一个个点进去看。

现在「今天」页“今日学习”下面有“今天还要练”：

- 列出今天到了复习时间的练习和词数，比如“定冠词 · 12 个名词的词性到了复习时间”。
- 点一下直接开始，**只出到期的词**，不用先选单词书或错题本，也不混新词。到期的词不管在哪本单词书里都会出。
- 做完一组还有到期的，就接着出；都做完了，页面会说“今天到期的都练完了”。
- 情景课的整句复习也列在这里（到期的句子数）。复数练习还没有复习排期，显示错题数。
- 没有到期的练习时，这一块不显示。

以前这里叫“推荐练习”，只显示错题数，点进去还要再选范围。

## 详细设计

- 后端 `practice_due.py`：`GET /api/today/practice?tz=` 返回 `{due: {nouns, verbs, perfekt, usage, dictation, sent-cloze, sent-order, sent-translate, sent-listen}}`。
  - 每项数的是这个用户在对应练习表（`noun_practice`、`verb_practice`、`perfekt_practice`、`usage_practice`、`dict_practice`、`sent_practice` 按 `mode`）里练过、`next_review` 为空（老记录）或在今天结束之前的词，条件和各练习出题时“到期”的条件一样；只算 `my_words` 里的词（自己删掉的不算），名词、动词、听写的筛选条件也和出题时一样。
  - “今天”按用户本地日期，凌晨 4 点换日（`today.local_day`）。
  - 只数不出题，不算免费次数。
- 各练习的出题接口多了一个范围 `scope=due`：`/api/grammar/nouns`、`/api/grammar/verbs|perfekt|usage`、`/api/dictation`、`/api/sentences`。只取到期的词，最容易忘的优先，不按单词书过滤，不补新词和没到期的词。这个范围只用于出题，“查看单词”等接口没有。
- 前端 `home.js` 的 `showRecommend()` 和 `DUE_PRACTICE`：每项点了调用 `gStartDue(知识点)`（设 `gTopic`、`gScopeNow = "due"` 进 `#gquiz`）、`dStart("due")` 或 `sStartDue(题型)`。这些都不改动用户在练习入口页选过的范围（不写 `gScope` / `dScope` / `sScope`）。
- 答题页在 `due` 范围下没有题时显示“今天到期的都练完了”。

## 变更记录

- 2026-11-09：第一版，取代今天页的“推荐练习”。
