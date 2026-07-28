from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .data_store import QinmianDataStore


WORKLOAD_HIGH = ["作业量偏大", "作业多", "实验多", "任务重", "很肝", "肝", "熬夜", "报告多", "周周"]
WORKLOAD_LOW = ["作业少", "轻松", "水", "负担小"]
GRADING_FRIENDLY = ["给分友好", "给分好", "高分", "不压分", "宽松", "曲线"]
GRADING_STRICT = ["给分低", "压分", "挂科", "严格", "偏严", "不宽松"]
SUBSTANCE_HIGH = ["干货", "扎实", "有用", "收获", "关键", "项目", "提升明显", "作品集收益"]
SUBSTANCE_LOW = ["照本宣科", "空", "无聊", "深度要靠自己", "水"]


def _hits(text: str, words: list[str]) -> int:
    return sum(1 for word in words if word.lower() in text.lower())


def clamp(value: float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, round(value)))


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    words = re.findall(r"[a-z0-9_+#.-]+", lowered)
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    grams: list[str] = []
    for chunk in chinese:
        if len(chunk) == 1:
            grams.append(chunk)
        else:
            grams.extend(chunk[i : i + 2] for i in range(len(chunk) - 1))
            grams.extend(chunk[i : i + 3] for i in range(max(0, len(chunk) - 2)))
    return words + grams


def cosine_similarity(a: str, b: str) -> float:
    vec_a = Counter(tokenize(a))
    vec_b = Counter(tokenize(b))
    if not vec_a or not vec_b:
        return 0.0
    shared = set(vec_a) & set(vec_b)
    numerator = sum(vec_a[t] * vec_b[t] for t in shared)
    denom_a = math.sqrt(sum(v * v for v in vec_a.values()))
    denom_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if denom_a == 0 or denom_b == 0:
        return 0.0
    return numerator / (denom_a * denom_b)


# ═════════════════════════════════════════════════════════════════════
# 课程难度数据库 (CourseDifficultyDB)
# ═════════════════════════════════════════════════════════════════════
# 从 course_difficulty.json 加载预计算的课程难度数据，
# 提供基于多维度评分的星级难度查询。

class CourseDifficultyDB:
    """课程难度数据库——基于教务系统全量数据的多维度难度评分"""

    _instance: CourseDifficultyDB | None = None
    _data: dict[str, Any] | None = None

    def __new__(cls) -> CourseDifficultyDB:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._data is not None:
            return
        self.load()

    def load(self) -> None:
        path = Path(__file__).resolve().parents[1] / "data" / "course_difficulty.json"
        if not path.exists():
            self._data = {"version": "0", "courses": [], "distribution": {"total_courses": 0}}
            return
        with path.open("r", encoding="utf-8") as f:
            self._data = json.load(f)
        # 按课程名索引
        self._by_name: dict[str, dict[str, Any]] = {}
        for c in self._data.get("courses", []):
            self._by_name[c["name"]] = c

    @property
    def is_loaded(self) -> bool:
        return bool(self._data and self._data.get("courses"))

    @property
    def version(self) -> str:
        return (self._data or {}).get("version", "0")

    @property
    def generated_at(self) -> str:
        return (self._data or {}).get("generated_at", "")

    @property
    def distribution(self) -> dict[str, Any]:
        return (self._data or {}).get("distribution", {})

    @property
    def model_info(self) -> dict[str, Any]:
        return (self._data or {}).get("difficulty_model", {})

    def total_courses(self) -> int:
        return self.distribution.get("total_courses", 0)

    def get(self, course_name: str) -> dict[str, Any] | None:
        """按课程名精确查找"""
        return self._by_name.get(course_name)

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """按课程名模糊搜索"""
        q = query.strip().lower()
        if not q:
            return []
        matches = []
        for cname, info in self._by_name.items():
            if q in cname.lower() or cname.lower() in q:
                matches.append(info)
        return matches[:top_k]

    def list_by_stars(self, stars: int) -> list[dict[str, Any]]:
        """按星级筛选"""
        return [c for c in self._data.get("courses", []) if c["stars"] == stars]

    def list_by_difficulty(self, min_score: float = 0, max_score: float = 100) -> list[dict[str, Any]]:
        return [
            c for c in self._data.get("courses", [])
            if min_score <= c["difficulty_score"] <= max_score
        ]

    def top_hardest(self, k: int = 20) -> list[dict[str, Any]]:
        return sorted(
            self._data.get("courses", []),
            key=lambda c: c["difficulty_score"],
            reverse=True,
        )[:k]

    def full_stats(self) -> dict[str, Any]:
        """完整的统计信息，含模型说明"""
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "total_courses": self.total_courses(),
            "distribution": self.distribution,
            "model": self.model_info,
        }

    def for_course_detail(self, course_name: str) -> dict[str, Any]:
        """为课程详情页提供的格式化难度数据"""
        result = self.get(course_name)
        if not result:
            # 模糊搜索
            matches = self.search(course_name, top_k=3)
            if matches:
                result = matches[0]
        if not result:
            return {
                "name": course_name,
                "stars": 0,
                "star_label": "暂无评估",
                "difficulty_score": None,
                "available": False,
            }
        return {
            "name": result["name"],
            "stars": result["stars"],
            "star_label": result["star_label"],
            "star_description": result["star_description"],
            "difficulty_score": result["difficulty_score"],
            "dimensions": result["dimensions"],
            "meta": result["meta"],
            "available": True,
        }


