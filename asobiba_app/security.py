from __future__ import annotations

import hashlib
import hmac
import os
import re


PIN_ITERATIONS = 180_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-ぁ-んァ-ヶ一-龠]{2,20}$")


class AuthError(ValueError):
    pass


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.fullmatch(username):
        raise AuthError("ユーザー名は2〜20文字の英数字・日本語・_・- で入力してください。")
    return username


def validate_pin(pin: str) -> str:
    pin = pin.strip()
    if len(pin) != 4 or not pin.isdigit():
        raise AuthError("PIN は数字4桁で入力してください。")
    return pin


def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PIN_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split("$", 1)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), PIN_ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)
