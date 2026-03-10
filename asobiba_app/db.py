from __future__ import annotations

import math
import os
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .security import AuthError, hash_pin, validate_pin, validate_username, verify_pin


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "asobiba.sqlite3"
FAILED_LOGIN_LIMIT = 5
FAILED_LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_LOCKOUT_DURATION = timedelta(minutes=15)
CLIENT_RATE_LIMIT_ATTEMPTS = 12
CLIENT_RATE_LIMIT_WINDOW = timedelta(minutes=5)
INVALID_CREDENTIALS_MESSAGE = "ユーザー名または PIN が違います。"


def _database_path() -> Path:
    configured_path = os.environ.get("ASOBIBA_DB_PATH", "").strip()
    path = Path(configured_path).expanduser() if configured_path else DEFAULT_DB_PATH
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


DB_PATH = _database_path()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                pin_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                game_id TEXT NOT NULL,
                title TEXT NOT NULL,
                note TEXT NOT NULL,
                room_code TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                client_key TEXT NOT NULL,
                success INTEGER NOT NULL,
                attempted_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS login_lockouts (
                username TEXT PRIMARY KEY,
                failed_attempts INTEGER NOT NULL,
                locked_until TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_login_attempts_username_attempted_at
                ON login_attempts (username, attempted_at);

            CREATE INDEX IF NOT EXISTS idx_login_attempts_client_attempted_at
                ON login_attempts (client_key, attempted_at);
            """
        )


def create_user(username: str, pin: str) -> dict[str, Any]:
    username = validate_username(username)
    pin = validate_pin(pin)
    now = datetime.utcnow().isoformat(timespec="seconds")
    try:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users (username, pin_hash, created_at) VALUES (?, ?, ?)",
                (username, hash_pin(pin), now),
            )
            return {"id": cursor.lastrowid, "username": username, "created_at": now}
    except sqlite3.IntegrityError as exc:
        raise AuthError("そのユーザー名はすでに使われています。") from exc


def _auth_timestamp(value: datetime | None = None) -> str:
    return (value or datetime.utcnow()).isoformat(timespec="microseconds")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _remaining_minutes(future_time: datetime, now: datetime) -> int:
    return max(1, math.ceil((future_time - now).total_seconds() / 60))


def _client_key(value: str | None) -> str:
    normalized = (value or "").strip()
    return normalized[:120] or "unknown"


def _client_rate_limit_message(retry_at: datetime, now: datetime) -> str:
    minutes = _remaining_minutes(retry_at, now)
    return f"ログイン試行が多いため、あと{minutes}分ほど待ってからお試しください。"


def _username_lockout_message(locked_until: datetime, now: datetime) -> str:
    minutes = _remaining_minutes(locked_until, now)
    return f"ログイン失敗が続いたため、このユーザー名はあと{minutes}分ほど待ってからお試しください。"


def _check_client_rate_limit(conn: sqlite3.Connection, client_key: str, now: datetime) -> None:
    cutoff = _auth_timestamp(now - CLIENT_RATE_LIMIT_WINDOW)
    row = conn.execute(
        """
        SELECT COUNT(*) AS attempt_count, MIN(attempted_at) AS first_attempted_at
        FROM login_attempts
        WHERE client_key = ? AND success = 0 AND attempted_at >= ?
        """,
        (client_key, cutoff),
    ).fetchone()
    if not row or row["attempt_count"] < CLIENT_RATE_LIMIT_ATTEMPTS:
        return
    retry_at = _parse_timestamp(row["first_attempted_at"]) + CLIENT_RATE_LIMIT_WINDOW
    if retry_at > now:
        raise AuthError(_client_rate_limit_message(retry_at, now))


def _get_active_lockout(conn: sqlite3.Connection, username: str, now: datetime) -> datetime | None:
    row = conn.execute(
        "SELECT locked_until FROM login_lockouts WHERE username = ?",
        (username,),
    ).fetchone()
    if not row:
        return None
    locked_until = _parse_timestamp(row["locked_until"])
    if locked_until <= now:
        conn.execute("DELETE FROM login_lockouts WHERE username = ?", (username,))
        return None
    return locked_until


def _record_login_attempt(
    conn: sqlite3.Connection,
    username: str,
    client_key: str,
    success: bool,
    attempted_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO login_attempts (username, client_key, success, attempted_at)
        VALUES (?, ?, ?, ?)
        """,
        (username, client_key, int(success), attempted_at),
    )