# ═════════════════════════════════════════════════════════════════════
# 原有 CourseHardnessAnalyzer (保留兼容，改为委托模式)
# ═════════════════════════════════════════════════════════════════════

class CourseHardnessAnalyzer:
    def __init__(self, store: QinmianDataStore) -> None:
        self.store = store
        self.difficulty_db = CourseDifficultyDB()

    def analyze(self, course_name: str, extra_reviews: list[str] | None = None) -> dict[str, Any]:
        # 1. 先尝试从难度数据库中获取预计算数据
        db_result = self.difficulty_db.for_course_detail(course_name)
        if db_result.get("available"):
            return self._enrich_with_reviews(course_name, db_result, extra_reviews)

        # 2. 回退：利用现有的评价数据实时分析
        reviews = [
            r
            for r in self.store.reviews_doc["reviews"]
            if course_name.lower() in r["course"].lower() or r["course"].lower() in course_name.lower()
        ]
        if extra_reviews:
            reviews.extend({"course": course_name, "source": "user-input", "text": text, "rating": 0} for text in extra_reviews)
        if not reviews:
            return {
                "course": course_name,
                "review_count": 0,
                "workload": 50,
                "grading_friendliness": 50,
                "substance": 50,
                "hardcore_index": 50,
                "summary": "暂无论坛评价数据，已返回中性估计。可导入论坛抓取结果后重新分析。",
                "evidence": [],
                "difficulty": None,
            }

        workload_scores = []
        grading_scores = []
        substance_scores = []
        evidence = []
        for review in reviews:
            text = review["text"]
            workload = 50 + 18 * _hits(text, WORKLOAD_HIGH) - 15 * _hits(text, WORKLOAD_LOW)
            grading = 50 + 18 * _hits(text, GRADING_FRIENDLY) - 16 * _hits(text, GRADING_STRICT)
            substance = 50 + 18 * _hits(text, SUBSTANCE_HIGH) - 15 * _hits(text, SUBSTANCE_LOW)
            workload_scores.append(clamp(workload))
            grading_scores.append(clamp(grading))
            substance_scores.append(clamp(substance))
            evidence.append(
                {
                    "source": review.get("source", ""),
                    "text": text,
                    "workload": clamp(workload),
                    "grading_friendliness": clamp(grading),
                    "substance": clamp(substance),
                }
            )
        workload = round(sum(workload_scores) / len(workload_scores))
        grading = round(sum(grading_scores) / len(grading_scores))
        substance = round(sum(substance_scores) / len(substance_scores))
        hardcore_index = clamp(workload * 0.45 + (100 - grading) * 0.2 + substance * 0.35)
        summary = (
            f"{course_name} 的作业量指数 {workload}/100，给分友好度 {grading}/100，"
            f"干货程度 {substance}/100，综合硬核指数 {hardcore_index}/100。"
        )
        return {
            "course": course_name,
            "review_count": len(reviews),
            "workload": workload,
            "grading_friendliness": grading,
            "substance": substance,
            "hardcore_index": hardcore_index,
            "summary": summary,
            "evidence": evidence[:8],
            "difficulty": None,
        }

    def _enrich_with_reviews(
        self, course_name: str, db_result: dict[str, Any], extra_reviews: list[str] | None
    ) -> dict[str, Any]:
        """结合难度数据库结果与实时评价"""
        reviews = [
            r
            for r in self.store.reviews_doc["reviews"]
            if course_name.lower() in r["course"].lower() or r["course"].lower() in course_name.lower()
        ]
        if extra_reviews:
            reviews.extend({"course": course_name, "source": "user-input", "text": text, "rating": 0} for text in extra_reviews)

        summary = (
            f"{db_result['name']} 综合难度 {db_result['difficulty_score']}/100"
            f"（{'⭐' * db_result['stars']} {db_result['star_label']}）。"
            f"基于教务系统数据分析，参考学分、课程类别、专业化程度等多维度指标。"
        )

        result: dict[str, Any] = {
            "course": db_result["name"],
            "stars": db_result["stars"],
            "star_label": db_result["star_label"],
            "star_description": db_result["star_description"],
            "difficulty_score": db_result["difficulty_score"],
            "dimensions": db_result["dimensions"],
            "meta": db_result["meta"],
            "review_count": len(reviews),
            "summary": summary,
            "evidence": [],
        }

        if reviews:
            evidence_list = []
            for r in reviews:
                text = r["text"]
                wl = clamp(50 + 18 * _hits(text, WORKLOAD_HIGH) - 15 * _hits(text, WORKLOAD_LOW))
                gr = clamp(50 + 18 * _hits(text, GRADING_FRIENDLY) - 16 * _hits(text, GRADING_STRICT))
                sb = clamp(50 + 18 * _hits(text, SUBSTANCE_HIGH) - 15 * _hits(text, SUBSTANCE_LOW))
                evidence_list.append({
                    "source": r.get("source", ""),
                    "text": text,
                    "workload": wl,
                    "grading_friendliness": gr,
                    "substance": sb,
                })
            result["evidence"] = evidence_list[:8]
            result["summary"] += f" 共 {len(reviews)} 条论坛评价佐证。"

        return result


