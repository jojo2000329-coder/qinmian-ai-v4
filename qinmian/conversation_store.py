"""
对话持久化存储 (ConversationStore)
==================================
将对话（会话）保存为 JSON 文件，支持：
- 创建新会话
- 列出所有会话（含摘要）
- 获取单条会话完整内容
- 删除会话
- 追加消息到已有会话
- 为会话生成标题摘要

所有数据保存在 data/conversations/ 目录下。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .auth_store import LEGACY_CONVERSATIONS_DIR, user_data_path

CONVERSATIONS_DIR = LEGACY_CONVERSATIONS_DIR
_CONVERSATION_ID_RE = re.compile(r"^[a-f0-9]{12}$")
_LOCK = threading.RLock()

# ── 关键词提取：从问题中提炼标题 ─────────────────────────────

# 停用词（不进入标题的常见提问词）
_STOPWORDS = {
    "请问", "我想", "帮我", "查一下", "看看", "怎么", "如何", "什么",
    "这个", "那个", "一个", "可以", "能", "要", "会", "没有", "吗",
    "呢", "啊", "吧", "的", "了", "是", "在", "有", "和", "就", "我",
    "你", "他", "她", "它", "们", "那", "哪", "谁", "几", "很", "太",
    "比较", "一些", "有点", "一下", "知道", "告诉", "介绍", "推荐",
    "解释", "说明", "列表", "生成", "创建", "开始", "进行",
}

# 关键名词后缀（这些词附近的信息值得保留）
_KEY_NOUNS = {
    "专业", "课程", "老师", "教师", "教授", "学院", "学校",
    "学分", "课表", "学位", "方向", "岗位", "职业", "就业",
    "难度", "评价", "作业", "考试", "考研", "实习",
    "算法", "数据", "软件", "硬件", "网络", "安全", "智能",
    "工程", "科学", "技术", "设计", "艺术", "管理", "金融",
    "经济", "法学", "文学", "医学", "教育",
}


def _extract_title(message: str, max_len: int = 24) -> str:
    """从用户第一条消息中提取关键信息作为对话标题"""
    msg = message.strip()
    if not msg:
        return "新对话"

    # 1. 消息较短直接使用
    if len(msg) <= max_len:
        return msg

    # 2. 按标点切分取第一句
    first_sent = re.split(r"[。！？\n;；]", msg)[0].strip()

    # 3. 从第一句中提取最佳关键词短语
    #    构建多字关键词（优先匹配更长的专业词汇组合）
    long_keywords = sorted(_KEY_NOUNS, key=len, reverse=True)

    best = {"phrase": "", "start": 999, "quality": 0}

    for kw in long_keywords:
        idx = first_sent.find(kw)
        if idx == -1:
            continue
        # 取关键词及其前 3 后 2 字作为短语
        start = max(0, idx - 3)
        end = min(len(first_sent), idx + len(kw) + 3)
        phrase = first_sent[start:end].strip("，, ")
        # 去掉开头可能的停用词
        for sw in sorted(_STOPWORDS, key=len, reverse=True):
            if phrase.startswith(sw):
                phrase = phrase[len(sw):].strip()
                break
        # 质量评分：靠前 + 短语完整度
        quality = (100 - idx) + len(phrase) * 2
        if quality > best["quality"]:
            best = {"phrase": phrase, "start": idx, "quality": quality}

    if best["phrase"]:
        result = best["phrase"]
        if len(result) > max_len:
            # 如果太长，截断到关键词为止
            kw_end = best["start"] + len(best["phrase"])
            result = first_sent[best["start"]:kw_end]
        if len(result) > max_len:
            result = result[:max_len] + "…"
        return result if result.strip() else first_sent[:max_len] + "…"

    # 4. 无关键词命中：去掉开头的停用词和语气词
    cleaned = first_sent
    for word in sorted(_STOPWORDS, key=len, reverse=True):
        if cleaned.startswith(word):
            cleaned = cleaned[len(word):].strip()
            break
    for word in ("吗", "呢", "啊", "吧", "的"):
        if cleaned.endswith(word) and len(cleaned) > len(word) + 2:
            cleaned = cleaned[:-len(word)].strip()

    if cleaned and len(cleaned) <= max_len:
        return cleaned
    if cleaned:
        return cleaned[:max_len] + "…"

    return first_sent[:max_len] + ("…" if len(first_sent) > max_len else "")


def _conversations_dir(user_id: str) -> Path:
    if user_id == "legacy":
        return CONVERSATIONS_DIR
    return user_data_path(user_id) / "conversations"


def _ensure_dir(user_id: str) -> Path:
    path = _conversations_dir(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _conv_path(conv_id: str, user_id: str) -> Path | None:
    if not _CONVERSATION_ID_RE.fullmatch(str(conv_id or "")):
        return None
    return _ensure_dir(user_id) / f"{conv_id}.json"


def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _list_files(user_id: str) -> list[Path]:
    directory = _ensure_dir(user_id)
    return sorted(directory.glob("*.json"), key=os.path.getmtime, reverse=True)


def _write_conversation(path: Path, payload: dict[str, Any]) -> None:
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


def create_conversation(title: str = "", user_id: str = "legacy") -> dict[str, Any]:
    """创建新会话，返回会话对象"""
    with _LOCK:
        directory = _ensure_dir(user_id)
        conv_id = uuid.uuid4().hex[:12]
        now = _timestamp()
        conv = {
            "id": conv_id,
            "title": str(title or "")[:80] or f"对话 {now}",
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
            "messages": [],
        }
        _write_conversation(directory / f"{conv_id}.json", conv)
        return conv


def list_conversations(limit: int = 50, user_id: str = "legacy") -> list[dict[str, Any]]:
    """列出所有会话摘要（不含完整消息）"""
    effective_limit = max(0, min(limit, 500))
    if effective_limit == 0:
        return []
    result = []
    with _LOCK:
        for path in _list_files(user_id):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                result.append({
                    "id": data.get("id", path.stem),
                    "title": data.get("title", "未命名对话"),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "message_count": data.get("message_count", 0),
                })
            except (json.JSONDecodeError, OSError):
                continue
            if len(result) >= effective_limit:
                break
    return result


def get_conversation(conv_id: str, user_id: str = "legacy") -> dict[str, Any] | None:
    """获取单条会话完整内容"""
    path = _conv_path(conv_id, user_id)
    if path is None or not path.exists():
        return None
    with _LOCK:
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None


def delete_conversation(conv_id: str, user_id: str = "legacy") -> bool:
    """删除会话"""
    path = _conv_path(conv_id, user_id)
    if path is None or not path.exists():
        return False
    with _LOCK:
        path.unlink()
        return True


def rename_conversation(
    conv_id: str,
    new_title: str,
    user_id: str = "legacy",
) -> dict[str, Any] | None:
    """重命名会话"""
    with _LOCK:
        conv = get_conversation(conv_id, user_id)
        path = _conv_path(conv_id, user_id)
        if not conv or path is None:
            return None
        conv["title"] = str(new_title)[:80]
        conv["updated_at"] = _timestamp()
        _write_conversation(path, conv)
        return conv


def delete_message(
    conv_id: str,
    msg_index: int,
    user_id: str = "legacy",
) -> dict[str, Any] | None:
    """删除会话中的单条消息"""
    with _LOCK:
        conv = get_conversation(conv_id, user_id)
        path = _conv_path(conv_id, user_id)
        if not conv or path is None:
            return None
        messages = conv.get("messages", [])
        if msg_index < 0 or msg_index >= len(messages):
            return None
        del messages[msg_index]
        conv["messages"] = messages
        conv["message_count"] = len(messages)
        conv["updated_at"] = _timestamp()
        _write_conversation(path, conv)
        return conv


def add_message(
    conv_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    user_id: str = "legacy",
) -> dict[str, Any] | None:
    """向已有会话追加一条消息"""
    with _LOCK:
        conv = get_conversation(conv_id, user_id)
        path = _conv_path(conv_id, user_id)
        if not conv or path is None:
            return None
        now = _timestamp()
        message = {
            "role": role if role in {"user", "assistant", "system"} else "user",
            "content": str(content),
            "timestamp": now,
            "metadata": metadata or {},
        }
        conv.setdefault("messages", []).append(message)
        conv["message_count"] = len(conv["messages"])
        conv["updated_at"] = now

        # 自动生成标题：从第一条用户消息中提取关键信息
        if conv["message_count"] == 1 and role == "user":
            conv["title"] = _extract_title(str(content))

        _write_conversation(path, conv)
        return conv


def get_or_create_active(
    active_id: str | None = None,
    user_id: str = "legacy",
) -> dict[str, Any]:
    """获取当前活跃会话，不存在则创建"""
    if active_id:
        conv = get_conversation(active_id, user_id)
        if conv:
            return conv
    return create_conversation(user_id=user_id)
