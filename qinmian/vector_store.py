"""
向量存储模块：基于向量的语义检索。

支持：
- 添加文本并自动向量化
- 余弦相似度语义搜索
- JSON 持久化存储与加载
- 按对话 ID 过滤（对话隔离）
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .embeddings import cosine_similarity, embed, local_embed


class VectorStore:
    """轻量级向量存储，支持语义检索"""

    def __init__(self, store_path: str | Path | None = None):
        self.vectors: list[dict[str, Any]] = []  # [{id, text, vector, metadata, timestamp}, ...]
        self.store_path = Path(store_path) if store_path else None

    # ── 核心操作 ─────────────────────────────────────────

    def add(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
    ) -> dict[str, Any]:
        """添加一条文本到向量库"""
        vector = embed(text)
        if doc_id is None:
            doc_id = f"vec-{int(time.time() * 1000)}-{len(self.vectors)}"
        record = {
            "id": doc_id,
            "text": text,
            "vector": vector,
            "metadata": metadata or {},
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.vectors.append(record)
        return record

    def upsert(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        doc_id: str | None = None,
        local_only: bool = False,
    ) -> dict[str, Any]:
        """Insert or replace a deterministic document ID."""
        if not doc_id:
            return self.add(text=text, metadata=metadata)
        vector = local_embed(text) if local_only else embed(text)
        record = {
            "id": doc_id,
            "text": text,
            "vector": vector,
            "metadata": metadata or {},
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for index, existing in enumerate(self.vectors):
            if existing.get("id") == doc_id:
                self.vectors[index] = record
                return record
        self.vectors.append(record)
        return record

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        语义搜索：查询文本 → 向量化 → 余弦相似度排序

        参数：
            query: 查询文本
            top_k: 返回 top N 结果
            min_score: 最低相似度阈值
            filter_metadata: 元数据过滤条件（如 {"conversation_id": "xxx"}）
        """
        query_vec = embed(query)
        scored = []

        for record in self.vectors:
            # 元数据过滤
            if filter_metadata:
                meta = record.get("metadata", {})
                matched = True
                for key, val in filter_metadata.items():
                    if meta.get(key) != val:
                        matched = False
                        break
                if not matched:
                    continue

            score = cosine_similarity(query_vec, record["vector"])
            if score >= min_score:
                scored.append((score, record))

        # 按相似度降序排列
        scored.sort(key=lambda x: -x[0])
        return [
            {
                "id": rec["id"],
                "text": rec["text"],
                "score": round(score, 4),
                "metadata": rec.get("metadata", {}),
                "timestamp": rec.get("timestamp", ""),
            }
            for score, rec in scored[:top_k]
        ]

    def delete(self, doc_id: str) -> bool:
        """按 ID 删除记录"""
        before = len(self.vectors)
        self.vectors = [v for v in self.vectors if v.get("id") != doc_id]
        return len(self.vectors) < before

    def delete_by_metadata(self, key: str, value: Any) -> int:
        """按元数据条件删除（如删除某个对话的所有记忆）"""
        before = len(self.vectors)
        self.vectors = [
            v for v in self.vectors if v.get("metadata", {}).get(key) != value
        ]
        return before - len(self.vectors)

    def clear(self) -> int:
        """清空所有向量"""
        count = len(self.vectors)
        self.vectors.clear()
        return count

    def count(self) -> int:
        return len(self.vectors)

    # ── 持久化 ─────────────────────────────────────────

    def save(self, path: str | Path | None = None) -> None:
        """保存到 JSON 文件"""
        save_path = Path(path) if path else self.store_path
        if not save_path:
            raise ValueError("No save path specified")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        # 保存时去掉 vector 字段以减小体积（可选）或保留
        payload = {
            "version": 2,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "records": self.vectors,
        }
        temp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                delete=False,
                dir=save_path.parent,
                prefix=f".{save_path.name}.",
                suffix=".tmp",
            ) as temp_file:
                json.dump(payload, temp_file, ensure_ascii=False, indent=2)
                temp_name = temp_file.name
            os.replace(temp_name, save_path)
        finally:
            if temp_name:
                temp_path = Path(temp_name)
                if temp_path.exists():
                    temp_path.unlink()

    def load(self, path: str | Path | None = None) -> int:
        """从 JSON 文件加载"""
        load_path = Path(path) if path else self.store_path
        if not load_path or not load_path.exists():
            return 0
        with load_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        self.vectors = payload.get("records", [])
        if payload.get("version", 1) < 2:
            for record in self.vectors:
                record["vector"] = local_embed(record.get("text", ""))
        return len(self.vectors)