class ProfessorMatcher:
    def __init__(self, store: QinmianDataStore) -> None:
        self.store = store

    def match(self, interest_text: str, top_k: int = 5) -> list[dict[str, Any]]:
        rows = []
        # Build homepage lookup from faculty profiles
        homepage_lookup: dict[str, str] = {}
        for teacher in self.store.faculty_profiles_doc.get("teachers", []):
            name = teacher.get("name", "").strip()
            hp = teacher.get("homepage", "").strip()
            if name and hp:
                homepage_lookup[name] = hp

        for professor in self.store.professors_doc["professors"]:
            profile = " ".join(
                [
                    professor.get("name", ""),
                    professor.get("college", ""),
                    " ".join(professor.get("research_interests", [])),
                    " ".join(professor.get("papers", [])),
                    " ".join(professor.get("courses", [])),
                ]
            )
            score = cosine_similarity(interest_text, profile)
            pname = professor.get("name", "")
            rows.append(
                {
                    "id": professor["id"],
                    "name": pname,
                    "college": professor["college"],
                    "title": professor.get("title", ""),
                    "research_interests": professor.get("research_interests", []),
                    "papers": professor.get("papers", [])[:3],
                    "courses": professor.get("courses", []),
                    "similarity": round(score, 4),
                    "homepage": homepage_lookup.get(pname, ""),
                }
            )
        return sorted(rows, key=lambda r: r["similarity"], reverse=True)[:top_k]