def _recent_failed_attempts(conn: sqlite3.Connection, username: str, now: datetime) -> int:
    cutoff = _auth_timestamp(now - FAILED_LOGIN_WINDOW)
    last_success = conn.execute(
        "SELECT MAX(attempted_at) AS attempted_at FROM login_attempts WHERE username = ? AND success = 1",
        (username,),
    ).fetchone()["attempted_at"]
    lower_bound = max(cutoff, last_success) if last_success else cutoff
    return conn.execute(
        """
        SELECT COUNT(*) AS failure_count
        FROM login_attempts
        WHERE username = ? AND success = 0 AND attempted_at > ?
        """,
        (username, lower_bound),
    ).fetchone()["failure_count"]


def _set_lockout(conn: sqlite3.Connection, username: str, failed_attempts: int, now: datetime) -> datetime:
    locked_until = now + LOGIN_LOCKOUT_DURATION
    conn.execute(
        """
        INSERT INTO login_lockouts (username, failed_attempts, locked_until, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            failed_attempts = excluded.failed_attempts,
            locked_until = excluded.locked_until,
            updated_at = excluded.updated_at
        """,
        (username, failed_attempts, _auth_timestamp(locked_until), _auth_timestamp(now)),
    )
    return locked_until


def authenticate_user(username: str, pin: str, client_key: str | None = None) -> dict[str, Any]:
    username = validate_username(username)
    pin = validate_pin(pin)
    client_key = _client_key(client_key)
    now = datetime.utcnow()
    attempted_at = _auth_timestamp(now)
    error_message: str | None = None
    row: sqlite3.Row | None = None
    with get_connection() as conn:
        try:
            _check_client_rate_limit(conn, client_key, now)
        except AuthError as exc:
            error_message = str(exc)
        else:
            locked_until = _get_active_lockout(conn, username, now)
            if locked_until:
                error_message = _username_lockout_message(locked_until, now)
            else:
                row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
                success = bool(row and verify_pin(pin, row["pin_hash"]))
                _record_login_attempt(conn, username, client_key, success, attempted_at)
                if not success:
                    failed_attempts = _recent_failed_attempts(conn, username, now)
                    if failed_attempts >= FAILED_LOGIN_LIMIT:
                        locked_until = _set_lockout(conn, username, failed_attempts, now)
                        error_message = _username_lockout_message(locked_until, now)
                    else:
                        error_message = INVALID_CREDENTIALS_MESSAGE
                else:
                    conn.execute("DELETE FROM login_lockouts WHERE username = ?", (username,))
    if error_message:
        raise AuthError(error_message)
    return dict(row)


def get_user_by_id(user_id: str | int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT id, username, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def create_post(author_id: int, author_name: str, game_id: str, title: str, note: str, room_code: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO posts (author_id, author_name, game_id, title, note, room_code, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (author_id, author_name, game_id, title, note, room_code, datetime.utcnow().isoformat(timespec="seconds")),
        )


def list_open_posts() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM posts WHERE status = 'open' ORDER BY id DESC LIMIT 20"
        ).fetchall()
    return [dict(row) for row in rows]


def close_missing_room_posts(active_room_codes: Iterable[str]) -> None:
    room_codes = tuple(active_room_codes)
    with get_connection() as conn:
        if room_codes:
            placeholders = ", ".join("?" for _ in room_codes)
            conn.execute(
                f"UPDATE posts SET status = 'closed' WHERE status = 'open' AND room_code NOT IN ({placeholders})",
                room_codes,
            )
        else:
            conn.execute("UPDATE posts SET status = 'closed' WHERE status = 'open'")


def close_post(post_id: int, author_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE posts SET status = 'closed' WHERE id = ? AND author_id = ?",
            (post_id, author_id),
        )


def get_user_summary(user_id: int) -> dict[str, Any]:
    user = get_user_by_id(user_id)
    with get_connection() as conn:
        posts = conn.execute(
            "SELECT COUNT(*) AS count FROM posts WHERE author_id = ?",
            (user_id,),
        ).fetchone()["count"]
    return {"user": user, "post_count": posts}
