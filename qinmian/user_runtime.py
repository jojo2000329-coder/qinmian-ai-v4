"""Persistent per-user state for mutable academic tools."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .auth_store import user_data_path
from .data_store import QinmianDataStore


class UserRuntimeStoreManager:
    """Give each user isolated seat watchers, events, and simulated inventory."""

    def __init__(self, base_store: QinmianDataStore) -> None:
        self.base_store = base_store
        self._stores: dict[str, QinmianDataStore] = {}
        self._lock = threading.RLock()

    def _state_path(self, user_id: str) -> Path:
        return user_data_path(user_id) / "runtime_state.json"

    def get(self, user_id: str) -> QinmianDataStore:
        with self._lock:
            existing = self._stores.get(user_id)
            if existing is not None:
                return existing

            store = copy.copy(self.base_store)
            state_path = self._state_path(user_id)
            payload: dict[str, Any] = {}
            if state_path.exists():
                try:
                    loaded = json.loads(state_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        payload = loaded
                except (json.JSONDecodeError, OSError):
                    payload = {}

            offerings = payload.get("offerings")
            store.seat_doc = {
                "offerings": copy.deepcopy(
                    offerings
                    if isinstance(offerings, list)
                    else self.base_store.seat_doc.get("offerings", [])
                )
            }
            store.watchers = copy.deepcopy(
                payload.get("watchers") if isinstance(payload.get("watchers"), list) else []
            )
            store.events = copy.deepcopy(
                payload.get("events") if isinstance(payload.get("events"), list) else []
            )
            self._stores[user_id] = store
            return store

    def save(self, user_id: str) -> None:
        with self._lock:
            store = self.get(user_id)
            state_path = self._state_path(user_id)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "offerings": store.seat_doc.get("offerings", []),
                "watchers": store.watchers,
                "events": store.events[-100:],
            }
            temp_name = ""
            try:
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    delete=False,
                    dir=state_path.parent,
                    prefix=f".{state_path.name}.",
                    suffix=".tmp",
                ) as temp_file:
                    json.dump(payload, temp_file, ensure_ascii=False, indent=2)
                    temp_name = temp_file.name
                os.replace(temp_name, state_path)
            finally:
                if temp_name:
                    temp_path = Path(temp_name)
                    if temp_path.exists():
                        temp_path.unlink()
