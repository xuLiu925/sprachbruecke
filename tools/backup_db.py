"""备份 vocab.db（服务器上运行，只用标准库）

    python tools/backup_db.py daily    每天一份: backups/daily/vocab.YYYYMMDD.db.gz, 今天已有就跳过, 保留最近 7 份
    python tools/backup_db.py deploy   部署前一份: backups/vocab.db.YYYYMMDD-HHMMSS.gz, 保留最近 10 份

用 SQLite 的在线备份, 服务运行时也能得到一致的副本(直接 cp 可能拷到写了一半的数据)。
恢复: 先停服务, gunzip -c 备份文件 > vocab.db, 再启动。
"""
import glob
import gzip
import os
import shutil
import sqlite3
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "vocab.db")
BACKUPS = os.path.join(BASE, "backups")
KEEP = {"daily": 7, "deploy": 10}


def snapshot(dest):
    """在线备份到 dest(gzip 压缩), 先写临时文件, 完成后再改名, 中途失败不会留下坏文件"""
    tmp = dest + ".tmp"
    src = sqlite3.connect(DB)
    out = sqlite3.connect(tmp + ".db")
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    with open(tmp + ".db", "rb") as f, gzip.open(tmp, "wb") as g:
        shutil.copyfileobj(f, g)
    os.remove(tmp + ".db")
    os.replace(tmp, dest)


def prune(pattern, keep):
    files = sorted(glob.glob(pattern))      # 文件名里是日期时间, 按名字排就是按时间排
    for f in files[:-keep]:
        os.remove(f)


def main(kind):
    if not os.path.exists(DB):
        print("== 没有 vocab.db, 不用备份")
        return
    now = datetime.now()
    if kind == "daily":
        folder = os.path.join(BACKUPS, "daily")
        dest = os.path.join(folder, f"vocab.{now:%Y%m%d}.db.gz")
        pattern = os.path.join(folder, "vocab.*.db.gz")
    else:
        folder = BACKUPS
        dest = os.path.join(folder, f"vocab.db.{now:%Y%m%d-%H%M%S}.gz")
        pattern = os.path.join(folder, "vocab.db.*")    # 也清理以前没压缩的部署备份(名字同样以日期开头)
    os.makedirs(folder, exist_ok=True)
    if os.path.exists(dest):
        return
    snapshot(dest)
    prune(pattern, KEEP[kind])
    print(f"== 已备份到 {os.path.relpath(dest, BASE)}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in KEEP:
        sys.exit("用法: python tools/backup_db.py daily|deploy")
    main(sys.argv[1])
