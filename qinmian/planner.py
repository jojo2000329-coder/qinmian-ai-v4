from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .analytics import cosine_similarity
from .data_store import QinmianDataStore


class CareerPlanner:
    def __init__(self, store: QinmianDataStore) -> None:
        self.store = store

    def recommend_for_major(
        self,
        major_id: str,
        limit: int = 6,
    ) -> dict[str, Any]:
        """Rank curated career profiles for one selected major."""
        major = self.store.get_major(str(major_id or "").strip())
        if not major:
            raise KeyError(f"unknown major: {major_id}")

        limit = max(1, min(int(limit or 6), 10))
        curriculum = self.store.curriculum_for(major["id"])
        course_names = [
            str(course.get("name", "")).strip()
            for course in curriculum.get("courses", [])
            if course.get("name")
        ]
        major_names = {
            str(major.get("name", "")).strip(),
            str(major.get("display_name", "")).strip(),
            *{
                str(alias).strip()
                for alias in major.get("aliases", [])
                if str(alias).strip()
            },
        }
        major_names.discard("")
        major_text = " ".join([
            *sorted(major_names),
            str(major.get("college", "")),
            str(major.get("discipline", "")),
            " ".join(major.get("streams", [])),
            " ".join(course_names),
        ])

        rows: list[dict[str, Any]] = []
        for role_name, role in self.store.career_doc.get("roles", {}).items():
            targets = {
                str(item).strip()
                for item in role.get("target_majors", [])
                if str(item).strip()
            }
            direct_target = bool(major_names & targets)
            partial_target = not direct_target and any(
                left and right and (left in right or right in left)
                for left in major_names
                for right in targets
            )
            target_disciplines = {
                str(candidate.get("discipline", "")).strip()
                for candidate in self.store.majors
                if {
                    str(candidate.get("name", "")).strip(),
                    str(candidate.get("display_name", "")).strip(),
                } & targets
            }
            same_discipline = bool(
                major.get("discipline")
                and major.get("discipline") in target_disciplines
            )

            role_text = " ".join([
                role_name,
                " ".join(role.get("aliases", [])),
                " ".join(role.get("keywords", [])),
                " ".join(targets),
                str(role.get("description", "")),
                " ".join(role.get("must_courses", [])),
            ])
            semantic_score = max(0.0, cosine_similarity(major_text, role_text))
            name_affinity = max(
                0.0,
                cosine_similarity(
                    " ".join(sorted(major_names)),
                    " ".join([role_name, *role.get("aliases", [])]),
                ),
            )
            must_courses = [
                str(item).strip()
                for item in role.get("must_courses", [])
                if str(item).strip()
            ]
            course_hits = sum(
                1
                for required in must_courses
                if any(
                    required in course or course in required
                    for course in course_names
                    if len(course) >= 2
                )
            )
            course_overlap = min(
                1.0,
                course_hits / max(1, min(len(must_courses), 4)),
            )

            raw_score = (
                (0.68 if direct_target else 0.44 if partial_target else 0.0)
                + (0.18 if same_discipline else 0.0)
                + semantic_score * 0.20
                + course_overlap * 0.12
            )
            if direct_target:
                raw_score = max(raw_score, 0.82)
            score = min(99, max(1, round(raw_score * 100)))
            if direct_target:
                match_type = "direct"
                reason = f"职业画像明确将“{major['name']}”列为适配专业"
            elif partial_target:
                match_type = "major_related"
                reason = "职业画像的目标专业与当前专业名称或方向高度相关"
            elif same_discipline:
                match_type = "discipline_related"
                reason = "与当前专业属于相近学科门类，核心能力具有较强迁移性"
            else:
                match_type = "skill_related"
                reason = "当前专业课程与岗位能力存在可迁移的知识或技能"

            level = (
                "高度适配"
                if score >= 80
                else "比较适配"
                if score >= 60
                else "相关方向"
                if score >= 40
                else "拓展方向"
            )
            rows.append({
                "name": role_name,
                "aliases": list(role.get("aliases", [])),
                "category": self.store.career_category(role_name, role),
                "description": str(role.get("description", "")).strip(),
                "score": score,
                "level": level,
                "match_type": match_type,
                "reason": reason,
                "matched_target_majors": sorted(major_names & targets),
                "target_major_count": len(targets),
                "name_affinity": round(name_affinity, 4),
                "must_courses": must_courses,
                "keywords": list(role.get("keywords", [])),
            })

        rows.sort(
            key=lambda row: (
                row["match_type"] == "direct",
                row["match_type"] == "major_related",
                row["score"],
                row["name_affinity"],
                -row["target_major_count"],
                row["name"],
            ),
            reverse=True,
        )
        relevant_rows = [
            row
            for row in rows
            if row["match_type"] != "skill_related" or row["score"] >= 40
        ]
        if not relevant_rows:
            relevant_rows = rows[:1]
        selected_rows = relevant_rows[:limit]
        return {
            "major": major,
            "recommendations": selected_rows,
            "recommendation_count": len(selected_rows),
            "available_profile_count": len(rows),
            "notice": (
                "推荐依据为职业画像目标专业、学科门类、培养方案课程与岗位能力的综合匹配；"
                "用于探索方向，不代表就业承诺。"
            ),
        }

    def plan(self, career: str, major_id: str | None = None) -> dict[str, Any]:
        career = str(career or "").strip() or "自定义岗位"
        role_name, role, match_info = self._match_role(career)
        ranked_majors = self._rank_majors(role, career)
        selected_major = self.store.get_major(major_id) if major_id else None
        if not selected_major:
            selected_major = ranked_majors[0]["major"] if ranked_majors else self.store.majors[0]
        curriculum = self.store.curriculum_for(selected_major["id"])
        program_years = self.store.program_years_for(selected_major)
        semester_count = self._semester_count(selected_major)
        semesters = self._build_semesters(
            curriculum["courses"],
            role,
            semester_count,
            selected_major,
            role_name,
        )
        academic_years, planning_periods = self._build_academic_years(
            semesters,
            program_years,
            selected_major,
            role_name,
        )
        selected_fit = self._major_fit(
            selected_major,
            role,
            career,
            curriculum["courses"],
        )
        milestones = list(role.get("milestones", []))
        if semester_count == 10 and not any("第5年" in item for item in milestones):
            milestones.append("第5年：完成高阶专业实践、毕业考核及执业或升学衔接。")
        return {
            "career": career,
            "matched_role": role_name,
            "career_match": match_info,
            "profile_category": self.store.career_category(role_name, role),
            "profile_description": role.get("description", ""),
            "profile_aliases": role.get("aliases", []),
            "available_profile_count": len(self.store.career_doc.get("roles", {})),
            "selected_major": selected_major,
            "selected_major_fit": selected_fit,
            "recommended_majors": ranked_majors[:8],
            "must_courses": role.get("must_courses", []),
            "elective_keywords": role.get("elective_keywords", []),
            "milestones": milestones,
            "salary_range": role.get("salary_range", ""),
            "program_years": program_years,
            "semester_count": semester_count,
            "regular_semester_count": semester_count,
            "summer_term_count": max(0, program_years - 1),
            "planning_period_count": len(planning_periods),
            "semesters": semesters,
            "planning_periods": planning_periods,
            "academic_years": academic_years,
            "planning_note": (
                "每学年前两学期对应培养方案正式学期；非毕业学年的第3学期为小学期职业增强建议，"
                "不冒充学校正式课程且按 0 学分展示。具体安排请以学院和教务系统为准。"
            ),
        }

    def _match_role(
        self,
        career: str,
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        roles = self.store.career_doc["roles"]
        query = self._normalize_role_text(career)
        if not query:
            return self._custom_role(career, 0.0)

        for name, role in roles.items():
            if query == self._normalize_role_text(name):
                return (
                    name,
                    role,
                    self._match_info("exact", 1.0, False),
                )
            for alias in role.get("aliases", []):
                if query == self._normalize_role_text(alias):
                    return (
                        name,
                        role,
                        self._match_info("alias", 1.0, False),
                    )

        substring_matches: list[tuple[float, int, str, dict[str, Any]]] = []
        for name, role in roles.items():
            for candidate in [name, *role.get("aliases", [])]:
                normalized = self._normalize_role_text(candidate)
                if len(normalized) < 2:
                    continue
                if normalized in query or query in normalized:
                    coverage = min(len(query), len(normalized)) / max(
                        len(query),
                        len(normalized),
                    )
                    substring_matches.append(
                        (0.78 + coverage * 0.2, len(normalized), name, role)
                    )
        if substring_matches:
            score, _, name, role = max(substring_matches)
            return (
                name,
                role,
                self._match_info("alias", min(0.98, score), False),
            )

        best_name = ""
        best_score = -1.0
        for name, role in roles.items():
            profile = " ".join([
                name,
                " ".join(role.get("aliases", [])),
                " ".join(role.get("keywords", [])),
                " ".join(role.get("target_majors", [])),
                str(role.get("description", "")),
            ])
            score = cosine_similarity(career, profile)
            if score > best_score:
                best_name = name
                best_score = score
        if best_score < 0.16:
            return self._custom_role(career, max(0.0, best_score))
        return (
            best_name,
            roles[best_name],
            self._match_info("semantic", best_score, False),
        )

    @staticmethod
    def _normalize_role_text(value: str) -> str:
        return re.sub(
            r"[^0-9a-z\u4e00-\u9fff]+",
            "",
            str(value or "").lower(),
        )

    @staticmethod
    def _match_info(
        match_type: str,
        score: float,
        is_custom: bool,
    ) -> dict[str, Any]:
        notices = {
            "exact": "已使用职业库中的精确岗位画像。",
            "alias": "已根据常用别名匹配职业画像。",
            "semantic": "未找到同名岗位，已采用语义最接近的职业画像。",
            "custom": "职业库中暂无可靠匹配，已生成通用规划框架；建议结合招聘要求继续补充。",
        }
        return {
            "type": match_type,
            "score": round(float(score), 4),
            "is_custom": is_custom,
            "notice": notices[match_type],
        }

    def _custom_role(
        self,
        career: str,
        score: float,
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        return (
            "自定义岗位",
            {
                "aliases": [],
                "category": "自定义方向",
                "description": (
                    f"职业库中暂无可靠匹配：“{career}”。以下内容为通用学业规划框架。"
                ),
                "keywords": [career],
                "target_majors": [],
                "must_courses": [],
                "elective_keywords": [],
                "salary_range": "",
                "milestones": [
                    "第1年：补齐通识、数学/写作和专业导论。",
                    "第2年：完成学科基础与核心专业课。",
                    "第3年：用选修课和项目靠近目标岗位。",
                    "第4年：用实习、科研或毕业设计形成作品。",
                ],
            },
            self._match_info("custom", score, True),
        )

    def _rank_majors(self, role: dict[str, Any], career: str) -> list[dict[str, Any]]:
        rows = []
        for major in self.store.majors:
            score = self._major_score(major, role, career)
            rows.append({"major": major, "score": round(score, 4)})
        return sorted(rows, key=lambda r: r["score"], reverse=True)

    def _major_score(self, major: dict[str, Any], role: dict[str, Any], career: str) -> float:
        targets = role.get("target_majors", [])
        major_text = " ".join(
            [
                major["name"],
                major["display_name"],
                major["college"],
                " ".join(major.get("streams", [])),
                major.get("discipline", ""),
            ]
        )
        target_text = " ".join([career, " ".join(role.get("keywords", [])), " ".join(targets)])
        direct_target = major["name"] in targets or major["display_name"] in targets
        partial_target = any(
            target and (target in major["display_name"] or major["name"] in target)
            for target in targets
        )
        target_bonus = 0.52 if direct_target else 0.28 if partial_target else 0.0
        semantic_score = cosine_similarity(target_text, major_text) * 0.58
        quality_bonus = (
            0.04
            if major.get("first_class_level") == "G"
            else 0.02
            if major.get("first_class_level") == "S"
            else 0.0
        )
        score = semantic_score + target_bonus + quality_bonus
        if direct_target:
            score = max(score, 0.82 + quality_bonus)
        elif partial_target:
            score = max(score, 0.58 + quality_bonus)
        return min(1.0, score)

    def _major_fit(
        self,
        major: dict[str, Any],
        role: dict[str, Any],
        career: str,
        courses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        score = self._major_score(major, role, career)
        percentage = round(score * 100)
        if percentage >= 75:
            level = "高度匹配"
        elif percentage >= 50:
            level = "比较匹配"
        elif percentage >= 30:
            level = "可迁移发展"
        else:
            level = "专业跨度较大"

        targets = role.get("target_majors", [])
        is_direct = major["name"] in targets or major["display_name"] in targets
        course_names = {course.get("name", "") for course in courses}
        missing_courses = [
            name for name in role.get("must_courses", []) if name not in course_names
        ]
        if is_direct:
            reason = "该专业属于岗位资料中的直接推荐专业，培养方向与目标岗位联系紧密。"
        elif percentage >= 50:
            reason = "该专业与目标岗位共享较多学科基础，可通过方向选修、项目和实习完成衔接。"
        elif percentage >= 30:
            reason = "具备部分可迁移能力，但需要主动补齐岗位核心课程并积累相关项目。"
        else:
            reason = "并非不能从事该职业，但跨专业成本较高，建议重点补课、做项目并尽早实习验证。"
        return {
            "score": percentage,
            "level": level,
            "is_direct": is_direct,
            "reason": reason,
            "missing_core_courses": missing_courses[:8],
        }

    def _semester_count(self, major: dict[str, Any]) -> int:
        return self.store.program_years_for(major) * 2

    def _build_semesters(
        self,
        courses: list[dict[str, Any]],
        role: dict[str, Any],
        semester_count: int,
        major: dict[str, Any],
        role_name: str,
    ) -> list[dict[str, Any]]:
        must = set(role.get("must_courses", []))
        by_semester: dict[int, list[dict[str, Any]]] = defaultdict(list)
        used_names = set()

        # 先完整保留培养方案中已有的课程；职业规划只做增补，不应把普通课程过滤掉。
        for course in courses:
            raw_semester = int(course.get("semester") or 1)
            semester = max(1, min(raw_semester, semester_count))
            by_semester[semester].append(course)
            used_names.add(course["name"])

        # 岗位核心课不在培养方案时，明确标为 0 学分职业增强建议。
        missing_boosters = [name for name in must if name not in used_names]
        for index, name in enumerate(missing_boosters):
            semester = min(3 + index % max(1, semester_count - 2), semester_count)
            suggestion = self._suggested_course(
                f"建议补充：{name}",
                semester,
                f"{role_name}核心能力，可通过选修、自学或项目补齐",
                f"career-booster-{index}",
            )
            by_semester[semester].append(suggestion)
            used_names.add(suggestion["name"])

        # 每学期补充到至少 5 项，让路线覆盖专业认知、项目、实习和求职。
        # 增补项均为 0 学分并带“建议”前缀，不冒充学校正式课程。
        for semester in range(1, semester_count + 1):
            candidates = self._enrichment_suggestions(
                semester,
                semester_count,
                major.get("display_name", major.get("name", "本专业")),
                role_name,
            )
            for offset, (name, note) in enumerate(candidates):
                if len(by_semester[semester]) >= 5:
                    break
                if name in used_names:
                    continue
                suggestion = self._suggested_course(
                    name,
                    semester,
                    note,
                    f"career-enrichment-{semester}-{offset}",
                )
                by_semester[semester].append(suggestion)
                used_names.add(name)

        semesters = []
        for semester in range(1, semester_count + 1):
            rows = sorted(
                by_semester.get(semester, []),
                key=lambda c: (c.get("origin") == "career", c["category"], c["name"]),
            )
            credits = sum(c.get("credits", 0) for c in rows)
            semesters.append(
                {
                    "semester": semester,
                    "label": f"第{semester}学期",
                    "credits": credits,
                    "courses": rows,
                    "official_course_count": sum(
                        1 for course in rows if course.get("origin") != "career"
                    ),
                    "suggested_course_count": sum(
                        1 for course in rows if course.get("origin") == "career"
                    ),
                    "focus": self._focus_for_semester(semester),
                }
            )
        return semesters

    @staticmethod
    def _year_label(year: int) -> str:
        labels = {
            1: "大一",
            2: "大二",
            3: "大三",
            4: "大四",
            5: "大五",
            6: "大六",
        }
        return labels.get(year, f"第{year}学年")

    def _build_academic_years(
        self,
        semesters: list[dict[str, Any]],
        program_years: int,
        major: dict[str, Any],
        role_name: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Group formal semesters by year and insert non-credit summer mini-terms."""
        by_number = {int(item["semester"]): item for item in semesters}
        academic_years: list[dict[str, Any]] = []
        planning_periods: list[dict[str, Any]] = []
        period_index = 0
        major_name = major.get("display_name") or major.get("name") or "本专业"

        for year in range(1, program_years + 1):
            year_label = self._year_label(year)
            periods: list[dict[str, Any]] = []
            for term in (1, 2):
                official_semester = (year - 1) * 2 + term
                base = dict(by_number.get(official_semester, {
                    "semester": official_semester,
                    "credits": 0,
                    "courses": [],
                    "official_course_count": 0,
                    "suggested_course_count": 0,
                    "focus": "以学院最新培养方案为准",
                }))
                period_index += 1
                base.update({
                    "period_index": period_index,
                    "year": year,
                    "year_label": year_label,
                    "term": term,
                    "term_type": "regular",
                    "official_semester": official_semester,
                    "label": f"{year_label} · 第{term}学期",
                    "short_label": f"第{term}学期",
                })
                periods.append(base)
                planning_periods.append(base)

            # 毕业学年不再虚构第3学期；此前学年增加明确标注的小学期规划。
            if year < program_years:
                period_index += 1
                summer_courses = self._summer_suggestions(
                    year,
                    program_years,
                    major_name,
                    role_name,
                )
                summer = {
                    "semester": None,
                    "period_index": period_index,
                    "year": year,
                    "year_label": year_label,
                    "term": 3,
                    "term_type": "summer",
                    "official_semester": None,
                    "label": f"{year_label} · 第3学期（小学期）",
                    "short_label": "第3学期（小学期）",
                    "credits": 0,
                    "courses": summer_courses,
                    "official_course_count": 0,
                    "suggested_course_count": len(summer_courses),
                    "focus": self._summer_focus(year, program_years),
                }
                periods.append(summer)
                planning_periods.append(summer)

            academic_years.append({
                "year": year,
                "label": year_label,
                "is_graduation_year": year == program_years,
                "period_indexes": [period["period_index"] for period in periods],
            })

        return academic_years, planning_periods

    def _summer_suggestions(
        self,
        year: int,
        program_years: int,
        major_name: str,
        role_name: str,
    ) -> list[dict[str, Any]]:
        if year == 1:
            rows = [
                ("建议：专业认知调研", f"走访学院、实验室或行业单位，验证对{major_name}的理解"),
                ("建议：基础工具训练营", "集中补齐数据处理、检索、写作或专业软件基础"),
                ("建议：低门槛学科竞赛", "用小型团队任务检验兴趣与协作方式"),
                ("建议：志愿服务与社会实践", "积累真实情境中的沟通、责任和执行证据"),
                ("建议：大一学习复盘", "复盘前两学期并制定下一学年的能力清单"),
            ]
        elif year == 2:
            rows = [
                (f"建议：{role_name}岗位体验", "通过企业开放日、访谈或短期见习了解真实工作"),
                ("建议：专业项目实训", "完成一个可运行、可展示、可复盘的小型项目"),
                ("建议：科研或竞赛入门", "加入导师课题组或参加与专业相关的竞赛"),
                ("建议：专业英语与资料阅读", "阅读岗位文档、行业报告或基础论文"),
                ("建议：作品集阶段整理", "记录问题、过程、个人贡献和结果证据"),
            ]
        elif year < program_years - 1:
            rows = [
                (f"建议：{role_name}方向实习", "用真实任务验证职业匹配度并记录能力缺口"),
                ("建议：高阶项目或科研实践", "完成一项与目标岗位直接相关的综合成果"),
                ("建议：行业导师访谈", "请从业者评估课程、项目和求职准备"),
                ("建议：资格与能力证明准备", "按专业需求准备证书、考试或公开成果"),
                ("建议：毕业方向预研", "提前确定毕业论文、设计或长期实践方向"),
            ]
        else:
            rows = [
                (f"建议：{role_name}长期实习", "承担连续任务并沉淀可验证的岗位能力证据"),
                ("建议：毕业成果预研", "提前完成选题、资料、方案或实验准备"),
                ("建议：求职与升学材料定稿", "完善简历、作品集、推荐材料与备选方案"),
                ("建议：专业资格准备", "按行业或执业要求安排考试与能力训练"),
                ("建议：毕业学年风险复核", "核对学分、实践、毕业审核和关键时间节点"),
            ]

        return [
            self._suggested_course(
                name,
                None,
                note,
                f"career-summer-{year}-{index}",
            )
            for index, (name, note) in enumerate(rows)
        ]

    @staticmethod
    def _summer_focus(year: int, program_years: int) -> str:
        if year == 1:
            return "认知调研、基础训练与社会实践"
        if year == 2:
            return "岗位体验、项目实训与竞赛科研"
        if year < program_years - 1:
            return "方向实习、高阶项目与毕业预研"
        return "长期实习、毕业预研与去向准备"

    def _suggested_course(
        self,
        name: str,
        semester: int | None,
        note: str,
        course_id: str,
    ) -> dict[str, Any]:
        return {
            "id": course_id,
            "name": name,
            "category": "规划建议",
            "credits": 0,
            "semester": semester,
            "origin": "career",
            "planning_note": note,
            "teachers": [
                {
                    "id": "planning",
                    "name": note,
                    "college": "",
                    "title": "",
                }
            ],
        }

    def _enrichment_suggestions(
        self,
        semester: int,
        semester_count: int,
        major_name: str,
        role_name: str,
    ) -> list[tuple[str, str]]:
        semester_rows: dict[int, list[tuple[str, str]]] = {
            1: [
                ("建议：专业认知与生涯探索", f"了解{major_name}培养路径和典型岗位"),
                ("建议：信息检索与学术规范", "训练可靠资料检索、引用和学术诚信"),
                ("建议：数字工具基础", "掌握表格、可视化和基础数据处理"),
                ("建议：表达沟通与团队协作", "通过汇报和小组任务训练通用能力"),
                ("建议：专业社团与朋辈交流", "低成本探索兴趣并认识高年级项目"),
            ],
            2: [
                ("建议：学术写作与表达", "训练结构化写作、演示和答辩能力"),
                ("建议：数据素养基础", "理解数据采集、清洗、分析和呈现"),
                ("建议：学科竞赛体验", "选择一项低门槛竞赛验证兴趣"),
                ("建议：课程项目初体验", "把基础知识用于一个可完成的小项目"),
                ("建议：专业基础复盘", "梳理后续核心课程的先修知识"),
            ],
            3: [
                (f"建议：{role_name}岗位技能入门", "对照岗位要求建立技能清单"),
                ("建议：专业工具综合实训", "使用本专业常见工具完成小型任务"),
                ("建议：跨学科方法训练", "连接统计、计算、写作或设计方法"),
                ("建议：专业英语与文献阅读", "阅读行业资料和基础论文"),
                ("建议：课程项目作品化", "把课程作业整理为可展示成果"),
            ],
            4: [
                (f"建议：{role_name}岗位技能进阶", "针对岗位要求完成一次能力升级"),
                ("建议：行业小型项目", "完成包含需求、过程和结果的项目"),
                ("建议：团队项目管理", "训练分工、进度、沟通和复盘"),
                ("建议：研究文献精读", "阅读并复述本专业代表性资料"),
                ("建议：作品集框架搭建", "开始记录项目证据和个人贡献"),
            ],
            5: [
                (f"建议：{role_name}方向项目", "完成一个与目标岗位直接相关的完整项目"),
                ("建议：行业案例分析", "理解真实业务、工程或专业场景"),
                ("建议：科研或高水平竞赛训练", "在导师指导下完成可验证成果"),
                ("建议：企业真实课题实践", "接触需求分析、协作和交付流程"),
                ("建议：求职作品集初稿", "沉淀项目说明、过程证据和反思"),
            ],
            6: [
                (f"建议：{role_name}综合项目", "独立或组队完成一项完整成果"),
                ("建议：项目复盘与技术报告", "说明方案、数据、结果和改进方向"),
                ("建议：暑期实习准备", "完善简历并建立目标单位清单"),
                ("建议：作品集阶段评审", "请教师或行业导师给出反馈"),
                ("建议：行业资格与能力认证", "按职业需要选择证书或能力证明"),
            ],
            7: [
                (f"建议：{role_name}岗位实习", "用真实岗位验证职业匹配度"),
                ("建议：毕业设计方向确定", "让毕业成果与目标岗位形成联系"),
                ("建议：作品集与简历完善", "突出专业能力、项目成果和个人贡献"),
                ("建议：面试与笔试训练", "按目标岗位准备案例、技能题和表达"),
                ("建议：秋招与升学时间表", "建立节点并准备备选方案"),
            ],
            8: [
                ("建议：毕业设计或论文深化", "形成可展示、可验证的毕业成果"),
                ("建议：作品集终稿", "整理最能代表个人能力的成果"),
                ("建议：面试复盘与补强", "根据真实面试反馈修正能力短板"),
                ("建议：校招与升学双路径决策", "结合录取和岗位信息完成选择"),
                ("建议：行业导师毕业复盘", "形成入职或深造后的学习计划"),
            ],
        }
        if semester <= 8:
            return semester_rows[semester]

        # 五年制专业的第 9、10 学期使用高阶实践建议，并确保各学期名称不同。
        if semester == 9:
            rows = [
                ("建议：高阶专业实践强化", "完成长期实习、临床、设计或工程实践"),
                ("建议：毕业成果中期评审", "形成论文、作品、报告或可交付项目"),
                (f"建议：{role_name}资格与能力验证", "按行业要求准备资格、考试或能力证明"),
                ("建议：行业导师复盘", "请校内外导师评估能力缺口"),
                ("建议：毕业去向方案确认", "完成求职、升学或创业方案"),
            ]
            return rows
        return [
            ("建议：毕业实践与岗位衔接", "把长期专业实践转化为岗位能力证据"),
            ("建议：毕业成果终期答辩", "完成论文、作品、报告或项目交付"),
            (f"建议：{role_name}入职准备", "梳理岗位流程、工具和专业规范"),
            ("建议：执业或升学材料完善", "按毕业去向准备全部证明材料"),
            ("建议：毕业去向正式落地", "完成签约、录取、创业或后续计划"),
        ]

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
