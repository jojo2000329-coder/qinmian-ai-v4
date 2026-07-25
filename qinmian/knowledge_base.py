"""
知识库与长期记忆系统 (KnowledgeBase)
=====================================
提供基于向量语义检索的「长期记忆」存储与检索。

核心能力：
1. 对话存储：将每轮对话存入向量库
2. 语义检索：基于向量相似度的语义搜索（非关键词匹配）
3. 记忆召回：自动召回相关历史记忆并注入上下文
4. 知识库开关：API 可控制启用/禁用

数据存储：
- data/knowledge_base/records.json：向量库持久化文件（含向量数据）
- 降级兼容旧版关键词格式
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .vector_store import VectorStore


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "data" / "knowledge_base"
KNOWLEDGE_FILE = KNOWLEDGE_DIR / "records.json"


def _tokenize(text: str) -> list[str]:
    """简易分词：英文单词 + 中文二元/三元组"""
    lowered = text.lower()
    words = re.findall(r"[a-z0-9_+#.-]+", lowered)
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    grams: list[str] = []
    for chunk in chinese:
        if len(chunk) == 1:
            grams.append(chunk)
        else:
            grams.extend(chunk[i: i + 2] for i in range(len(chunk) - 1))
            grams.extend(chunk[i: i + 3] for i in range(max(0, len(chunk) - 2)))
    return words + grams


def _timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class KnowledgeBase:
    """
    长期记忆知识库（基于向量语义检索）。

    用法：
        kb = KnowledgeBase()
        kb.store("用户问题", "助手回答", "conv_abc123", {"意图": "course_hardness"})
        results = kb.search("数据结构难吗", top_k=5)
        context = kb.get_relevant_context("机器学习", max_items=3)
    """

    def __init__(self, store_path: str | Path | None = None) -> None:
        self._enabled: bool = True
        self._knowledge_file = Path(store_path) if store_path else KNOWLEDGE_FILE
        self._vector_store = VectorStore(self._knowledge_file)
        self._lock = threading.RLock()
        self._load()

    # ── 开关控制 ────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value

    def status(self) -> dict[str, Any]:
        domain_records = [
            record for record in self._vector_store.vectors
            if record.get("metadata", {}).get("source") == "major_catalog"
        ]
        major_ids = {
            record.get("metadata", {}).get("major_id")
            for record in domain_records
            if record.get("metadata", {}).get("major_id")
        }
        return {
            "enabled": self._enabled,
            "total_records": self._vector_store.count(),
            "domain_records": len(domain_records),
            "conversation_records": self._vector_store.count() - len(domain_records),
            "majors_indexed": len(major_ids),
            "major_aspects": sorted({
                record.get("metadata", {}).get("aspect", "")
                for record in domain_records
                if record.get("metadata", {}).get("aspect")
            }),
            "storage_path": str(self._knowledge_file),
        }

    # ── 持久化 ──────────────────────────────────────────────────

    def _load(self) -> None:
        self._knowledge_file.parent.mkdir(parents=True, exist_ok=True)
        if self._knowledge_file.exists():
            try:
                self._vector_store.load(self._knowledge_file)
            except Exception:
                self._vector_store = VectorStore(self._knowledge_file)

    def _save(self) -> None:
        self._knowledge_file.parent.mkdir(parents=True, exist_ok=True)
        self._vector_store.save(self._knowledge_file)

    def index_major_catalog(self, store: Any) -> dict[str, Any]:
        """Build searchable knowledge documents for every configured major."""
        with self._lock:
            return self._index_major_catalog_unlocked(store)

    def _index_major_catalog_unlocked(self, store: Any) -> dict[str, Any]:
        revision_payload = json.dumps(
            [store.majors_doc, store.curriculum_doc, store.graduation_credit_doc],
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        catalog_revision = hashlib.sha256(revision_payload).hexdigest()[:16]
        existing_domain = [
            record for record in self._vector_store.vectors
            if record.get("metadata", {}).get("source") == "major_catalog"
        ]
        existing_major_ids = {
            record.get("metadata", {}).get("major_id") for record in existing_domain
        }
        if (
            existing_domain
            and existing_major_ids == {major["id"] for major in store.majors}
            and all(
                record.get("metadata", {}).get("catalog_revision") == catalog_revision
                for record in existing_domain
            )
        ):
            result = self.status()
            result.update({"total_majors": len(store.majors), "coverage_complete": True})
            return result

        desired_ids: set[str] = set()

        for major in store.majors:
            major_id = major["id"]
            major_name = major.get("display_name") or major.get("name", "")
            base_metadata = {
                "source": "major_catalog",
                "major_id": major_id,
                "major_name": major_name,
                "college": major.get("college", ""),
                "campus": major.get("campus", ""),
                "catalog_revision": catalog_revision,
            }

            overview_id = f"major-{major_id}-overview"
            desired_ids.add(overview_id)
            overview = "\n".join([
                f"专业名称：{major_name}",
                f"所属学院：{major.get('college', '')}",
                f"校区：{major.get('campus', '')}",
                f"学科方向：{major.get('discipline', '')}",
                f"专业方向：{'、'.join(major.get('streams', [])) or '未分流'}",
                f"相关学院：{'、'.join(major.get('related_colleges', [])) or '无'}",
                f"专业认证：{major.get('accredited') or '暂无标注'}",
                f"学费组：{major.get('tuition_group', '')}",
            ])
            self._vector_store.upsert(
                overview,
                {**base_metadata, "aspect": "overview"},
                overview_id,
                local_only=True,
            )

            domestic = store.curriculum_for(major_id, "domestic")
            course_id = f"major-{major_id}-curriculum"
            desired_ids.add(course_id)
            courses = domestic.get("courses", [])
            course_lines = []
            for semester in range(1, 9):
                names = [c.get("name", "") for c in courses if c.get("semester") == semester]
                if names:
                    course_lines.append(f"第{semester}学期：{'、'.join(names)}")
            course_text = "\n".join([
                f"{major_name}培养方案与课程结构",
                f"课程类别模板学分：{json.dumps(domestic.get('category_template_credits', {}), ensure_ascii=False)}",
                *course_lines,
            ])
            self._vector_store.upsert(
                course_text,
                {**base_metadata, "aspect": "curriculum"},
                course_id,
                local_only=True,
            )

            for student_type, label in (("domestic", "境内生"), ("international", "境外生")):
                curriculum = store.curriculum_for(major_id, student_type)
                if student_type == "international" and not curriculum.get("available_student_types", {}).get("international"):
                    continue
                credit_id = f"major-{major_id}-credits-{student_type}"
                desired_ids.add(credit_id)
                rule = curriculum.get("credit_rule", {})
                credit_text = "\n".join([
                    f"{major_name}{label}毕业学分要求",
                    f"总学分：{rule.get('graduation_total', rule.get('total', '以教务数据为准'))}",
                    f"学分规则：{json.dumps(rule, ensure_ascii=False)}",
                    f"必修课示例：{'、'.join(c.get('name', '') for c in curriculum.get('first_required_courses', []))}",
                    f"推荐选修课：{'、'.join(c.get('name', '') for c in curriculum.get('recommended_electives', []))}",
                ])
                self._vector_store.upsert(
                    credit_text,
                    {**base_metadata, "aspect": "credits", "student_type": student_type},
                    credit_id,
                    local_only=True,
                )

        self._vector_store.vectors = [
            record for record in self._vector_store.vectors
            if record.get("metadata", {}).get("source") != "major_catalog"
            or record.get("id") in desired_ids
        ]
        self._save()
        result = self.status()
        result["total_majors"] = len(store.majors)
        result["coverage_complete"] = result["majors_indexed"] == len(store.majors)
        return result

    # ── 存储 ────────────────────────────────────────────────────

    def store(
        self,
        user_message: str,
        assistant_answer: str,
        conversation_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        将一轮对话存入知识库（长期记忆）。

        参数:
            user_message: 用户消息
            assistant_answer: 助手回答
            conversation_id: 所属会话ID
            metadata: 额外元数据（意图、专业、课程等）

        返回:
            创建的知识条目
        """
        if not self._enabled:
            return {"status": "disabled"}

        with self._lock:
            combined = f"用户：{user_message}\n助手：{assistant_answer}"
            record_metadata = {
                "conversation_id": conversation_id,
                **(metadata or {}),
            }

            doc_id = f"mem-{int(time.time() * 1000000)}"

            self._vector_store.add(
                text=combined,
                metadata=record_metadata,
                doc_id=doc_id,
            )

            self._save()

        return {
            "id": doc_id,
            "user_message": user_message[:500],
            "assistant_answer": assistant_answer[:1000],
            "conversation_id": conversation_id,
            "metadata": metadata or {},
            "created_at": _timestamp(),
        }

    def store_conversation_summary(
        self,
        conv_id: str,
        messages: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        将会话中的多轮对话批量存入知识库。
        每轮对话生成一条记忆记录。
        """
        if not self._enabled:
            return []
        created = []
        for i in range(0, len(messages) - 1, 2):
            user_msg = messages[i] if i < len(messages) and messages[i].get("role") == "user" else None
            asst_msg = messages[i + 1] if i + 1 < len(messages) and messages[i + 1].get("role") == "assistant" else None
            if user_msg and asst_msg:
                record = self.store(
                    user_message=user_msg.get("content", ""),
                    assistant_answer=asst_msg.get("content", ""),
                    conversation_id=conv_id,
                    metadata=metadata,
                )
                created.append(record)
        return created

    # ── 检索 ────────────────────────────────────────────────────

    def _keyword_score(self, query: str, text: str) -> float:
        """
        基于 n-gram 关键词重叠的评分。

        评分逻辑：
        - 只对 query 部分（"用户：..."）评分，忽略回答部分
        - 对 n-gram 做 TF 加权（高频词降权）
        - 精确子串匹配加成
        - 最终值范围 0~1，0.3 以上为强相关，0.15~0.3 为中等，0.05~0.15 为弱相关
        """
        # 只取用户问题部分（"用户：..." 之后的内容）
        q_part = query
        t_part = text
        if "用户：" in text and "助手：" in text:
            t_part = text.split("用户：")[1].split("\n")[0] if "\n" in text.split("用户：")[1] else text.split("用户：")[1]
        if "助手：" in t_part:
            t_part = t_part.split("助手：")[0]

        q_tokens = _tokenize(q_part)
        t_tokens = _tokenize(t_part)

        if not q_tokens or not t_tokens:
            return 0.0

        # 精确子串匹配加分
        exact_bonus = 1.5 if q_part.strip() in t_part else 1.0

        # TF 加权：长 token 更有价值（通常是完整词汇）
        from collections import Counter
        q_count = Counter(q_tokens)
        t_count = Counter(t_tokens)

        q_set = set(q_tokens)
        t_set = set(t_tokens)
        overlap = q_set & t_set

        if not overlap:
            return 0.0

        # 加权 F1-score：长 token 权重更高
        q_weight = sum(1.0 + len(t) * 0.1 for t in q_set)
        t_weight = sum(1.0 + len(t) * 0.1 for t in t_set)
        overlap_weight = sum(1.0 + len(t) * 0.1 for t in overlap)

        recall = overlap_weight / q_weight if q_weight > 0 else 0
        precision = overlap_weight / t_weight if t_weight > 0 else 0

        if recall + precision == 0:
            return 0.0
        f1 = 2 * recall * precision / (recall + precision)
        return round(min(f1 * exact_bonus, 0.95), 4)

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        混合检索：关键词评分（主要）+ 向量语义（辅助）。
        返回按相似度降序排列的记忆条目。
        """
        if not self._enabled:
            return []

        with self._lock:
            # 1. 关键词评分（对所有记录）
            scored = []
            for record in self._vector_store.vectors:
                text = record.get("text", "")
                kw_score = self._keyword_score(query, text)
                metadata = record.get("metadata", {})
                if metadata.get("source") == "major_catalog":
                    major_name = str(metadata.get("major_name", ""))
                    aspect = metadata.get("aspect", "")
                    if major_name and major_name in query:
                        kw_score += 0.55
                    if aspect == "credits" and any(word in query for word in ("学分", "毕业", "要求")):
                        kw_score += 0.3
                    elif aspect == "curriculum" and any(word in query for word in ("课程", "课表", "培养方案", "学什么")):
                        kw_score += 0.3
                    elif aspect == "overview" and any(word in query for word in ("介绍", "学院", "校区", "方向", "专业")):
                        kw_score += 0.2
                    kw_score = min(kw_score, 1.5)
                if kw_score > 0:
                    scored.append((kw_score, record))

            # 2. 向量语义补充（当关键词结果不足时）
            if len(scored) < top_k:
                vec_results = self._vector_store.search(query, top_k=top_k*2, min_score=0.0)
                seen_ids = {r.get("id") for _, r in scored}
                for vr in vec_results:
                    if vr["id"] not in seen_ids and vr["score"] > 0:
                        scored.append((vr["score"] * 0.5, {"id": vr["id"], "text": vr["text"], "metadata": vr["metadata"], "timestamp": vr.get("timestamp", "")}))
                        seen_ids.add(vr["id"])

            # 3. 排序返回
            scored.sort(key=lambda x: -x[0])
            results = []
            for score, record in scored[:top_k]:
                text = record.get("text", "")
                results.append({
                    "score": round(score, 4),
                    "text": text,
                    "user_message": text.split("\n")[0].replace("用户：", "")[:200] if "用户：" in text else "",
                    "assistant_answer": text.split("助手：")[-1][:300] if "助手：" in text else text[:300],
                    "conversation_id": record.get("metadata", {}).get("conversation_id", ""),
                    "metadata": record.get("metadata", {}),
                    "created_at": record.get("timestamp", ""),
                })
            return results

    def get_relevant_context(
        self,
        query: str,
        max_items: int = 3,
        conversation_id: str | None = None,
    ) -> str:
        """
        获取与 query 相关的历史记忆，格式化为上下文文本。
        供 Agent 注入系统提示使用。

        参数：
            query: 查询文本
            max_items: 最多返回几条记忆
            conversation_id: 可选，限定某会话内的记忆
        """
        results = self.search(query, top_k=max_items * 3)
        if conversation_id:
            results.sort(
                key=lambda item: (
                    item.get("metadata", {}).get("source") == "major_catalog"
                    or item.get("metadata", {}).get("conversation_id") == conversation_id,
                    item.get("score", 0),
                ),
                reverse=True,
            )
        results = results[:max_items]
        if not results:
            return ""

        parts = ["【以下是与当前问题相关的专业知识与历史记忆】"]
        for i, r in enumerate(results, 1):
            parts.append(
                f"--- 记忆 {i} (相关度: {r['score']}) ---\n"
                f"{r['text'][:500]}"
            )
        return "\n\n".join(parts)

    # ── 管理 ────────────────────────────────────────────────────

    def clear(self) -> int:
        """清空知识库，返回删除的记录数"""
        with self._lock:
            count = self._vector_store.count()
            self._vector_store.clear()
            self._save()
            return count

    def clear_conversation_memories(self) -> int:
        """Delete private conversation memories while preserving the major catalog."""
        with self._lock:
            before = self._vector_store.count()
            self._vector_store.vectors = [
                record for record in self._vector_store.vectors
                if record.get("metadata", {}).get("source") == "major_catalog"
            ]
            deleted = before - self._vector_store.count()
            self._save()
            return deleted

    def delete_conversation_memories(self, conversation_id: str) -> int:
        """Delete all long-term memories owned by one conversation."""
        with self._lock:
            deleted = self._vector_store.delete_by_metadata(
                "conversation_id",
                conversation_id,
            )
            if deleted:
                self._save()
            return deleted

    def all_records(self, limit: int = 100) -> list[dict[str, Any]]:
        """返回所有知识条目（摘要）"""
        with self._lock:
            records = self._vector_store.vectors[:limit]
            return [
                {
                    "id": r.get("id", ""),
                    "text": r.get("text", "")[:200],
                    "conversation_id": r.get("metadata", {}).get("conversation_id", ""),
                    "created_at": r.get("timestamp", ""),
                }
                for r in records
            ]

    def count(self) -> int:
        with self._lock:
            return self._vector_store.count()
