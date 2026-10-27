"""各模块共用的小工具"""
from functools import wraps

from flask import jsonify, request, session


def err(msg, code=400):
    return jsonify({"error": msg}), code


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
