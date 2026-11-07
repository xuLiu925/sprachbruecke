# 听写

## 功能介绍

听发音，写出单词（名词按「我的」页的设置带冠词）。入口：底部「练习」→ 听写。

- **练习范围**：单词书（A1–C1、专题书、全部单词）或听写错题本，每个范围显示已练、已掌握、待巩固的词数，点“查看”能看这个范围里的词。
- **按记忆情况选词**：每组 20 个词，先出到期的词，再出没练过的（今日学习学过的排前面，然后按词频），最后用还没到期、但最容易忘的词补满。
- **本组内重考**：写错的词排到这组最后再考一次。得分只算第一次作答。
- **写错时标出错的字母**：“你写的”里多出来或写错的字母标红，“正确”里漏掉的字母标绿。
- **听写错题本**：写错过的词自动进去，记忆稳定后自动移出；也可以手动加词、移除。统一错题本页 `#wrong` 里也有“听写”这一类。
- **单词卡**：答完后点“单词卡”（电脑按 D），能看变格、例句等。
- 不影响今日学习的复习计划。

快捷键（电脑）：回车 = 检查 / 下一个，Ctrl+回车 = 再听一遍，D = 单词卡（答完后），Backspace / “‹ 上一个” = 回看（不能改答案），Esc = 返回。

## 详细设计

- 后端 `dictation.py`，结构照定冠词练习 `noun_quiz.py`，并复用它的 `update_practice()`（FSRS 更新）和 `pick_round()`（到期 / 新词 / 备用的配比）。
- 表：`dict_practice`（字段同 `noun_practice`：`stability / difficulty / last_review / next_review / weak` 等）、`dict_list`（手动加进错题本的词）。听写和词义复习是不同的能力，所以不用 `progress`。
- 评分：写对 = 良好（3），写错 = 忘了（1），写错后最早明天再出；同一天再写对不算数。稳定性 ≥ 7 天移出错题本，≥ 21 天算已掌握。手动加的词要手动移除。
- 对错由前端判断（`review.js` 的 `checkSpell()`，`ae / oe / ue / ss` 也算对），后端只记结果。只上报每组第一次作答，重考那一次不上报。
- 能出题的词：不超过 40 个字符，不含数字、括号、斜线、点和逗号（缩写这类词读出来没法写）。
- 接口：
  - `GET /api/dictation?scope=&n=20&tz=`：出一组题（免费版每天 3 组，`billing.py` 的 `LIMITS`）
  - `GET /api/dictation/books`：各个范围的统计（字段和定冠词一样，`nouns` = 词数，前端共用 `scopeItems()`）
  - `GET /api/dictation/words?scope=&page=`：查看一个范围里的词
  - `POST /api/dictation/result` `{word_id, ok}`：记一次作答
  - `POST /api/dictation/list` `{word_id}` 或 `{text}`、`DELETE /api/dictation/list/<id>`：手动加进错题本 / 移出错题本
- 前端 `static/js/dictation.js`：入口页 `#dictation`（选练习范围），答题页 `#dquiz`；单词列表用 `gnouns.js`（`DICT_LIST`）。
- 旧接口 `/api/drill/dictation`（随机抽学过的 20 个词）已删除。

## 变更记录

- 2026-11-07：重做。加练习范围、FSRS 排期、本组内重考、听写错题本（并进统一错题本页）、写错时标出错的字母、单词卡按钮。删除旧接口 `/api/drill/dictation`。
