"""从单词书里彻底删掉几个词: 加进排除名单 → 重新生成单词书 → 备份数据库 → 导入

运行(在项目目录下):  python tools/remove_words.py ahh hmm
                    不带词就会提示输入(空格分开); 也可以双击 tools/remove_words.bat
区分大小写(名词首字母大写)。已经在排除名单里的词不会重复写。
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from database import DB_PATH  # noqa: E402

EXCLUDE = os.path.join(ROOT, "tools", "wordbook_exclude.txt")
STEPS = [
    ["tools/build_wordbook.py"],
    ["tools/translate_wordbook.py"],
    ["tools/merge_wordbook.py"],
    None,  # 备份数据库
    ["tools/import_wordbook.py", "data/wordbook.json"],
]


def add_to_exclude(words):
    old = set()
    text = ""
    if os.path.exists(EXCLUDE):
        with open(EXCLUDE, encoding="utf-8") as f:
            text = f.read()
        old = {l.split("#")[0].strip() for l in text.splitlines()}
    new = [w for w in dict.fromkeys(words) if w not in old]
    if new:
        with open(EXCLUDE, "a", encoding="utf-8") as f:
            if text and not text.endswith("\n"):
                f.write("\n")
            f.write("".join(w + "\n" for w in new))
    for w in words:
        print(("  + " if w in new else "  已在名单里: ") + w)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    words = sys.argv[1:] or input("要删的词(空格分开, 区分大小写): ").split()
    words = [w.strip() for w in words if w.strip()]
    if not words:
        print("没有输入词, 什么都没做")
        return 1
    print(f"== 1/{len(STEPS) + 1} 写进排除名单")
    add_to_exclude(words)

    for i, step in enumerate(STEPS, 2):
        if step is None:
            print(f"== {i}/{len(STEPS) + 1} 备份数据库")
            if os.path.exists(DB_PATH):
                shutil.copy2(DB_PATH, DB_PATH + ".bak")
                print("  已备份到 " + DB_PATH + ".bak")
            else:
                print("  还没有数据库, 跳过")
            continue
        print(f"== {i}/{len(STEPS) + 1} python {' '.join(step)}")
        if subprocess.run([sys.executable] + step, cwd=ROOT).returncode != 0:
            print("\n!! 这一步出错了, 后面的没有运行。把上面的报错发给 Claude。")
            return 1
    print("\n== 完成。手机上也要更新的话, 再运行一次 deploy.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
