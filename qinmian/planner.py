from __future__ import annotations

from collections import defaultdict
from typing import Any

from .analytics import cosine_similarity
from .data_store import QinmianDataStore


class CareerPlanner:
    def __init__(self, store: QinmianDataStore) -> None:
        self.store = store

    def plan(self, career: str, major_id: str | None = None) -> dict[str, Any]:
        role_name, role = self._match_role(career)
        ranked_majors = self._rank_majors(role, career)
        selected_major = self.store.get_major(major_id) if major_id else None
        if not selected_major:
            selected_major = ranked_majors[0]["major"] if ranked_majors else self.store.majors[0]
        curriculum = self.store.curriculum_for(selected_major["id"])
        semester_count = self._semester_count(selected_major)
        semesters = self._build_semesters(curriculum["courses"], role, semester_count)
        return {
            "career": career,
            "matched_role": role_name,
            "selected_major": selected_major,
            "recommended_majors": ranked_majors[:8],
            "must_courses": role.get("must_courses", []),
            "elective_keywords": role.get("elective_keywords", []),
            "milestones": role.get("milestones", []),
            "semester_count": semester_count,
            "semesters": semesters,
        }

    def _match_role(self, career: str) -> tuple[str, dict[str, Any]]:
        roles = self.store.career_doc["roles"]
        if career in roles:
            return career, roles[career]
        best_name = ""
        best_score = -1.0
        for name, role in roles.items():
            profile = " ".join([name, " ".join(role.get("keywords", [])), " ".join(role.get("target_majors", []))])
            score = cosine_similarity(career, profile)
            if score > best_score:
                best_name = name
                best_score = score
        if best_score <= 0:
            return (
                "自定义岗位",
                {
                    "keywords": [career],
                    "target_majors": [],
                    "must_courses": [],
                    "elective_keywords": [],
                    "milestones": [
                        "第1年：补齐通识、数学/写作和专业导论。",
                        "第2年：完成学科基础与核心专业课。",
                        "第3年：用选修课和项目靠近目标岗位。",
                        "第4年：用实习、科研或毕业设计形成作品。"
                    ],
                },
            )
        return best_name, roles[best_name]

    def _rank_majors(self, role: dict[str, Any], career: str) -> list[dict[str, Any]]:
        targets = role.get("target_majors", [])
        rows = []
        for major in self.store.majors:
            major_text = " ".join(
                [
                    major["name"],
                    major["display_name"],
                    major["college"],
                    " ".join(major.get("streams", [])),
                    major.get("discipline", ""),
                ]
            )
            target_bonus = 0.35 if major["name"] in targets or major["display_name"] in targets else 0
            stream_bonus = 0.12 if any(t in major["display_name"] for t in targets) else 0
            quality_bonus = 0.06 if major.get("first_class_level") == "G" else 0.03 if major.get("first_class_level") == "S" else 0
            score = cosine_similarity(" ".join([career, " ".join(role.get("keywords", [])), " ".join(targets)]), major_text)
            score = min(1.0, score + target_bonus + stream_bonus + quality_bonus)
            if score > 0:
                rows.append({"major": major, "score": round(score, 4)})
        return sorted(rows, key=lambda r: r["score"], reverse=True)

    def _semester_count(self, major: dict[str, Any]) -> int:
        display = major.get("display_name", "")
        if "五年" in display or major.get("discipline") in {"medicine", "architecture"}:
            return 10
        return 8

    def _build_semesters(self, courses: list[dict[str, Any]], role: dict[str, Any], semester_count: int) -> list[dict[str, Any]]:
        must = set(role.get("must_courses", []))
        elective_keywords = role.get("elective_keywords", [])
        by_semester: dict[int, list[dict[str, Any]]] = defaultdict(list)
        used_names = set()
        for course in courses:
            semester = min(int(course.get("semester", semester_count)), semester_count)
            is_core = (
                course["name"] in must
                or course["origin"] in {"common", "required"}
                or any(keyword in course["name"] for keyword in elective_keywords)
            )
            if is_core:
                by_semester[semester].append(course)
                used_names.add(course["name"])
        for course in courses:
            if course["name"] in used_names:
                continue
            semester = min(int(course.get("semester", semester_count)), semester_count)
            if course["category"] in {"专业选修", "通识选修", "实践与创新"} and len(by_semester[semester]) < 6:
                by_semester[semester].append(course)
                used_names.add(course["name"])
        missing_boosters = [name for name in must if name not in used_names]
        for index, name in enumerate(missing_boosters):
            semester = min(5 + index % max(1, semester_count - 4), semester_count)
            by_semester[semester].append(
                {
                    "id": f"career-booster-{index}",
                    "name": name,
                    "category": "职业增强",
                    "credits": 0,
                    "semester": semester,
                    "origin": "career",
                    "teachers": [{"id": "external", "name": "建议通过选修/自学/项目补齐", "college": "", "title": ""}],
                }
            )
        semesters = []
        for semester in range(1, semester_count + 1):
            rows = sorted(by_semester.get(semester, []), key=lambda c: (c["category"], c["name"]))
            credits = sum(c.get("credits", 0) for c in rows)
            semesters.append(
                {
                    "semester": semester,
                    "label": f"第{semester}学期",
                    "credits": credits,
                    "courses": rows,
                    "focus": self._focus_for_semester(semester),
                }
            )
        return semesters

    def _focus_for_semester(self, semester: int) -> str:
        if semester <= 2:
            return "通识、数学/写作与专业入门"
        if semester <= 4:
            return "学科基础与关键前置课"
        if semester <= 6:
            return "方向选修、项目和科研训练"
        if semester <= 8:
            return "实习、毕业设计和作品沉淀"
        return "临床/设计/实践强化"
