"""
向量化模块：将文本转换为向量（embedding）。

支持两种方式：
1. 本地 n-gram 向量化（无需外部依赖）
2. API 嵌入（调用 OpenAI-compatible /v1/embeddings 端点，如 DeepSeek）

优先使用 API 嵌入，不可用时自动降级为本地向量化。
"""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


# ── 本地 n-gram 向量化 ──────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """将文本拆分为 token 列表：英文词 + 中文 uni/bi/tri-gram"""
    lowered = text.lower()
    words = re.findall(r"[a-z0-9_+#.-]+", lowered)
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    grams: list[str] = []
    for chunk in chinese:
        if len(chunk) == 1:
            grams.append(chunk)
        else:
            # 添加 bi-gram 和 tri-gram
            grams.extend(chunk[i : i + 2] for i in range(len(chunk) - 1))
            grams.extend(chunk[i : i + 3] for i in range(len(chunk) - 2))
            grams.append(chunk)  # 全词
    return words + grams


def local_embed(text: str, dim: int = 256) -> list[float]:
    """
    本地 n-gram 向量化。
    使用特征哈希（feature hashing）将 token 映射到固定维度向量。
    """
    tokens = _tokenize(text)
    vec = [0.0] * dim
    for token in tokens:
        # Python's built-in hash is randomized between processes, which makes
        # persisted vectors invalid after a restart. Use a stable digest.
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        h = int.from_bytes(digest, "big") % dim
        vec[h] += 1.0
    # L2 归一化
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


# ── API 嵌入 ────────────────────────────────────────────────

def _load_llm_config() -> dict[str, str]:
    """读取 LLM 配置，获取 API Key 和 base_url"""
    data_dir = Path(__file__).resolve().parents[1] / "data"
    config: dict[str, Any] = {}
    for filename in ("llm_config.json", "llm_config.local.json"):
        config_path = data_dir / filename
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as f:
                config.update(json.load(f))
    return config


def api_embed(text: str) -> list[float] | None:
    """调用 OpenAI-compatible /v1/embeddings API 获取向量"""
    config = _load_llm_config()
    api_key = (
        os.getenv("QINMIAN_LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or config.get("api_key", "")
    )
    base_url = os.getenv("QINMIAN_LLM_BASE_URL") or config.get("base_url", "")
    model = os.getenv("QINMIAN_EMBEDDING_MODEL") or config.get("embedding_model", "text-embedding-3-small")
    enabled = str(
        os.getenv("QINMIAN_EMBEDDING_ENABLED", config.get("embedding_enabled", "0"))
    ).lower() in {"1", "true", "yes", "on"}

    if not enabled or not api_key or not base_url:
        return None

    # 尝试多个可能的 embedding 端点路径
    urls_to_try = [
        f"{base_url.rstrip('/')}/embeddings",
        f"{base_url.rstrip('/')}/v1/embeddings",
    ]

    payload = json.dumps({
        "model": model,
        "input": text,
    }).encode("utf-8")

    req_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    for url in urls_to_try:
        try:
            req = urllib.request.Request(url, data=payload, headers=req_headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if "data" in result and len(result["data"]) > 0:
                    return result["data"][0].get("embedding")
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, OSError):
            continue
    return None


# ── 统一接口 ────────────────────────────────────────────────

def embed(text: str, dim: int = 256) -> list[float]:
    """
    统一 embedding 接口。
    优先使用 API 嵌入，失败时降级为本地向量化。
    """
    # 尝试 API 嵌入
    api_result = api_embed(text)
    if api_result is not None:
        return api_result
    # 降级：本地向量化
    return local_embed(text, dim=dim)


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """计算两个向量之间的余弦相似度"""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
