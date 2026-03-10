from __future__ import annotations

import base64
import hmac
import os
import time
from typing import Any

from fastapi import Request

from .db import get_user_by_id
import hashlib


SECRET = os.environ.get("ASOBIBA_SECRET", "asobiba-dev-secret").encode("utf-8")
ROOM_TOKEN_TTL = 60 * 60 * 24


def _sign(payload: str) -> str:
    return hmac.new(SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def login_cookie_value(user_id: str) -> str:
    return f"{user_id}.{_sign(user_id)}"


def session_user_id(cookie_value: str | None) -> str | None:
    if not cookie_value or "." not in cookie_value:
        return None
    user_id, signature = cookie_value.split(".", 1)
    if hmac.compare_digest(signature, _sign(user_id)):
        return user_id
    return None


def current_user(request: Request) -> dict[str, Any] | None:
    user_id = session_user_id(request.cookies.get("asobiba_session"))
    if not user_id:
        return None
    return get_user_by_id(user_id)


def room_token(user_id: str, room_code: str) -> str:
    issued_at = str(int(time.time()))
    payload = f"{user_id}:{room_code}:{issued_at}"
    return base64.urlsafe_b64encode(f"{payload}:{_sign(payload)}".encode("utf-8")).decode("utf-8")


def validate_room_token(token: str, room_code: str) -> str | None:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        user_id, encoded_room, issued_at, signature = decoded.split(":", 3)
    except Exception:
        return None
    payload = f"{user_id}:{encoded_room}:{issued_at}"
    if encoded_room != room_code or not hmac.compare_digest(signature, _sign(payload)):
        return None
    if int(time.time()) - int(issued_at) > ROOM_TOKEN_TTL:
        return None
    return user_id
