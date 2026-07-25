from __future__ import annotations

import csv
import copy
import io
import json
import random
import re
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


def load_json(name: str) -> dict[str, Any]:
    path = DATA_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_json_optional(name: str, default: dict[str, Any]) -> dict[str, Any]:
    path = DATA_DIR / name
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def slug(text: str) -> str:
    return (
        text.lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("（", "-")
        .replace("）", "-")
        .replace("(", "-")
        .replace(")", "-")
    )


class QinmianDataStore:
    def __init__(self) -> None:
        self.majors_doc = load_json("majors_2026.json")
        self.curriculum_doc = load_json("curriculum_templates.json")
        self.graduation_credit_doc = load_json_optional(
            "graduation_credit_requirements.json",
            {"source": {}, "student_types": {}},
        )
        self.reviews_doc = load_json("course_reviews.json")
        self.professors_doc = load_json("professors.json")
        self.career_doc = load_json("career_profiles.json")
        self.seat_doc = load_json("seat_inventory.json")
        self.teacher_roster_doc = load_json_optional("teacher_roster.json", {"teachers": []})
        self.faculty_profiles_doc = load_json_optional("faculty_profiles.json", {"source": {}, "colleges": [], "ranks": [], "teachers": []})
        self.course_assignments_doc = load_json_optional("course_assignments.json", {"source": {}, "assignments": []})
        self.imported_teacher_schedule_path = DATA_DIR / "imported_teacher_schedule.json"
        self.imported_teacher_schedule = self._load_imported_teacher_schedule()
        self._merge_imported_teacher_schedule()
        self.majors = self.majors_doc["majors"]
        self.major_by_id = {m["id"]: m for m in self.majors}
        self.watchers: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    def _load_imported_teacher_schedule(self) -> list[dict[str, Any]]:
        if not self.imported_teacher_schedule_path.exists():
            return []
        with self.imported_teacher_schedule_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            return payload.get("rows", [])
        if isinstance(payload, list):
            return payload
        return []

    def _save_imported_teacher_schedule(self) -> None:
        payload = {
            "source": "华侨大学教务课表导入",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "rows": self.imported_teacher_schedule,
        }
        with self.imported_teacher_schedule_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def _merge_imported_teacher_schedule(self) -> None:
        if not self.imported_teacher_schedule:
            return
        professor_by_name = {p["name"]: p for p in self.professors_doc.get("professors", [])}
        offering_ids = {o.get("id") for o in self.seat_doc.get("offerings", [])}
        for row in self.imported_teacher_schedule:
            teacher = row.get("teacher", "").strip()
            course = row.get("course", "").strip()
            if not teacher or not course:
                continue
            professor = professor_by_name.get(teacher)
            if not professor:
                professor = {
                    "id": f"jw-teacher-{slug(teacher)}",
                    "name": teacher,
                    "college": row.get("college", ""),
                    "title": row.get("title", ""),
                    "research_interests": [],
                    "papers": [],
                    "courses": [],
                    "source": "imported_jw_schedule",
                }
                professor_by_name[teacher] = professor
                self.professors_doc.setdefault("professors", []).append(professor)
            if course not in professor.setdefault("courses", []):
                professor["courses"].append(course)
            offering_id = row.get("id") or f"jw-{slug(course)}-{slug(teacher)}-{slug(row.get('section', '01'))}"
            if offering_id in offering_ids:
                continue
            offering_ids.add(offering_id)
            self.seat_doc.setdefault("offerings", []).append(
                {
                    "id": offering_id,
                    "course": course,
                    "section": row.get("section", "01"),
                    "teacher": teacher,
                    "day": row.get("day", ""),
                    "start": row.get("start", ""),
                    "end": row.get("end", ""),
                    "capacity": int(row.get("capacity") or 0),
                    "enrolled": int(row.get("enrolled") or 0),
                    "campus": row.get("campus", ""),
                    "source": "imported_jw_schedule",
                }
            )

    def list_majors(
        self,
        q: str = "",
        campus: str = "",
        college: str = "",
        discipline: str = "",
    ) -> list[dict[str, Any]]:
        q = q.strip().lower()
        results = []
        for major in self.majors:
            haystack = " ".join(
                [
                    major.get("name", ""),
                    major.get("display_name", ""),
                    major.get("college", ""),
                    major.get("campus", ""),
                    " ".join(major.get("streams", [])),
                    " ".join(major.get("related_colleges", [])),
                    " ".join(major.get("aliases", [])),
                    major.get("discipline", ""),
                ]
            ).lower()
            if q and q not in haystack:
                continue
            if campus and campus != major.get("campus"):
                continue
            if college and college != major.get("college") and college not in major.get("related_colleges", []):
                continue
            if discipline and discipline != major.get("discipline"):
                continue
            results.append(major)
        return results

    def get_major(self, major_id: str) -> dict[str, Any] | None:
        return self.major_by_id.get(major_id)

    def colleges(self) -> list[str]:
        names = set()
        for major in self.majors:
            names.add(major["college"])
            names.update(major.get("related_colleges", []))
        for teacher in self.teacher_roster_doc.get("teachers", []):
            if teacher.get("college"):
                names.add(teacher["college"])
        for teacher in self.faculty_profiles_doc.get("teachers", []):
            names.update(teacher.get("colleges", []))
        return sorted(names)

    def teacher_roster_colleges(self) -> list[str]:
        return sorted({t["college"] for t in self.teacher_roster_doc.get("teachers", []) if t.get("college")})

    def teacher_roster_by_college(self, college: str = "", q: str = "", scheduled: str = "") -> list[dict[str, Any]]:
        college = college.strip()
        q = q.strip().lower()
        scheduled = self._normalize_scheduled(scheduled)
        rows = []
        for teacher in self.teacher_roster_doc.get("teachers", []):
            haystack = " ".join(
                [
                    teacher.get("teacher_id", ""),
                    teacher.get("name", ""),
                    teacher.get("college", ""),
                    teacher.get("gender", ""),
                    teacher.get("scheduled", ""),
                ]
            ).lower()
            if college and college != teacher.get("college"):
                continue
            if q and q not in haystack:
                continue
            if scheduled and scheduled != teacher.get("scheduled"):
                continue
            rows.append(teacher)
        return sorted(rows, key=lambda row: (row.get("college", ""), row.get("name", ""), row.get("teacher_id", "")))

    def teacher_roster_by_name(self, name: str) -> list[dict[str, Any]]:
        name = name.strip().lower()
        if not name:
            return []
        rows = []
        for teacher in self.teacher_roster_doc.get("teachers", []):
            teacher_name = teacher.get("name", "").lower()
            teacher_id = teacher.get("teacher_id", "").lower()
            if name in teacher_name or name in teacher_id:
                rows.append(teacher)
        return sorted(rows, key=lambda row: (row.get("college", ""), row.get("name", ""), row.get("teacher_id", "")))

    def all_teacher_names(self) -> list[str]:
        names = set()
        for teacher in self.teacher_roster_doc.get("teachers", []):
            if teacher.get("name"):
                names.add(teacher["name"])
        for teacher in self.faculty_profiles_doc.get("teachers", []):
            if teacher.get("name"):
                names.add(teacher["name"])
        for row in self.course_assignments_doc.get("assignments", []):
            if row.get("teacher"):
                names.add(row["teacher"])
        return sorted(names)

    def teacher_course_assignments(self, teacher_name: str) -> list[dict[str, Any]]:
        query = teacher_name.strip().lower()
        if not query:
            return []
        rows = []
        for row in self.course_assignments_doc.get("assignments", []):
            teacher = row.get("teacher", "")
            teacher_lower = teacher.lower()
            if query in teacher_lower or teacher_lower in query:
                rows.append(row)
        return sorted(rows, key=lambda row: (row.get("course", ""), row.get("term", ""), row.get("teacher", "")))

    def teacher_course_summary(self, teacher_name: str, limit: int = 200) -> list[dict[str, Any]]:
        groups: dict[tuple[str, Any], dict[str, Any]] = {}
        for row in self.teacher_course_assignments(teacher_name):
            key = (row.get("course", ""), row.get("credits", 0))
            item = groups.setdefault(
                key,
                {
                    "course": row.get("course", ""),
                    "credits": row.get("credits", 0),
                    "majors": set(),
                    "campuses": set(),
                    "college": row.get("college", ""),
                    "records": 0,
                },
            )
            item["majors"].update(row.get("majors", []))
            if row.get("campus"):
                item["campuses"].add(row["campus"])
            if not item.get("college") and row.get("college"):
                item["college"] = row["college"]
            item["records"] += 1
        summaries = []
        for item in groups.values():
            summaries.append(
                {
                    **item,
                    "majors": sorted(item["majors"]),
                    "campuses": sorted(item["campuses"]),
                }
            )
        return sorted(summaries, key=lambda row: (row.get("course", ""), row.get("credits", 0)))[:limit]

    def enrich_teacher_row(self, row: dict[str, Any]) -> dict[str, Any]:
        item = copy.deepcopy(row)
        item["courses_taught"] = self.teacher_course_summary(row.get("name", ""), limit=200)
        return item

    def course_assignments_for_course(self, course_name: str) -> list[dict[str, Any]]:
        query = course_name.strip().lower()
        if not query:
            return []
        exact = [row for row in self.course_assignments_doc.get("assignments", []) if row.get("course", "").lower() == query]
        if exact:
            return exact
        return [
            row
            for row in self.course_assignments_doc.get("assignments", [])
            if query in row.get("course", "").lower() or row.get("course", "").lower() in query
        ]

    def faculty_profile_colleges(self) -> list[str]:
        names = {row.get("name", "") for row in self.faculty_profiles_doc.get("colleges", [])}
        for teacher in self.faculty_profiles_doc.get("teachers", []):
            names.update(teacher.get("colleges", []))
        return sorted(name for name in names if name)

    def faculty_profile_ranks(self) -> list[str]:
        names = {row.get("name", "") for row in self.faculty_profiles_doc.get("ranks", [])}
        for teacher in self.faculty_profiles_doc.get("teachers", []):
            if teacher.get("title"):
                names.add(teacher["title"])
        return sorted(names)

    def teacher_query_colleges(self) -> list[str]:
        return sorted(set(self.teacher_roster_colleges()) | set(self.faculty_profile_colleges()))

    def faculty_profiles(self, college: str = "", rank: str = "", q: str = "", tutor: str = "") -> list[dict[str, Any]]:
        college = college.strip()
        rank = rank.strip()
        q = q.strip().lower()
        tutor = tutor.strip()
        rows = []
        for teacher in self.faculty_profiles_doc.get("teachers", []):
            haystack = " ".join(
                [
                    teacher.get("teacher_id", ""),
                    teacher.get("name", ""),
                    teacher.get("english_name", ""),
                    teacher.get("title", ""),
                    teacher.get("unit_raw", ""),
                    teacher.get("profile", ""),
                    teacher.get("graduate_tutor", ""),
                    teacher.get("doctor_tutor", ""),
                    " ".join(teacher.get("colleges", [])),
                    " ".join(teacher.get("matched_roster_colleges", [])),
                ]
            ).lower()
            if college and college not in teacher.get("colleges", []) and college not in teacher.get("matched_roster_colleges", []):
                continue
            if rank and not self._rank_matches(teacher.get("title", ""), rank):
                continue
            if tutor == "doctor" and not teacher.get("doctor_tutor"):
                continue
            if tutor == "graduate" and not (teacher.get("graduate_tutor") or teacher.get("doctor_tutor")):
                continue
            if q and q not in haystack:
                continue
            rows.append(teacher)
        return sorted(rows, key=lambda row: (",".join(row.get("colleges", [])), row.get("title", ""), row.get("name", "")))

    def faculty_profiles_by_name(self, name: str) -> list[dict[str, Any]]:
        return self.faculty_profiles(q=name)

    def _rank_matches(self, title: str, rank: str) -> bool:
        if not rank:
            return True
        if title == rank:
            return True
        if rank == "教授":
            return title == "教授" or title.startswith("教授（")
        if rank == "副教授":
            return title == "副教授" or title.startswith("副教授（")
        if rank == "讲师":
            return title == "讲师" or title.startswith("讲师（")
        if rank == "研究员":
            return title == "研究员" or title.startswith("研究员（")
        if rank == "副研究员":
            return title == "副研究员" or title.startswith("副研究员（")
        return rank in title

    def _normalize_scheduled(self, scheduled: str = "") -> str:
        value = scheduled.strip()
        if value in {"是", "已排课", "有排课", "true", "1", "yes"}:
            return "是"
        if value in {"否", "未排课", "没排课", "没有排课", "false", "0", "no"}:
            return "否"
        return ""

    def campuses(self) -> list[str]:
        return sorted({m["campus"] for m in self.majors})

    def disciplines(self) -> list[str]:
        return sorted({m["discipline"] for m in self.majors})

    def normalize_student_type(self, student_type: str | None) -> str:
        value = str(student_type or "").strip().lower()
        if value in {"international", "overseas", "境外生", "留学生", "华裔学生"}:
            return "international"
        return "domestic"

    def _template_credit_rule_for(self, major: dict[str, Any]) -> dict[str, Any]:
        rules = self.curriculum_doc["credit_rules"]
        if major["name"] in {"临床医学"} or major["discipline"] == "medicine":
            return copy.deepcopy(rules["medicine"])
        if major["name"] in {"建筑学"} or major["discipline"] == "architecture":
            return copy.deepcopy(rules["architecture"])
        if major["discipline"] == "art":
            return copy.deepcopy(rules["art"])
        return copy.deepcopy(rules["default"])

    def _credit_name(self, value: str) -> str:
        text = str(value or "").strip().lower()
        text = text.replace("（", "(").replace("）", ")")
        return re.sub(r"[\s,，、·]", "", text)

    def _credit_base_name(self, value: str) -> str:
        return self._credit_name(value).split("(", 1)[0]

    def _graduation_credit_record_for(
        self,
        major: dict[str, Any],
        student_type: str,
    ) -> dict[str, Any] | None:
        section = self.graduation_credit_doc.get("student_types", {}).get(student_type, {})
        records = section.get("records", [])
        college_names = {self._credit_name(major.get("college", ""))}
        college_names.update(
            self._credit_name(value)
            for value in major.get("related_colleges", [])
            if value
        )
        candidates = [major.get("name", ""), major.get("display_name", "")]
        candidates.extend(major.get("aliases", []))
        candidate_names = {self._credit_name(value) for value in candidates if value}
        candidate_bases = {self._credit_base_name(value) for value in candidates if value}

        best: tuple[int, dict[str, Any]] | None = None
        for record in records:
            if self._credit_name(record.get("college", "")) not in college_names:
                continue
            record_name = self._credit_name(record.get("major", ""))
            record_base = self._credit_base_name(record.get("major", ""))
            score = 0
            if record_name in candidate_names:
                score = 100
            elif record_base and record_base in candidate_bases:
                score = 80
            if score and (best is None or score > best[0]):
                best = (score, record)
        return copy.deepcopy(best[1]) if best else None

    def graduation_credit_rule_for(
        self,
        major: dict[str, Any],
        student_type: str = "domestic",
    ) -> dict[str, Any]:
        student_type = self.normalize_student_type(student_type)
        section = self.graduation_credit_doc.get("student_types", {}).get(student_type, {})
        record = self._graduation_credit_record_for(major, student_type)
        if record:
            return {
                "graduation_total": record["graduation_total"],
                "categories": record["categories"],
                "category_minimums": record.get("category_minimums", {}),
                "student_type": student_type,
                "student_type_label": section.get("label", "境内生" if student_type == "domestic" else "境外生"),
                "matched_major": record.get("major", ""),
                "matched_college": record.get("college", ""),
                "source_row": record.get("source_row"),
                "validation": record.get("validation", {}),
                "source": self.graduation_credit_doc.get("source", {}),
                "source_kind": "user_provided_real_data",
                "is_template": False,
            }

        fallback = self._template_credit_rule_for(major)
        fallback["category_minimums"] = {
            name: value if isinstance(value, (int, float)) else None
            for name, value in fallback.get("categories", {}).items()
        }
        fallback.update(
            {
                "student_type": student_type,
                "student_type_label": section.get("label", "境内生" if student_type == "domestic" else "境外生"),
                "matched_major": "",
                "matched_college": "",
                "source": {"name": "内置课程模板"},
                "source_kind": "template_fallback",
                "is_template": True,
                "validation": {},
            }
        )
        return fallback

    def _template_for(self, major: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        templates = self.curriculum_doc["templates"]
        key = major.get("discipline", "default")
        if key in templates:
            return self._merge_template(key)
        return self._fallback_template(major)

    def _merge_template(self, key: str) -> dict[str, list[dict[str, Any]]]:
        templates = self.curriculum_doc["templates"]
        template = copy.deepcopy(templates[key])
        base_name = template.pop("extends", None)
        if not base_name:
            return {
                "required": template.get("required", []),
                "electives": template.get("electives", []),
            }
        base = self._merge_template(base_name)
        return {
            "required": base["required"] + template.get("required", []),
            "electives": base["electives"] + template.get("electives", []),
        }

    def _fallback_template(self, major: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        discipline = major.get("discipline", "")
        major_name = major.get("name", "专业")
        common_foundation = [
            {"name": f"{major_name}导论", "category": "学科基础", "credits": 2, "semester": 1},
            {"name": f"{major_name}研究方法", "category": "学科基础", "credits": 3, "semester": 3},
            {"name": "毕业论文/设计", "category": "实践与创新", "credits": 8, "semester": 8},
        ]
        by_discipline: dict[str, dict[str, list[dict[str, Any]]]] = {
            "architecture": {
                "required": [
                    {"name": "建筑设计基础", "category": "专业必修", "credits": 6, "semester": 1},
                    {"name": "建筑制图", "category": "专业必修", "credits": 3, "semester": 2},
                    {"name": "建筑构造", "category": "专业必修", "credits": 4, "semester": 3},
                    {"name": "城市规划原理", "category": "专业必修", "credits": 3, "semester": 4},
                    {"name": "建筑设计 studio", "category": "专业必修", "credits": 8, "semester": 5},
                ],
                "electives": [
                    {"name": "智慧建造专题", "category": "专业选修", "credits": 2, "semester": 6},
                    {"name": "历史街区保护", "category": "专业选修", "credits": 2, "semester": 7},
                ],
            },
            "civil": {
                "required": [
                    {"name": "工程力学", "category": "学科基础", "credits": 5, "semester": 2},
                    {"name": "结构力学", "category": "专业必修", "credits": 4, "semester": 3},
                    {"name": "土力学", "category": "专业必修", "credits": 3, "semester": 4},
                    {"name": "混凝土结构设计", "category": "专业必修", "credits": 4, "semester": 5},
                ],
                "electives": [
                    {"name": "智慧建造与BIM", "category": "专业选修", "credits": 2, "semester": 6},
                    {"name": "城市地下空间工程导论", "category": "专业选修", "credits": 2, "semester": 6},
                ],
            },
            "material": {
                "required": [
                    {"name": "材料科学基础", "category": "专业必修", "credits": 4, "semester": 3},
                    {"name": "物理化学", "category": "学科基础", "credits": 4, "semester": 3},
                    {"name": "材料现代分析方法", "category": "专业必修", "credits": 3, "semester": 5},
                    {"name": "材料工程基础", "category": "专业必修", "credits": 3, "semester": 5},
                ],
                "electives": [
                    {"name": "新能源材料", "category": "专业选修", "credits": 3, "semester": 6},
                    {"name": "材料计算与数据", "category": "专业选修", "credits": 2, "semester": 7},
                ],
            },
            "chemistry": {
                "required": [
                    {"name": "无机化学", "category": "学科基础", "credits": 4, "semester": 1},
                    {"name": "有机化学", "category": "学科基础", "credits": 4, "semester": 2},
                    {"name": "化工原理", "category": "专业必修", "credits": 5, "semester": 4},
                    {"name": "化工设计", "category": "专业必修", "credits": 3, "semester": 6},
                ],
                "electives": [
                    {"name": "绿色化工", "category": "专业选修", "credits": 2, "semester": 6},
                    {"name": "能源电化学", "category": "专业选修", "credits": 2, "semester": 7},
                ],
            },
            "media": {
                "required": [
                    {"name": "新闻学概论", "category": "专业必修", "credits": 3, "semester": 1},
                    {"name": "传播学概论", "category": "专业必修", "credits": 3, "semester": 2},
                    {"name": "新闻采访与写作", "category": "专业必修", "credits": 4, "semester": 3},
                    {"name": "新媒体内容生产", "category": "专业必修", "credits": 3, "semester": 5},
                ],
                "electives": [
                    {"name": "数据新闻", "category": "专业选修", "credits": 2, "semester": 6},
                    {"name": "短视频策划", "category": "专业选修", "credits": 2, "semester": 6},
                ],
            },
            "language": {
                "required": [
                    {"name": "综合语言训练", "category": "专业必修", "credits": 8, "semester": 1},
                    {"name": "语言学概论", "category": "专业必修", "credits": 3, "semester": 3},
                    {"name": "跨文化交际", "category": "专业必修", "credits": 3, "semester": 4},
                    {"name": "高级写作", "category": "专业必修", "credits": 3, "semester": 5},
                ],
                "electives": [
                    {"name": "商务翻译", "category": "专业选修", "credits": 2, "semester": 6},
                    {"name": "语料库与语言技术", "category": "专业选修", "credits": 2, "semester": 7},
                ],
            },
            "humanities": {
                "required": [
                    {"name": "中国文化概论", "category": "专业必修", "credits": 3, "semester": 2},
                    {"name": "学术阅读与写作", "category": "专业必修", "credits": 3, "semester": 3},
                    {"name": "专业经典导读", "category": "专业必修", "credits": 4, "semester": 4},
                ],
                "electives": [
                    {"name": "数字人文", "category": "专业选修", "credits": 2, "semester": 6},
                    {"name": "海外华人社会研究", "category": "专业选修", "credits": 2, "semester": 7},
                ],
            },
            "art": {
                "required": [
                    {"name": "造型基础", "category": "学科基础", "credits": 6, "semester": 1},
                    {"name": "设计构成", "category": "专业必修", "credits": 4, "semester": 2},
                    {"name": "专业创作", "category": "专业必修", "credits": 6, "semester": 5},
                    {"name": "毕业创作", "category": "实践与创新", "credits": 8, "semester": 8},
                ],
                "electives": [
                    {"name": "数字媒体艺术", "category": "专业选修", "credits": 3, "semester": 5},
                    {"name": "作品集工作坊", "category": "专业选修", "credits": 2, "semester": 7},
                ],
            },
        }
        template = by_discipline.get(
            discipline,
            {
                "required": [
                    {"name": f"{major_name}核心课程I", "category": "专业必修", "credits": 4, "semester": 3},
                    {"name": f"{major_name}核心课程II", "category": "专业必修", "credits": 4, "semester": 4},
                    {"name": f"{major_name}综合实践", "category": "实践与创新", "credits": 4, "semester": 6},
                ],
                "electives": [
                    {"name": f"{major_name}专题研讨", "category": "专业选修", "credits": 2, "semester": 6},
                    {"name": f"{major_name}前沿进展", "category": "专业选修", "credits": 2, "semester": 7},
                ],
            },
        )
        return {
            "required": common_foundation + template["required"],
            "electives": template["electives"],
        }

    def curriculum_for(self, major_id: str, student_type: str = "domestic") -> dict[str, Any]:
        major = self.get_major(major_id)
        if not major:
            raise KeyError(f"unknown major: {major_id}")
        student_type = self.normalize_student_type(student_type)
        rule = self.graduation_credit_rule_for(major, student_type)
        template = self._template_for(major)
        courses: list[dict[str, Any]] = []
        for origin, rows in [
            ("common", self.curriculum_doc["common_courses"]),
            ("required", template["required"]),
            ("elective", template["electives"]),
            ("general_elective", self.curriculum_doc["general_electives"]),
        ]:
            for row in rows:
                item = copy.deepcopy(row)
                item["id"] = f"{major_id}-{origin}-{slug(item['name'])}-{item.get('semester', 0)}"
                item["origin"] = origin
                item["teachers"] = self.teachers_for_course(item["name"])
                courses.append(item)
        by_category: dict[str, int] = {}
        for course in courses:
            by_category[course["category"]] = by_category.get(course["category"], 0) + course["credits"]
        return {
            "major": major,
            "credit_rule": rule,
            "student_type": student_type,
            "available_student_types": {
                kind: self._graduation_credit_record_for(major, kind) is not None
                for kind in ("domestic", "international")
            },
            "courses": sorted(courses, key=lambda c: (c.get("semester", 99), c["category"], c["name"])),
            "category_template_credits": by_category,
            "first_required_courses": [
                c
                for c in sorted(courses, key=lambda c: (c.get("semester", 99), c["name"]))
                if c["category"] == "专业必修"
            ][:8],
            "recommended_electives": [
                c
                for c in sorted(courses, key=lambda c: (c.get("semester", 99), c["name"]))
                if c["category"] in {"专业选修", "通识选修"}
            ][:10],
        }

    def teachers_for_course(self, course_name: str) -> list[dict[str, str]]:
        matches = []
        seen_names = set()
        for professor in self.professors_doc["professors"]:
            if course_name in professor.get("courses", []):
                seen_names.add(professor["name"])
                matches.append(
                    {
                        "id": professor["id"],
                        "name": professor["name"],
                        "college": professor["college"],
                        "title": professor.get("title", ""),
                    }
                )
        assignment_groups: dict[str, dict[str, Any]] = {}
        for row in self.course_assignments_for_course(course_name):
            teacher = row.get("teacher", "")
            if not teacher or teacher in seen_names:
                continue
            item = assignment_groups.setdefault(
                teacher,
                {
                    "id": f"course-assignment-{slug(teacher)}",
                    "name": teacher,
                    "college": row.get("college", ""),
                    "title": "",
                    "credits": row.get("credits", 0),
                    "majors": set(),
                },
            )
            item["majors"].update(row.get("majors", []))
            if not item.get("college") and row.get("college"):
                item["college"] = row["college"]
        for item in assignment_groups.values():
            matches.append(
                {
                    **item,
                    "majors": sorted(item["majors"]),
                }
            )
        return matches or [{"id": "pending", "name": "待导入任课教师", "college": "", "title": ""}]

    def import_teacher_schedule_text(self, text: str, replace: bool = False) -> dict[str, Any]:
        rows = self._parse_teacher_schedule_text(text)
        if replace:
            self.imported_teacher_schedule = []
        existing_keys = {
            (
                row.get("teacher", ""),
                row.get("course", ""),
                row.get("section", ""),
                row.get("day", ""),
                row.get("start", ""),
            )
            for row in self.imported_teacher_schedule
        }
        imported = []
        skipped = []
        for row in rows:
            key = (
                row.get("teacher", ""),
                row.get("course", ""),
                row.get("section", ""),
                row.get("day", ""),
                row.get("start", ""),
            )
            if key in existing_keys:
                skipped.append(row)
                continue
            existing_keys.add(key)
            imported.append(row)
            self.imported_teacher_schedule.append(row)
        self._save_imported_teacher_schedule()
        self._merge_imported_teacher_schedule()
        return {
            "status": "ok",
            "imported": len(imported),
            "skipped": len(skipped),
            "total": len(self.imported_teacher_schedule),
            "sample": imported[:5],
        }

    def _parse_teacher_schedule_text(self, text: str) -> list[dict[str, Any]]:
        text = text.strip("\ufeff \n\r\t")
        if not text:
            return []
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                raw_rows = payload.get("rows") or payload.get("data") or payload.get("items") or []
            else:
                raw_rows = payload
            if isinstance(raw_rows, list):
                return [self._normalize_teacher_schedule_row(row) for row in raw_rows if isinstance(row, dict)]
        except json.JSONDecodeError:
            pass
        dialect = "excel-tab" if "\t" in text.splitlines()[0] else "excel"
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        rows = []
        for raw in reader:
            row = self._normalize_teacher_schedule_row(raw)
            if row.get("teacher") and row.get("course"):
                rows.append(row)
        return rows

    def _normalize_teacher_schedule_row(self, raw: dict[str, Any]) -> dict[str, Any]:
        def pick(*names: str) -> str:
            normalized = {str(k).strip().lower(): v for k, v in raw.items()}
            for name in names:
                key = name.strip().lower()
                if key in normalized and normalized[key] is not None:
                    return str(normalized[key]).strip()
            for k, v in raw.items():
                key = str(k).strip().lower()
                if any(name.strip().lower() in key for name in names) and v is not None:
                    return str(v).strip()
            return ""

        return {
            "teacher": pick("teacher", "教师", "任课教师", "授课教师", "老师", "姓名"),
            "course": pick("course", "课程", "课程名称", "教学班名称", "课程名"),
            "section": pick("section", "教学班", "班级", "课程序号", "课堂号") or "01",
            "day": pick("day", "星期", "周次", "上课星期", "上课时间"),
            "start": pick("start", "开始", "开始时间", "节次开始", "上课开始"),
            "end": pick("end", "结束", "结束时间", "节次结束", "下课时间"),
            "campus": pick("campus", "校区", "开课校区"),
            "college": pick("college", "学院", "开课学院", "教师学院", "任课学院"),
            "title": pick("title", "职称"),
            "capacity": pick("capacity", "容量", "课容量") or "0",
            "enrolled": pick("enrolled", "已选", "选课人数") or "0",
        }

    def all_course_names(self) -> list[str]:
        names = {review["course"] for review in self.reviews_doc["reviews"]}
        names.update(row.get("course", "") for row in self.course_assignments_doc.get("assignments", []) if row.get("course"))
        for major in self.majors:
            try:
                names.update(c["name"] for c in self.curriculum_for(major["id"])["courses"])
            except KeyError:
                continue
        return sorted(names)

    def hot_directions(self) -> list[dict[str, Any]]:
        return self.career_doc["hot_directions"]

    def offerings(self) -> list[dict[str, Any]]:
        rows = []
        for row in self.seat_doc["offerings"]:
            item = copy.deepcopy(row)
            item["remaining"] = item["capacity"] - item["enrolled"]
            rows.append(item)
        return rows

    def add_watcher(self, course: str, student: str = "demo-student") -> dict[str, Any]:
        match = self._find_offering(course)
        if not match:
            result = {
                "status": "not_found",
                "message": f"未找到 {course} 的模拟开课记录，可先导入教务余位数据。",
            }
            self.events.append(self._event("watcher_failed", result["message"]))
            return result
        if match["capacity"] > match["enrolled"]:
            match["enrolled"] += 1
            result = {
                "status": "auto_enrolled",
                "message": f"{course} {match['section']} 已有余位，勤勉已通过模拟 API 自动捡漏。",
                "offering": self._with_remaining(match),
            }
            self.events.append(self._event("auto_enrolled", result["message"]))
            return result
        watcher = {
            "id": f"watch-{int(time.time() * 1000)}-{random.randint(100, 999)}",
            "course": match["course"],
            "section": match["section"],
            "student": student,
            "status": "watching",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.watchers.append(watcher)
        message = f"{course} {match['section']} 暂无余位，已进入实时监控队列。"
        self.events.append(self._event("watching", message))
        return {"status": "watching", "message": message, "watcher": watcher, "offering": self._with_remaining(match)}

    def tick_seats(self) -> dict[str, Any]:
        released = []
        picked = []
        for offering in self.seat_doc["offerings"]:
            full = offering["enrolled"] >= offering["capacity"]
            has_watcher = any(w["course"] == offering["course"] and w["status"] == "watching" for w in self.watchers)
            if full and has_watcher and random.random() < 0.65:
                offering["enrolled"] -= 1
                released.append(self._with_remaining(offering))
            for watcher in self.watchers:
                if watcher["status"] != "watching":
                    continue
                if watcher["course"] != offering["course"]:
                    continue
                if offering["capacity"] > offering["enrolled"]:
                    offering["enrolled"] += 1
                    watcher["status"] = "picked"
                    watcher["picked_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    picked.append({"watcher": watcher, "offering": self._with_remaining(offering)})
                    self.events.append(self._event("auto_enrolled", f"{offering['course']} {offering['section']} 自动捡漏成功"))
        if not released and not picked:
            self.events.append(self._event("tick", "本轮模拟未释放名额"))
        return {
            "released": released,
            "picked": picked,
            "watchers": self.watchers,
            "offerings": self.offerings(),
            "events": self.events[-12:],
        }

    def _find_offering(self, course: str) -> dict[str, Any] | None:
        course_lower = course.lower().strip()
        for offering in self.seat_doc["offerings"]:
            if course_lower in offering["course"].lower() or offering["course"].lower() in course_lower:
                return offering
        return None

    def _with_remaining(self, offering: dict[str, Any]) -> dict[str, Any]:
        item = copy.deepcopy(offering)
        item["remaining"] = item["capacity"] - item["enrolled"]
        return item

    def _event(self, kind: str, message: str) -> dict[str, str]:
        return {
            "kind": kind,
            "message": message,
            "time": time.strftime("%H:%M:%S"),
        }