class CreditChecker:
    def __init__(self, store: QinmianDataStore) -> None:
        self.store = store

    def check(
        self,
        major_id: str,
        completed_courses: list[Any],
        student_type: str = "domestic",
    ) -> dict[str, Any]:
        curriculum = self.store.curriculum_for(major_id, student_type)
        courses = curriculum["courses"]
        rule = curriculum["credit_rule"]
        completed_names = set()
        explicit_credits: dict[str, tuple[str, float]] = {}
        for item in completed_courses:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    completed_names.add(name)
            elif isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                completed_names.add(name)
                if "category" in item and "credits" in item:
                    explicit_credits[name] = (str(item["category"]), float(item["credits"]))
        earned_by_category: dict[str, float] = defaultdict(float)
        matched = []
        unmatched = []
        course_by_name = {c["name"]: c for c in courses}
        for name in completed_names:
            if name in explicit_credits:
                category, credits = explicit_credits[name]
                category = self._credit_category(category, name, rule)
                earned_by_category[category] += credits
                matched.append({"name": name, "category": category, "credits": credits, "source": "explicit"})
                continue
            course = course_by_name.get(name) or self._fuzzy_find(name, courses)
            if course:
                category = self._credit_category(course["category"], course["name"], rule)
                earned_by_category[category] += course["credits"]
                matched.append({"name": course["name"], "category": category, "credits": course["credits"], "source": "curriculum"})
            else:
                unmatched.append(name)
        deficits = []
        total_earned = sum(earned_by_category.values())
        minimums = rule.get("category_minimums", rule["categories"])
        for category, required_display in rule["categories"].items():
            required = minimums.get(category)
            earned = earned_by_category.get(category, 0)
            gap = max(0, required - earned) if isinstance(required, (int, float)) else None
            deficits.append(
                {
                    "category": category,
                    "required": required_display,
                    "required_minimum": required,
                    "earned": earned,
                    "gap": gap,
                    "status": "unknown" if gap is None else "ok" if gap == 0 else "risk",
                }
            )
        risk_points = [f"{d['category']} 缺口 {d['gap']:g} 学分" for d in deficits if isinstance(d["gap"], (int, float)) and d["gap"] > 0]
        unknown_points = [f"{d['category']} 要求为“{d['required']}”，需按培养方案人工确认" for d in deficits if d["gap"] is None]
        validation = rule.get("validation", {})
        source_warning = []
        if validation.get("matches_graduation_total") is False:
            source_warning.append(
                f"源表分类合计 {validation.get('category_total')} 与总学分 {rule['graduation_total']} 不一致"
            )
        return {
            "major": curriculum["major"],
            "graduation_total": rule["graduation_total"],
            "credit_rule": rule,
            "student_type": curriculum["student_type"],
            "total_earned": total_earned,
            "total_gap": max(0, rule["graduation_total"] - total_earned),
            "deficits": deficits,
            "matched": matched,
            "unmatched": unmatched,
            "risk_points": source_warning + risk_points + unknown_points,
        }

    def _credit_category(self, category: str, course_name: str, rule: dict[str, Any]) -> str:
        if rule.get("is_template"):
            return category
        if course_name == "社会实践":
            return "社会实践"
        mapping = {
            "通识必修": "通识教育必修",
            "通识选修": "通识教育选修",
            "学科基础": "专业基础课",
            "专业必修": "专业核心课",
            "专业选修": "专业选修课",
            "实践与创新": "专业实践",
        }
        return mapping.get(category, category)

    def _fuzzy_find(self, name: str, courses: list[dict[str, Any]]) -> dict[str, Any] | None:
        name_lower = name.lower()
        for course in courses:
            course_lower = course["name"].lower()
            if name_lower in course_lower or course_lower in name_lower:
                return course
        return None


def time_to_minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


