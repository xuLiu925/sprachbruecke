# 通德 Sprachbrücke

给中文母语者用的德语学习网页应用。后端 Flask + SQLite，前端纯 HTML + JavaScript（无框架、无构建工具），轻到可以跑在一台旧安卓手机（Termux）上。

## 功能

- **词汇复习**：FSRS-5 间隔重复算法（自己实现，无依赖）；认词 + 拼写两种题型；der / die / das 颜色区分；浏览器朗读发音
- **冠词练习**、**听写**
- **语法基础**：24 个知识点（冠词、代词、介词、动词变位、语序、形容词词尾、比较级、完成时、可分动词、数字、钟点等），每个有速查表和选择题
- 单词详情（变格 / 变位）、添加单词、批量导入、按用户的修改和隐藏
- 多用户（默认只允许第一个用户注册）

## 运行

需要 Python 3。

```
pip install -r requirements.txt
python app.py
```

浏览器打开 `http://localhost:8000`，第一次注册的账号就是你的账号。之后想开放注册，设置环境变量 `ALLOW_REGISTER=1`。

数据库 `vocab.db` 和会话密钥 `.secret_key` 会在第一次运行时自动生成。

测试：`python tests/test_api.py`（使用临时数据库，输出 `ALL OK` 表示通过）。

## 单词书

仓库里**不包含单词书数据**（体积大，来源有版权限制），只自带 15 个示例词。可以用 `tools/` 里的脚本自己生成：

1. `tools/extract_wiktionary.py`：从德语维基词典 dump 中抽取词条
2. `tools/build_wordbook.py`：合并分级词表和词频数据
3. `tools/translate_wordbook.py`：添加中文释义（机器翻译）
4. `tools/import_wordbook.py data/wordbook.json`：导入数据库

前 3 步需要自己准备原始数据，并且需要几 GB 的内存和硬盘空间。请自行确认所用数据的许可条款。

## 说明

- 语法内容和示例是作者自己整理的，可能有错，请对照教材核对。
- 机器翻译的释义不一定准确，在 App 里点开单词就可以修改。

## 许可

代码采用 [MIT](LICENSE) 许可。
