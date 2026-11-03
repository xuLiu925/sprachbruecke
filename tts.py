"""在线德语发音(Blueprint): 设备上没有德语语音时, 前端改用这里

服务器替浏览器去谷歌翻译的朗读接口取 mp3 并缓存到 tts_cache/,
同一句话只取一次; 浏览器不用直接连谷歌(国内的朋友也能听)。
没登录时只能读试学的词和例句。
这个接口是非官方的, 谷歌随时可能限制, 取不到时返回 502, 前端退回系统语音。
"""
import hashlib
import os
import urllib.parse
import urllib.request

from flask import Blueprint, Response, request

from database import BASE
from helpers import current_user_id, err
from trial import allowed_tts

bp = Blueprint("tts", __name__)

CACHE_DIR = os.path.join(BASE, "tts_cache")
MAX_LEN = 200  # 谷歌接口一次最多约 200 字符
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
    if current_user_id() is None and not allowed_tts(text):   # 游客只能读试学的词(trial.py)
        return err("请先登录", 401)
    if len(text) > MAX_LEN:
        return err("文字太长")
    path = os.path.join(CACHE_DIR, hashlib.sha1(text.encode("utf-8")).hexdigest() + ".mp3")
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
    else:
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
