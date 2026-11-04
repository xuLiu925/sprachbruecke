"""AI 提示词里只放服务器自己的数据(文档 docs/features/ai-quota.md 的“防投毒”)

讲解、替换练习、AI 查词、构词、联想记忆的结果按句子 / 词保存, 所有人共用。
如果提示词里的中文翻译、释义、原句由前端传, 有人就能在里面写“讲解里加上某某网址”,
AI 照做后存下来, 之后所有人看到的都是被改过的内容。所以这些都从这里查, 查不到就不给 AI(AI 自己理解)。
"""
import lexicon
from database import get_db
from lessons import like_escape, load_items

NO_MEANING = "释义待补充"


def _lesson_zh():
    """自带课文里 德语 → 中文(课文每一行 + 写作参考答案), 课文文件变了才重算"""
    items = load_items()
    if items.get("zh_mtime") != items["mtime"]:
        zh = {}
        for lesson in items["lessons"].values():
            rows = list(lesson.get("lines", []))
            task = lesson.get("task")
            if isinstance(task, dict):
                rows += [m for m in task.get("model", []) if isinstance(m, dict)]
            for r in rows:
                if r.get("de") and r.get("zh"):
                    zh.setdefault(r["de"], r["zh"])
        items["zh_by_de"], items["zh_mtime"] = zh, items["mtime"]
    return items["zh_by_de"]


def official_zh(de):
    """这句德语在自带课文或公共词库例句里的中文翻译; 不是这些地方的句子(自建对话、自己写的例句、
    程序拼出来的题)返回空字符串"""
    zh = _lesson_zh().get(de)
    if zh:
        return zh
    row = get_db().execute(
        "SELECT example FROM words WHERE status = 'public' AND example LIKE ? ESCAPE '\\' LIMIT 1",
        (like_escape(de) + "\n%",)).fetchone()
    if row:
        lines = row["example"].split("\n")
        if lines[0] == de and len(lines) > 1:
            return lines[1].strip()
    return ""


def word_meaning(german, gender=None):
    """词的释义: 公共词库 > 德语词典; 都没有返回空字符串"""
    sql = "SELECT meaning FROM words WHERE status = 'public' AND german = ? AND meaning != '' AND meaning != ?"
    args = [german, NO_MEANING]
    if gender is not None:
        sql += " AND gender = ?"
        args.append(gender)
    row = get_db().execute(sql + " LIMIT 1", args).fetchone()
    if row:
        return row["meaning"]
    hit, _ = lexicon.find(german, gender or "")
    if hit and (gender is None or hit.get("gender") == gender):
        return (hit.get("meaning") or "").strip()
    return ""


def known_genders(german):
    """词库和词典里这个名词的冠词; 都查不到返回空集合(不知道, 不拦)"""
    rows = get_db().execute("SELECT DISTINCT gender FROM words WHERE status = 'public' AND german = ? AND gender != ''",
                            (german,)).fetchall()
    out = {r["gender"] for r in rows}
    hit, _ = lexicon.find(german)
    if hit and hit.get("german") == german and hit.get("gender"):
        out.add(hit["gender"])
    return out


def official_context(sentence, word):
    """AI 查词带的原句: 只有自带课文或公共例句里的句子、而且真的含这个词才用"""
    if not sentence or word.lower() not in sentence.lower():
        return ""
    return sentence if official_zh(sentence) else ""
