"""
LangChain 工具集 + Function Calling 定义
=========================================
将现有分析功能封装为 LangChain Tool，
并提供 OpenAI-compatible Function Calling schema。

配合 LLM 使用时，LangChain Agent 或 OpenAI Function Calling
可以自动根据用户问题选择合适的工具调用。
"""

from __future__ import annotations

import json
from typing import Any

from .analytics import (
    ConflictResolver,
    CourseDifficultyDB,
    CourseHardnessAnalyzer,
    CreditChecker,
    ProfessorMatcher,
)
from .data_store import QinmianDataStore
from .planner import CareerPlanner

# ── 尝试导入 LangChain（可选） ──
try:
    from langchain.tools import BaseTool, Tool
    from langchain_core.tools import tool as lc_tool
    LANGCHAIN_AVAILABLE = True
except ImportError:
    BaseTool = object  # type: ignore
    lc_tool = None
    LANGCHAIN_AVAILABLE = False


# ═════════════════════════════════════════════════════════════════════
# Function Calling Schema（不依赖 LangChain 也可用）
# ═════════════════════════════════════════════════════════════════════

def get_function_schemas() -> list[dict[str, Any]]:
    """
    返回 OpenAI-compatible Function Calling schemas。
    可直接传给 Chat Completion API 的 `functions` 或 `tools` 参数。
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "analyze_course_hardness",
                "description": "分析指定课程的难度，包括星级评定、多维度评分和选课建议。当用户问课程难不难、硬不硬核、水不水时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "course_name": {
                            "type": "string",
                            "description": "课程名称，如'数据结构'、'机器学习'",
                        }
                    },
                    "required": ["course_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_majors",
                "description": "搜索华侨大学的本科专业。支持按名称、校区、学院、学科门类筛选。当用户问有哪些专业、某个专业怎么样时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词，如'计算机'、'人工智能'"},
                        "campus": {"type": "string", "description": "校区筛选：'泉州校区'或'厦门校区'"},
                        "college": {"type": "string", "description": "学院筛选，如'计算机科学与技术学院'"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_curriculum",
                "description": "查询指定专业的培养方案，包括课程列表、学分要求、必修课和选修课。当用户问某个专业要学什么、毕业学分多少时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "major_id": {"type": "string", "description": "专业ID，如'computer-science'、'software-engineering'"},
                        "student_type": {"type": "string", "enum": ["domestic", "international"], "description": "学生类型：domestic=境内生，international=境外生"},
                    },
                    "required": ["major_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_credits",
                "description": "学分体检：检查已修课程是否满足毕业学分要求，找出学分缺口。当用户问学分够不够、毕业风险时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "major_id": {"type": "string", "description": "专业ID"},
                        "completed_courses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "已修课程名称列表",
                        },
                        "student_type": {"type": "string", "enum": ["domestic", "international"], "description": "学生类型"},
                    },
                    "required": ["major_id", "completed_courses"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "match_professor",
                "description": "根据研究方向匹配最合适的教师。当用户想找做某个方向的老师、或者匹配导师时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "interest": {"type": "string", "description": "研究方向或兴趣关键词，如'自然语言处理'、'集成电路'"},
                        "top_k": {"type": "integer", "description": "返回结果数量，默认5"},
                    },
                    "required": ["interest"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "plan_career",
                "description": "职业规划：根据目标岗位推荐最相关的专业和课程安排。当用户问某个职业怎么规划、4年课表时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "career": {"type": "string", "description": "目标岗位名称，如'算法工程师'、'数据分析师'"},
                        "major_id": {"type": "string", "description": "可选，已有专业ID"},
                    },
                    "required": ["career"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_course_teachers",
                "description": "查询某门课程的所有任课教师信息。当用户问谁教这门课、任课老师是谁时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "course_name": {"type": "string", "description": "课程名称"},
                    },
                    "required": ["course_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "resolve_conflicts",
                "description": "排课冲突检测与解决：检查所选课程是否存在时间冲突，给出替代方案。当用户问课程冲突、时间安排时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "major_id": {"type": "string", "description": "专业ID"},
                        "selected_courses": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "day": {"type": "string"},
                                    "start": {"type": "string"},
                                    "end": {"type": "string"},
                                },
                            },
                            "description": "已选课程列表（含时间信息）",
                        },
                    },
                    "required": ["major_id", "selected_courses"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_course_difficulty",
                "description": "按难度或星级搜索课程。当用户想找硬核课或水课时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "min_stars": {"type": "integer", "description": "最低星级（1-5），如5表示找最难的课"},
                        "max_stars": {"type": "integer", "description": "最高星级"},
                        "keyword": {"type": "string", "description": "课程关键词"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_teacher_info",
                "description": "查询教师的详细信息：所属学院、职称、研究方向、主页等。当用户问某个老师的情况时调用。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "teacher_name": {"type": "string", "description": "教师姓名"},
                    },
                    "required": ["teacher_name"],
                },
            },
        },
    ]


# ═════════════════════════════════════════════════════════════════════
# 工具执行器（不依赖 LangChain）
# ═════════════════════════════════════════════════════════════════════

class FunctionCallExecutor:
    """
    Function Calling 执行器。
    根据 OpenAI 返回的 function_call 选择并执行对应工具。
    可在不安装 LangChain 的情况下独立使用。
    """

    def __init__(self, store: QinmianDataStore) -> None:
        self.store = store
        self.hardness_analyzer = CourseHardnessAnalyzer(store)
        self.professor_matcher = ProfessorMatcher(store)
        self.credit_checker = CreditChecker(store)
        self.conflict_resolver = ConflictResolver(store)
        self.career_planner = CareerPlanner(store)
        self.difficulty_db = CourseDifficultyDB()

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """执行函数调用并返回 JSON 字符串结果"""
        executor = self._get_executor(name)
        if executor is None:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
        try:
            result = executor(arguments)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def _get_executor(self, name: str):
        executors = {
            "analyze_course_hardness": self._exec_analyze_hardness,
            "search_majors": self._exec_search_majors,
            "get_curriculum": self._exec_get_curriculum,
            "check_credits": self._exec_check_credits,
            "match_professor": self._exec_match_professor,
            "plan_career": self._exec_plan_career,
            "get_course_teachers": self._exec_course_teachers,
            "resolve_conflicts": self._exec_resolve_conflicts,
            "search_course_difficulty": self._exec_search_difficulty,
            "get_teacher_info": self._exec_teacher_info,
        }
        return executors.get(name)

    def _exec_analyze_hardness(self, args: dict[str, Any]) -> dict[str, Any]:
        course = args.get("course_name", "")
        return self.hardness_analyzer.analyze(course)

    def _exec_search_majors(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        return self.store.list_majors(
            q=args.get("query", ""),
            campus=args.get("campus", ""),
            college=args.get("college", ""),
        )[:20]

    def _exec_get_curriculum(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.store.curriculum_for(
            args.get("major_id", ""),
            args.get("student_type", "domestic"),
        )

    def _exec_check_credits(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.credit_checker.check(
            args.get("major_id", ""),
            args.get("completed_courses", []),
            args.get("student_type", "domestic"),
        )

    def _exec_match_professor(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        return self.professor_matcher.match(
            args.get("interest", ""),
            top_k=args.get("top_k", 5),
        )

    def _exec_plan_career(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.career_planner.plan(
            args.get("career", ""),
            args.get("major_id"),
        )

    def _exec_course_teachers(self, args: dict[str, Any]) -> dict[str, Any]:
        course = args.get("course_name", "")
        teachers = self.store.teachers_for_course(course)
        return {"course": course, "teachers": teachers}

    def _exec_resolve_conflicts(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.conflict_resolver.resolve(
            args.get("major_id", ""),
            args.get("selected_courses", []),
        )

    def _exec_search_difficulty(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        min_s = args.get("min_stars", 0)
        max_s = args.get("max_stars", 5)
        keyword = args.get("keyword", "")
        results = self.difficulty_db.list_by_stars(min_s) if min_s == max_s else []
        if not results and keyword:
            results = self.difficulty_db.search(keyword, top_k=20)
        if not results:
            results = self.difficulty_db.list_by_difficulty(
                min_score=max(0, (min_s or 0) * 20 - 10),
                max_score=min(100, (max_s or 5) * 20 + 10),
            )[:20]
        return results

    def _exec_teacher_info(self, args: dict[str, Any]) -> dict[str, Any]:
        name = args.get("teacher_name", "")
        roster = self.store.teacher_roster_by_name(name)
        profiles = self.store.faculty_profiles_by_name(name)
        courses = self.store.teacher_course_summary(name)
        return {
            "teacher_name": name,
            "roster_matches": roster[:10],
            "profile_matches": profiles[:10],
            "taught_courses": courses[:20],
        }


# ═════════════════════════════════════════════════════════════════════
# LangChain Tool 定义（可选）
# ═════════════════════════════════════════════════════════════════════

def _make_tools(executor: FunctionCallExecutor) -> list:
    """创建 LangChain Tool 列表"""
    if not LANGCHAIN_AVAILABLE:
        return []

    return [
        Tool(
            name="analyze_course_hardness",
            func=lambda course_name="": executor.execute(
                "analyze_course_hardness", {"course_name": course_name}
            ),
            description="分析指定课程的难度（星级、多维度评分、选课建议）。输入: 课程名称。",
        ),
        Tool(
            name="search_majors",
            func=lambda query="", campus="", college="": executor.execute(
                "search_majors",
                {"query": query, "campus": campus, "college": college},
            ),
            description="搜索华侨大学本科专业。支持按名称、校区(泉州/厦门)、学院筛选。",
        ),
        Tool(
            name="get_curriculum",
            func=lambda major_id="": executor.execute(
                "get_curriculum", {"major_id": major_id}
            ),
            description="查询专业培养方案（课程列表、学分要求）。输入: 专业ID。",
        ),
        Tool(
            name="check_credits",
            func=lambda major_id="", completed_courses=None: executor.execute(
                "check_credits",
                {"major_id": major_id, "completed_courses": completed_courses or []},
            ),
            description="学分体检：检查已修课程是否满足毕业要求。输入: 专业ID, 已修课程列表。",
        ),
        Tool(
            name="match_professor",
            func=lambda interest="", top_k=5: executor.execute(
                "match_professor", {"interest": interest, "top_k": top_k}
            ),
            description="按研究方向匹配最合适的教师。输入: 研究方向关键词。",
        ),
        Tool(
            name="plan_career",
            func=lambda career="", major_id="": executor.execute(
                "plan_career", {"career": career, "major_id": major_id}
            ),
            description="职业规划：为目标岗位推荐专业和课程安排。输入: 岗位名称。",
        ),
        Tool(
            name="get_course_teachers",
            func=lambda course_name="": executor.execute(
                "get_course_teachers", {"course_name": course_name}
            ),
            description="查询某门课程的任课教师。输入: 课程名称。",
        ),
        Tool(
            name="search_course_difficulty",
            func=lambda min_stars=0, max_stars=5, keyword="": executor.execute(
                "search_course_difficulty",
                {"min_stars": min_stars, "max_stars": max_stars, "keyword": keyword},
            ),
            description="按难度星级搜索课程。输入: min_stars(1-5), max_stars, keyword。",
        ),
        Tool(
            name="get_teacher_info",
            func=lambda teacher_name="": executor.execute(
                "get_teacher_info", {"teacher_name": teacher_name}
            ),
            description="查询教师的详细信息（学院、职称、研究方向等）。输入: 教师姓名。",
        ),
    ]
