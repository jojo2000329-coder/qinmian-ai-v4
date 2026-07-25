"""Local user authentication and per-user data directory management."""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from .data_store import PROJECT_ROOT


MUTABLE_DATA_DIR = Path(
    os.getenv("QINMIAN_MUTABLE_DATA_DIR", str(PROJECT_ROOT / "data"))
).resolve()
USERS_FILE = MUTABLE_DATA_DIR / "users.json"
USER_DATA_DIR = MUTABLE_DATA_DIR / "user_data"
SESSION_SECRET_FILE = MUTABLE_DATA_DIR / ".session_secret"
LEGACY_CONVERSATIONS_DIR = MUTABLE_DATA_DIR / "conversations"

_USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fff.-]{3,32}$", re.UNICODE)
_USER_ID_RE = re.compile(r"^[a-f0-9]{16}$")
_LOCK = threading.RLock()


def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, ensure_ascii=False, indent=2)
            temp_name = temp_file.name
        os.replace(temp_name, path)
    finally:
        if temp_name:
            temp_path = Path(temp_name)
            if temp_path.exists():
                temp_path.unlink()


def normalize_username(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def validate_username(username: str) -> None:
    if not _USERNAME_RE.fullmatch(username):
        raise ValueError("用户名需为 3–32 个字符，可使用中文、字母、数字、点、横线或下划线")


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("密码至少需要 8 个字符")
    if len(password) > 128:
        raise ValueError("密码不能超过 128 个字符")


def user_data_path(user_id: str) -> Path:
    if not _USER_ID_RE.fullmatch(str(user_id or "")):
        raise ValueError("invalid user id")
    path = (USER_DATA_DIR / user_id).resolve()
    if path.parent != USER_DATA_DIR.resolve():
        raise ValueError("invalid user data path")
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_or_create_session_secret() -> str:
    configured = os.getenv("QINMIAN_SECRET_KEY", "").strip()
    if configured:
        return configured
    with _LOCK:
        if SESSION_SECRET_FILE.exists():
            secret = SESSION_SECRET_FILE.read_text(encoding="utf-8").strip()
            if secret:
                return secret
        secret = secrets.token_urlsafe(48)
        SESSION_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_path = SESSION_SECRET_FILE.with_suffix(".tmp")
        temp_path.write_text(secret, encoding="utf-8")
        os.replace(temp_path, SESSION_SECRET_FILE)
        return secret


def bootstrap_user_data(user_id: str) -> None:
    """Create an empty private storage area for a newly registered user."""
    root = user_data_path(user_id)
    conversations_dir = root / "conversations"
    knowledge_dir = root / "knowledge_base"
    conversations_dir.mkdir(parents=True, exist_ok=True)
    knowledge_dir.mkdir(parents=True, exist_ok=True)


class UserStore:
    """JSON-backed user registry. Passwords are stored only as secure hashes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or USERS_FILE
        self._users: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        with _LOCK:
            if not self.path.exists():
                self._users = []
                return
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                self._users = [
                    row for row in payload.get("users", [])
                    if isinstance(row, dict) and row.get("id") and row.get("password_hash")
                ]
            except (AttributeError, TypeError, json.JSONDecodeError, OSError) as exc:
                raise RuntimeError(f"用户注册表无法读取：{self.path}") from exc

    def _save(self) -> None:
        _atomic_write_json(
            self.path,
            {
                "version": 1,
                "updated_at": _timestamp(),
                "users": self._users,
            },
        )

    @staticmethod
    def public_user(user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": user["id"],
            "username": user["username"],
            "created_at": user.get("created_at", ""),
        }

    def count(self) -> int:
        with _LOCK:
            return len(self._users)

    def get(self, user_id: str) -> dict[str, Any] | None:
        with _LOCK:
            for user in self._users:
                if secrets.compare_digest(str(user.get("id", "")), str(user_id or "")):
                    return self.public_user(user)
        return None

    def register(self, username: Any, password: Any) -> tuple[dict[str, Any], bool]:
        normalized = normalize_username(username)
        password_text = str(password or "")
        validate_username(normalized)
        validate_password(password_text)
        lookup = normalized.casefold()

        with _LOCK:
            if any(str(user.get("username_key", "")).casefold() == lookup for user in self._users):
                raise ValueError("用户名已存在")
            user = {
                "id": secrets.token_hex(8),
                "username": normalized,
                "username_key": lookup,
                "password_hash": generate_password_hash(password_text),
                "created_at": _timestamp(),
            }
            self._users.append(user)
            self._save()

        bootstrap_user_data(user["id"])
        return self.public_user(user), False

    def authenticate(self, username: Any, password: Any) -> dict[str, Any] | None:
        lookup = normalize_username(username).casefold()
        password_text = str(password or "")
        with _LOCK:
            user = next(
                (
                    row for row in self._users
                    if str(row.get("username_key", row.get("username", ""))).casefold() == lookup
                ),
                None,
            )
            if not user or not check_password_hash(str(user.get("password_hash", "")), password_text):
                return None
            return self.public_user(user)
