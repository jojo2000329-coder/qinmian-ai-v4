"""Encrypted, per-user Bring Your Own Key (BYOK) LLM settings."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .api_config import normalize_provider_config, public_provider_presets
from .auth_store import user_data_path
from .llm import LLMClient
from .persistence import (
    database_enabled,
    delete_document,
    load_document,
    save_document,
)


class UserLLMConfigStore:
    """Store one encrypted OpenAI-compatible API configuration per user."""

    def __init__(
        self,
        secret_key: str,
        *,
        base_dir: Path | None = None,
        use_database: bool | None = None,
    ) -> None:
        digest = hashlib.sha256(str(secret_key).encode("utf-8")).digest()
        self._cipher = Fernet(base64.urlsafe_b64encode(digest))
        self._base_dir = Path(base_dir).resolve() if base_dir is not None else None
        self._use_database = database_enabled() if use_database is None else bool(use_database)
        self._clients: dict[str, LLMClient] = {}
        self._lock = threading.RLock()

    def _path(self, user_id: str) -> Path:
        if self._base_dir is None:
            return user_data_path(user_id) / "llm_config.json"
        path = (self._base_dir / user_id / "llm_config.json").resolve()
        if path.parent.parent != self._base_dir:
            raise ValueError("invalid user id")
        return path

    def _load(self, user_id: str) -> dict[str, Any]:
        if self._use_database:
            payload = load_document("llm_config", user_id, "settings", {})
            return payload if isinstance(payload, dict) else {}
        path = self._path(user_id)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save(self, user_id: str, payload: dict[str, Any]) -> None:
        if self._use_database:
            save_document("llm_config", user_id, "settings", payload)
            return
        path = self._path(user_id)
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

    def _encrypt(self, api_key: str) -> str:
        return self._cipher.encrypt(api_key.encode("utf-8")).decode("ascii")

    def _decrypt(self, encrypted_api_key: str) -> str:
        try:
            return self._cipher.decrypt(encrypted_api_key.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError, ValueError) as exc:
            raise ValueError("个人 API 密钥无法解密，请重新保存") from exc

    def public_settings(self, user_id: str) -> dict[str, Any]:
        payload = self._load(user_id)
        if not payload:
            return {
                "source": "server",
                "provider": "server",
                "base_url": "",
                "model": "",
                "has_api_key": False,
                "presets": public_provider_presets(),
            }
        return {
            "source": "personal",
            "provider": str(payload.get("provider", "custom")),
            "base_url": str(payload.get("base_url", "")),
            "model": str(payload.get("model", "")),
            "has_api_key": bool(payload.get("encrypted_api_key")),
            "presets": public_provider_presets(),
        }

    def save_settings(self, user_id: str, values: dict[str, Any]) -> dict[str, Any]:
        provider = str(values.get("provider", "")).strip().lower()
        if provider == "server":
            self.clear_settings(user_id)
            return self.public_settings(user_id)

        normalized = normalize_provider_config(
            provider,
            values.get("base_url", ""),
            values.get("model", ""),
        )
        existing = self._load(user_id)
        api_key = str(values.get("api_key", "")).strip()
        if len(api_key) > 2048 or any(character.isspace() for character in api_key):
            raise ValueError("API Key 格式不正确")
        encrypted_api_key = (
            self._encrypt(api_key)
            if api_key
            else str(existing.get("encrypted_api_key", ""))
        )
        if not encrypted_api_key:
            raise ValueError("请填写该账号自己的 API Key")

        payload = {
            "version": 1,
            **normalized,
            "encrypted_api_key": encrypted_api_key,
        }
        with self._lock:
            self._save(user_id, payload)
            self._clients.pop(user_id, None)
        return self.public_settings(user_id)

    def clear_settings(self, user_id: str) -> None:
        with self._lock:
            if self._use_database:
                delete_document("llm_config", user_id, "settings")
            else:
                path = self._path(user_id)
                if path.exists():
                    path.unlink()
            self._clients.pop(user_id, None)

    def get_client(self, user_id: str, server_default: LLMClient) -> LLMClient:
        payload = self._load(user_id)
        if not payload:
            return server_default
        with self._lock:
            cached = self._clients.get(user_id)
            if cached is not None:
                return cached
            api_key = self._decrypt(str(payload.get("encrypted_api_key", "")))
            client = LLMClient({
                "provider": payload.get("provider", "custom"),
                "base_url": payload.get("base_url", ""),
                "model": payload.get("model", ""),
                "vision_model": payload.get("model", ""),
                "display_name": payload.get("display_name", ""),
                "api_key": api_key,
            })
            self._clients[user_id] = client
            return client
