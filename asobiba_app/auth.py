from __future__ import annotations

import base64
import hmac
import os
import time
from typing import Any

from fastapi import Request

from .db import get_user_by_id
from .security import validate_username, AuthError
import hashlib


SECRET = os.environ.get("ASOBIBA_SECRET", "asobiba-dev-secret").encode("utf-8")
ROOM_TOKEN_TTL = 60 * 60 * 24


def _sign(payload: str) -> str:
    return hmac.new(SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def login_cookie_value(user_id: str) -> str:
    return f"{user_id}.{_sign(user_id)}"


def guest_cookie_value(guest_id: str, username: str) -> str:
    safe_name = validate_username(username)
    payload = f"guest:{guest_id}:{safe_name}"
    return f"{payload}.{_sign(payload)}"


def session_user_id(cookie_value: str | None) -> str | None:
    if not cookie_value or "." not in cookie_value:
        return None
    user_id, signature = cookie_value.split(".", 1)
    if hmac.compare_digest(signature, _sign(user_id)):
        return user_id
    return None


def current_user(request: Request) -> dict[str, Any] | None:
    raw = request.cookies.get("asobiba_session")
    user_id = session_user_id(raw)
    if user_id:
        user = get_user_by_id(user_id)
        if user:
            return {**user, "is_guest": False}
    guest = guest_identity(raw)
    if not guest:
        return None
    return guest


def guest_identity(cookie_value: str | None) -> dict[str, Any] | None:
    if not cookie_value or "." not in cookie_value:
        return None
    payload, signature = cookie_value.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(payload)):
        return None
    if not payload.startswith("guest:"):
        return None
    try:
        _, guest_id, username = payload.split(":", 2)
        return {
            "id": f"guest:{guest_id}",
            "username": validate_username(username),
            "is_guest": True,
            "created_at": "",
        }
    except (ValueError, AuthError):
        return None


def room_token(user_id: str, room_code: str) -> str:
    return room_token_for_user({"id": user_id, "username": "", "is_guest": False}, room_code)


def room_token_for_user(user: dict[str, Any], room_code: str) -> str:
    issued_at = str(int(time.time()))
    user_id = str(user.get("id", ""))
    username = str(user.get("username", ""))
    guest_flag = "1" if user.get("is_guest") else "0"
    payload = f"{user_id}:{username}:{guest_flag}:{room_code}:{issued_at}"
    return base64.urlsafe_b64encode(f"{payload}:{_sign(payload)}".encode("utf-8")).decode("utf-8")


def validate_room_token(token: str, room_code: str) -> dict[str, Any] | None:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        user_id, username, guest_flag, encoded_room, issued_at, signature = decoded.split(":", 5)
    except Exception:
        return None
    payload = f"{user_id}:{username}:{guest_flag}:{encoded_room}:{issued_at}"
    if encoded_room != room_code or not hmac.compare_digest(signature, _sign(payload)):
        return None
    if int(time.time()) - int(issued_at) > ROOM_TOKEN_TTL:
        return None
    try:
        safe_name = validate_username(username)
    except AuthError:
        return None
    return {
        "id": user_id,
        "username": safe_name,
        "is_guest": guest_flag == "1",
    }
