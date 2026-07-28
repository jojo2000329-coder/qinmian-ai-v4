"""Small JSON document store backed by PostgreSQL when DATABASE_URL is set."""

from __future__ import annotations

import copy
import os
import threading
from typing import Any


_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False


def database_enabled() -> bool:
    """Return whether cloud database persistence is configured."""
    return bool(_DATABASE_URL)


def _connect():
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - only possible in a misbuilt image
        raise RuntimeError(
            "DATABASE_URL is configured but psycopg is not installed"
        ) from exc
    return psycopg.connect(_DATABASE_URL, connect_timeout=10)


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        with _connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS qinmian_documents (
                        namespace TEXT NOT NULL,
                        owner_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (namespace, owner_id, document_id)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS qinmian_documents_owner_updated_idx
                    ON qinmian_documents (namespace, owner_id, updated_at DESC)
                    """
                )
        _SCHEMA_READY = True


def load_document(
    namespace: str,
    owner_id: str,
    document_id: str,
    default: Any = None,
) -> Any:
    """Load one JSON-compatible document."""
    _ensure_schema()
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload
                FROM qinmian_documents
                WHERE namespace = %s AND owner_id = %s AND document_id = %s
                """,
                (namespace, owner_id, document_id),
            )
            row = cursor.fetchone()
    return copy.deepcopy(default) if row is None else row[0]


def save_document(
    namespace: str,
    owner_id: str,
    document_id: str,
    payload: Any,
) -> None:
    """Insert or replace one JSON-compatible document."""
    _ensure_schema()
    from psycopg.types.json import Jsonb

    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO qinmian_documents
                    (namespace, owner_id, document_id, payload, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (namespace, owner_id, document_id)
                DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (namespace, owner_id, document_id, Jsonb(payload)),
            )


def delete_document(namespace: str, owner_id: str, document_id: str) -> bool:
    """Delete one document and report whether it existed."""
    _ensure_schema()
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM qinmian_documents
                WHERE namespace = %s AND owner_id = %s AND document_id = %s
                """,
                (namespace, owner_id, document_id),
            )
            deleted = cursor.rowcount > 0
    return deleted


def delete_owner_documents(owner_id: str) -> int:
    """Delete every private document owned by one account."""
    _ensure_schema()
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM qinmian_documents
                WHERE owner_id = %s
                """,
                (owner_id,),
            )
            return max(0, cursor.rowcount)


def list_documents(namespace: str, owner_id: str, limit: int = 500) -> list[Any]:
    """List an owner's documents from newest to oldest."""
    _ensure_schema()
    effective_limit = max(0, min(int(limit), 500))
    if effective_limit == 0:
        return []
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload
                FROM qinmian_documents
                WHERE namespace = %s AND owner_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (namespace, owner_id, effective_limit),
            )
            rows = cursor.fetchall()
    return [row[0] for row in rows]
