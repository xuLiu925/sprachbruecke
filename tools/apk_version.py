"""打包安卓 App 后写 static/tongde.json(android/build-apk.bat 调用), 网页据此提示 App 里的用户更新。

版本号从 android/app/build.gradle 读(versionName / versionCode), 更新说明从 android/release-notes.txt 读
(第一段, 空行以前的内容, 最多 200 字)。文件不进 git, 随 deploy.bat 的 static/ 一起上传。
文档 docs/features/android-app.md
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    with open(os.path.join(BASE, "android", "app", "build.gradle"), encoding="utf-8") as f:
        gradle = f.read()
    name = re.search(r'versionName\s+"([^"]+)"', gradle).group(1)
    code = int(re.search(r"versionCode\s+(\d+)", gradle).group(1))
    notes = ""
    path = os.path.join(BASE, "android", "release-notes.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = [l.rstrip() for l in f if not l.startswith("#")]
        first = "\n".join(lines).strip().split("\n\n")[0]
        notes = first.strip()[:200]
    out = {"version": name, "code": code, "notes": notes}
    with open(os.path.join(BASE, "static", "tongde.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"== static/tongde.json: {name} ({code})")


if __name__ == "__main__":
    sys.exit(main())
