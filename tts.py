"""在线德语发音(Blueprint): 设备上没有德语语音时, 前端改用这里

服务器替浏览器去谷歌翻译的朗读接口取 mp3 并缓存到 tts_cache/,
同一句话只取一次; 浏览器不用直接连谷歌(国内的朋友也能听)。
没登录时也能用, 但游客触发的新取(缓存里没有的)全站每小时最多 GUEST_FETCH_PER_HOUR 次;
试学的词不算(trial.py 的 allowed_tts)。
这个接口是非官方的, 谷歌随时可能限制, 取不到时返回 502, 前端退回系统语音。
"""
import hashlib
import os
import threading
import time
import urllib.parse
import urllib.request

from flask import Blueprint, Response, request

from auth import is_admin
from database import BASE
from helpers import current_user_id, err
from trial import allowed_tts

bp = Blueprint("tts", __name__)

CACHE_DIR = os.path.join(BASE, "tts_cache")
MAX_LEN = 200  # 谷歌接口一次最多约 200 字符
GUEST_FETCH_PER_HOUR = 200
USER_FETCH_PER_HOUR = 300   # 登录用户每人每小时新取几条(缓存里有的不算); 防止有人刷接口让谷歌封了服务器 IP
_guest_fetches = []   # 游客新取的时间戳(内存里, 重启清零)
_user_fetches = {}    # 用户编号 → 新取的时间戳
_guest_lock = threading.Lock()


def user_fetch_ok(uid):
    """登录用户新取一次: 最近一小时没超限就记一笔并返回 True。管理员不限"""
    if is_admin(uid):
        return True
    now = time.time()
    with _guest_lock:
        lst = [t for t in _user_fetches.get(uid, []) if t > now - 3600]
        if len(lst) >= USER_FETCH_PER_HOUR:
            _user_fetches[uid] = lst
            return False
        lst.append(now)
        _user_fetches[uid] = lst
        return True


def guest_fetch_ok():
    """游客新取一次: 最近一小时没超限就记一笔并返回 True"""
    now = time.time()
    with _guest_lock:
        while _guest_fetches and _guest_fetches[0] < now - 3600:
            _guest_fetches.pop(0)
        if len(_guest_fetches) >= GUEST_FETCH_PER_HOUR:
            return False
        _guest_fetches.append(now)
        return True


GOOGLE_URL = "https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=de&q="


def _fetch(text):
    req = urllib.request.Request(
        GOOGLE_URL + urllib.parse.quote(text),
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://translate.google.com/"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        data = r.read()
    if not data or len(data) > 2 * 1024 * 1024:
        raise ValueError("bad audio")
    return data


@bp.get("/api/tts")
def tts():
    text = " ".join((request.args.get("q") or "").split())
    if not text:
        return err("缺少文字")
    if len(text) > MAX_LEN:
        return err("文字太长")
    path = os.path.join(CACHE_DIR, hashlib.sha1(text.encode("utf-8")).hexdigest() + ".mp3")
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
    else:
        uid = current_user_id()
        if uid is None and not allowed_tts(text) and not guest_fetch_ok():
            return err("在线发音太忙，登录后再试", 429)   # 前端会退回设备语音
        if uid is not None and not user_fetch_ok(uid):
            return err("在线发音用得太多了，过一会儿再试", 429)
        try:
            data = _fetch(text)
        except Exception:
            return err("在线发音暂时不可用", 502)
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    resp = Response(data, mimetype="audio/mpeg")
    resp.headers["Cache-Control"] = "private, max-age=2592000"  # 浏览器也缓存 30 天
    return resp
