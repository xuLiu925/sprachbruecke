"""敏感内容过滤(文档 docs/features/content-filter.md)

通德是语言学习应用, 不讨论政治、宗教, 不要色情、暴力、辱骂、歧视的内容。两层:
1. AI 提示词里加 SAFETY_RULE(主要靠这一层, AI 能理解意思, 换个说法也绕不过去);
2. 关键词兜底: blocked(...) 查用户名、意见反馈、报错、自建对话(描述、粘贴的结果、AI 生成的结果)、
   共用的 AI 内容(讲解、替换练习、AI 查词、构词、联想记忆), 命中了就不保存。

词表 = 下面的 DEFAULT_WORDS + 服务器上的 .blocked_words(一行一个, # 开头是注释, 不进版本库), 文件改了自动重新读。
- 中文词: 去掉空格和标点后按字串找("习 近 平"也能拦住)。中文不分词, 太短的词会误伤:
  “其中共有”里有“中共”、“出口交易”里有“口交”、“舞台独唱”里有“台独”, 所以只放不会和正常话连在一起的词。
- 英文 / 德文 / 拼音: 只按整个词找("Xi Jinping"、"heil hitler" 这样写), 不然 "hausextra" 里会找到 "sex"。
关键词只能挡随手写的, 拼音缩写、谐音、拆字挡不住; 别加太宽的词(如“中国”“政府”), 正常课文会被误伤。
"""
import os
import re

from database import BASE

WORDS_FILE = os.path.join(BASE, ".blocked_words")

SAFETY_RULE = ("- 这是语言学习应用：不写政治（包括评价任何国家、政党、政府和政治人物）、宗教争议、色情、暴力、"
               "毒品、歧视和辱骂相关的内容，不出现真实的政治人物。")

# 基础词表(一行一个): 政治话题(批评和吹捧两个方向都不要)、色情、辱骂、极端主义。按需要在 .blocked_words 里增加
DEFAULT_WORDS = """
习近平
习主席
习大大
包子帝
xi jinping
xijinping
彭丽媛
毛泽东
毛主席
邓小平
江泽民
胡锦涛
温家宝
共产党
共匪
ccp
党中央
独裁者
独裁政权
专制政权
暴政
推翻政府
颠覆国家
八九六四
六四事件
八九民运
天安门事件
坦克人
法轮功
法轮大法
台湾独立
西藏独立
新疆独立
香港独立
新疆集中营
再教育营
种族灭绝
达赖喇嘛
刘晓波
文化大革命
反华
辱华
小粉红
美分党
傻逼
煞笔
操你妈
草泥马
你妈逼
狗日的
去死吧
婊子
贱人
nigger
hurensohn
fotze
wichser
色情
做爱
强奸
卖淫
嫖娼
裸聊
约炮
porn
porno
sex
希特勒
hitler
heil hitler
sieg heil
纳粹万岁
nsdap
恐怖袭击
制造炸弹
圣战
"""

_CJK_SKIP = re.compile(r"[\s\W_]+", re.UNICODE)
_LATIN_SPLIT = re.compile(r"[^0-9a-zäöüß]+")
_cache = {"mtime": None, "cjk": (), "latin": ()}


def _is_latin(w):
    return all(c.isascii() or c in "äöüßÄÖÜ" for c in w)


def _latin_norm(s):
    return " " + " ".join(_LATIN_SPLIT.split(str(s).lower())).strip() + " "


def _load():
    try:
        mtime = os.path.getmtime(WORDS_FILE)
    except OSError:
        mtime = None
    if _cache["mtime"] == mtime and (_cache["cjk"] or _cache["latin"]):
        return _cache
    lines = DEFAULT_WORDS.splitlines()
    if mtime is not None:
        try:
            with open(WORDS_FILE, encoding="utf-8") as f:
                lines += list(f)
        except OSError:
            pass
    cjk, latin = set(), set()
    for line in lines:
        w = line.strip()
        if not w or w.startswith("#"):
            continue
        if _is_latin(w):
            n = _latin_norm(w)
            if n.strip():
                latin.add(n)
        else:
            n = _CJK_SKIP.sub("", w).lower()
            if n:
                cjk.add(n)
    _cache.update(mtime=mtime, cjk=tuple(cjk), latin=tuple(latin))
    return _cache


def _strings(v, out):
    if isinstance(v, dict):
        for x in v.values():
            _strings(x, out)
    elif isinstance(v, (list, tuple)):
        for x in v:
            _strings(x, out)
    elif isinstance(v, str):
        out.append(v)


def blocked(*values):
    """有敏感词返回 True。可以传字符串、列表、字典(查里面所有文字); 每段文字分开查, 不会把两段连起来误判"""
    c = _load()
    texts = []
    for v in values:
        _strings(v, texts)
    for t in texts:
        cjk = _CJK_SKIP.sub("", t).lower()
        latin = _latin_norm(t)
        if any(w in cjk for w in c["cjk"]) or any(w in latin for w in c["latin"]):
            return True
    return False


def added(output, *source):
    """AI 生成的内容里有敏感词、而原来的句子 / 词 / 释义里没有 → True。
    单词书里本来就有 Diktator、Vergewaltigung 这类词, 讲解它们不算; AI 自己加进去的才拦"""
    return blocked(output) and not blocked(*source)


AI_MSG = "AI 生成的内容不合适，没有保存，请再试一次"
MSG = "内容里有不适合的词（通德不讨论政治、色情、暴力等话题），请换一种说法"
