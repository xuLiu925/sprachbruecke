"""各模块共用的小工具"""
from functools import wraps

from flask import jsonify, request, session


def err(msg, code=400):
    return jsonify({"error": msg}), code


def client_ip():
    """访问者的 IP: 经过 Cloudflare Worker 时是 Worker 填的 X-Real-IP, 直接经过快速隧道时是 CF-Connecting-IP,
    局域网 / Tailscale 直连时是 remote_addr。注意: 绕过 Worker 直接访问隧道链接的人能自己填 X-Real-IP,
    所以按 IP 的限制只能挡住普通人, 挡不住专门伪造的"""
    for h in ("X-Real-IP", "CF-Connecting-IP"):
        v = (request.headers.get(h) or "").strip()
        if v and len(v) <= 45:
            return v
    return request.remote_addr or "?"


def current_user_id():
    return session.get("uid")


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if current_user_id() is None:
            return err("请先登录", 401)
        return fn(*a, **kw)

    return wrapper


def json_body():
    # 要求 JSON, 同时能挡掉大多数跨站表单提交
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    return data