class ConflictResolver:
    DAYS = ["周一", "周二", "周三", "周四", "周五"]
    STANDARD_SLOTS = [
        ("08:00", "09:40"),
        ("10:00", "11:40"),
        ("14:30", "16:10"),
        ("16:20", "18:00"),
        ("19:00", "20:40"),
    ]

    def __init__(self, store: QinmianDataStore) -> None:
        self.store = store

    def resolve(self, major_id: str, selected_courses: list[dict[str, Any]]) -> dict[str, Any]:
        curriculum = self.store.curriculum_for(major_id)
        normalized, invalid_entries, duplicate_entries = self._normalize_courses(selected_courses)
        conflicts = []
        for i, left in enumerate(normalized):
            for right in normalized[i + 1 :]:
                if self._conflicts(left, right):
                    overlap = min(time_to_minutes(left["end"]), time_to_minutes(right["end"])) - max(
                        time_to_minutes(left["start"]), time_to_minutes(right["start"])
                    )
                    conflicts.append(
                        {
                            "left": left,
                            "right": right,
                            "reason": f"上课时间重叠 {overlap} 分钟",
                            "overlap_minutes": overlap,
                        }
                    )
        alternatives = self._alternatives(curriculum["courses"], normalized)
        recommended_changes: list[dict[str, Any]] = []
        changed_courses: set[tuple[str, str, str]] = set()
        for conflict in conflicts:
            left = conflict["left"]
            right = conflict["right"]
            movable = right
            if "必修" in right.get("category", "") and "必修" not in left.get("category", ""):
                movable = left
            change_key = (movable.get("name", ""), movable.get("day", ""), movable.get("start", ""))
            if change_key in changed_courses:
                continue
            change = self._find_reschedule(movable, normalized)
            if change:
                recommended_changes.append(change)
                changed_courses.add(change_key)

        name_counts = Counter(course.get("name", "") for course in normalized if course.get("name"))
        duplicate_courses = sorted(name for name, count in name_counts.items() if count > 1)
        plans = [
            {
                "name": "方案A：自动错峰（推荐）",
                "strategy": (
                    "优先保留必修课，并把可移动课程安排到当前课表中的空闲时段。"
                    if recommended_changes
                    else "当前没有可自动调整的冲突时段。"
                ),
                "changes": recommended_changes,
            },
            {
                "name": "方案B：压低本学期负荷",
                "strategy": "保留关键前置课，把非前置课程顺延到下一学期。",
                "changes": [
                    {
                        "action": "defer",
                        "course": course.get("name"),
                        "from_semester": course.get("semester", 1),
                        "to_semester": int(course.get("semester", 1)) + 1,
                    }
                    for course in normalized
                    if "必修" not in course.get("category", "")
                ][:2],
            },
            {
                "name": "方案C：同类别替代",
                "strategy": "若无法换时段，使用同类别、相近学分课程替代冲突选修课。",
                "changes": alternatives[:3],
            },
        ]
        return {
            "status": "conflict" if conflicts else "ok",
            "summary": (
                f"发现 {len(conflicts)} 组时间冲突，已生成 {len(recommended_changes)} 项可应用调整。"
                if conflicts
                else "未发现时间冲突。"
            ),
            "input_count": len(selected_courses),
            "course_count": len(normalized),
            "normalized_courses": normalized,
            "invalid_entries": invalid_entries,
            "duplicate_entries": duplicate_entries,
            "duplicate_courses": duplicate_courses,
            "conflicts": conflicts,
            "alternatives": alternatives,
            "recommended_changes": recommended_changes,
            "plans": plans,
        }

    def _normalize_courses(
        self,
        selected_courses: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        normalized: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        day_aliases = {
            "1": "周一", "星期一": "周一", "周一": "周一",
            "2": "周二", "星期二": "周二", "周二": "周二",
            "3": "周三", "星期三": "周三", "周三": "周三",
            "4": "周四", "星期四": "周四", "周四": "周四",
            "5": "周五", "星期五": "周五", "周五": "周五",
        }
        for index, raw in enumerate(selected_courses):
            name = re.sub(r"\s+", " ", str(raw.get("name", "")).strip())
            day = day_aliases.get(str(raw.get("day", "")).strip(), "")
            start = str(raw.get("start", "")).strip()
            end = str(raw.get("end", "")).strip()
            errors = []
            if not name:
                errors.append("课程名为空")
            if not day:
                errors.append("星期无效")
            try:
                start_minutes = time_to_minutes(start)
                end_minutes = time_to_minutes(end)
                if end_minutes <= start_minutes:
                    errors.append("结束时间必须晚于开始时间")
            except Exception:
                errors.append("时间格式无效")
            if errors:
                invalid.append({"index": index, "name": name or f"第{index + 1}条", "errors": errors})
                continue
            item = {
                **raw,
                "name": name,
                "day": day,
                "start": start,
                "end": end,
                "category": str(raw.get("category", "未分类")).strip() or "未分类",
                "semester": int(raw.get("semester") or 1),
            }
            identity = (name.casefold(), day, start, end)
            if identity in seen:
                duplicates.append({"index": index, "course": item, "reason": "同一课程和时段重复录入"})
                continue
            seen.add(identity)
            normalized.append(item)
        return normalized, invalid, duplicates

    def _conflicts(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        if left.get("day") != right.get("day"):
            return False
        try:
            left_start = time_to_minutes(left["start"])
            left_end = time_to_minutes(left["end"])
            right_start = time_to_minutes(right["start"])
            right_end = time_to_minutes(right["end"])
        except Exception:
            return False
        return max(left_start, right_start) < min(left_end, right_end)

    def _find_reschedule(
        self,
        course: dict[str, Any],
        selected_courses: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        other_courses = [row for row in selected_courses if row is not course]
        for day in self.DAYS:
            for start, end in self.STANDARD_SLOTS:
                candidate = {**course, "day": day, "start": start, "end": end}
                if all(not self._conflicts(candidate, other) for other in other_courses):
                    return {
                        "action": "reschedule",
                        "course": course.get("name", ""),
                        "from": {
                            "day": course.get("day", ""),
                            "start": course.get("start", ""),
                            "end": course.get("end", ""),
                        },
                        "to": {"day": day, "start": start, "end": end},
                        "reason": "避开现有课程并优先保留必修课",
                    }
        return None

    def _alternatives(self, courses: list[dict[str, Any]], selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected_names = {c.get("name") for c in selected}
        rows = []
        seen: set[tuple[str, int]] = set()
        for course in courses:
            if course["name"] in selected_names:
                continue
            if course["category"] not in {"专业选修", "通识选修", "实践与创新"}:
                continue
            key = (course["name"], int(course.get("semester") or 0))
            if key in seen:
                continue
            seen.add(key)
            candidate = {
                "name": course["name"],
                "category": course["category"],
                "credits": course["credits"],
                "semester": course.get("semester"),
                "reason": "同类别替代或补足学分",
            }
            rows.append(candidate)
        return rows[:8]
