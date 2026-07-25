from __future__ import annotations

import contextvars
import threading
import time
from collections import deque
from typing import Any

from .analytics import CourseHardnessAnalyzer, CreditChecker, ConflictResolver, ProfessorMatcher
from .data_store import QinmianDataStore
from .llm import LLMClient
from .personas import normalize_persona_id, persona_for, public_persona
from .planner import CareerPlanner


# ═════════════════════════════════════════════════════════════════════
# 对话记忆系统 (ConversationMemory)
# ═════════════════════════════════════════════════════════════════════

class ConversationMemory:
    """
    跟踪会话中的关键上下文信息，让 AI 具备"记忆"能力。
    
    记录的内容：
    - 最近 N 轮对话历史
    - 最后提到的课程名
    - 最后提到的专业 major_id
    - 最后提到的教师名
    - 最后触发的意图 (intent)
    - 已经讨论过的课程列表（避免重复推荐）
    """

    MAX_HISTORY = 12  # 最多记住 12 轮对话

    def __init__(self) -> None:
        self.history: deque[dict[str, str]] = deque(maxlen=self.MAX_HISTORY)
        self.last_course: str | None = None
        self.last_major_id: str | None = None
        self.last_teacher: str | None = None
        self.last_intent: str | None = None
        self.mentioned_courses: list[str] = []  # 对话中提及过的所有课程
        self.mentioned_majors: list[str] = []  # 对话中提及过的所有专业

    def add_turn(self, user_message: str, assistant_response: dict[str, Any]) -> None:
        """记录一轮对话"""
        self.history.append({
            "role": "user",
            "message": user_message,
            "timestamp": time.strftime("%H:%M:%S"),
        })
        intent = assistant_response.get("intent", "")
        answer = assistant_response.get("answer", "")
        self.history.append({
            "role": "assistant",
            "intent": intent,
            "answer": answer[:200],  # 截断避免太长
            "timestamp": time.strftime("%H:%M:%S"),
        })
        self.last_intent = intent

        # 从助手回复中提取课程名
        data = assistant_response.get("data", {})
        if isinstance(data, dict):
            course = data.get("course") or data.get("name") or ""
            if course and course not in self.mentioned_courses:
                self.last_course = course
                self.mentioned_courses.append(course)

            major = data.get("major") or data.get("selected_major")
            if isinstance(major, dict) and major.get("id"):
                self.last_major_id = major["id"]
                if major.get("display_name") and major["display_name"] not in self.mentioned_majors:
                    self.mentioned_majors.append(major["display_name"])

            teacher = data.get("teacher_name") or ""
            if teacher:
                self.last_teacher = teacher

            # 如果 data 中有显式的 course 字段（来自 hardness 分析）
            if "dimensions" in data and data.get("name"):
                cname = data["name"]
                if cname and cname not in self.mentioned_courses:
                    self.last_course = cname
                    self.mentioned_courses.append(cname)

    def get_recent_context(self, n: int = 4) -> str:
        """获取最近几轮对话的文本摘要"""
        recent = list(self.history)[-n*2:] if len(self.history) > n*2 else list(self.history)
        lines = []
        for turn in recent:
            if turn["role"] == "user":
                lines.append(f"用户: {turn['message']}")
            else:
                intent = turn.get("intent", "")
                answer = turn.get("answer", "")
                if answer:
                    lines.append(f"勤勉({intent}): {answer[:120]}")
        return "\n".join(lines)

    def get_context_summary(self) -> dict[str, Any]:
        """返回当前记忆摘要，供 agent 决策使用"""
        return {
            "last_course": self.last_course,
            "last_major_id": self.last_major_id,
            "last_teacher": self.last_teacher,
            "last_intent": self.last_intent,
            "mentioned_courses": self.mentioned_courses[-5:],  # 最近5个
            "mentioned_majors": self.mentioned_majors[-3:],
            "turn_count": len(self.history) // 2,
        }

    def has_discussed_course(self, course_name: str) -> bool:
        """检查是否已经讨论过某个课程"""
        return any(course_name in c or c in course_name for c in self.mentioned_courses)


# ═════════════════════════════════════════════════════════════════════
# 主代理类
# ═════════════════════════════════════════════════════════════════════

class QinmianAgent:
    def __init__(self, store: QinmianDataStore) -> None:
        self.store = store
        self.course_analyzer = CourseHardnessAnalyzer(store)
        self.professor_matcher = ProfessorMatcher(store)
        self.credit_checker = CreditChecker(store)
        self.conflict_resolver = ConflictResolver(store)
        self.career_planner = CareerPlanner(store)
        self.llm = LLMClient()
        self.memories: dict[str, ConversationMemory] = {}
        self._memory_lock = threading.RLock()
        self._current_memory: contextvars.ContextVar[ConversationMemory | None] = (
            contextvars.ContextVar("qinmian_current_memory", default=None)
        )
        self._request_context: contextvars.ContextVar[dict[str, Any]] = (
            contextvars.ContextVar("qinmian_request_context", default={})
        )
        self._persona_context: contextvars.ContextVar[str] = contextvars.ContextVar(
            "qinmian_persona_id",
            default="diligent",
        )
        self._last_message_context: contextvars.ContextVar[str] = contextvars.ContextVar(
            "qinmian_last_message",
            default="",
        )

    @property
    def memory(self) -> ConversationMemory:
        memory = self._current_memory.get()
        if memory is None:
            memory = self._memory_for("legacy:default")
            self._current_memory.set(memory)
        return memory

    def _memory_for(self, scope: str) -> ConversationMemory:
        with self._memory_lock:
            memory = self.memories.get(scope)
            if memory is None:
                memory = ConversationMemory()
                self.memories[scope] = memory
            return memory

    @property
    def _persona_id(self) -> str:
        return self._persona_context.get()

    @_persona_id.setter
    def _persona_id(self, value: str) -> None:
        self._persona_context.set(value)

    @property
    def _last_msg(self) -> str:
        return self._last_message_context.get()

    @_last_msg.setter
    def _last_msg(self, value: str) -> None:
        self._last_message_context.set(value)

    def respond(self, message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        user_id = str(context.get("user_id") or "legacy")
        conversation_id = str(context.get("conversation_id") or "default")
        self._current_memory.set(self._memory_for(f"{user_id}:{conversation_id}"))
        self._request_context.set(context)
        self._persona_id = normalize_persona_id(context.get("persona"))
        self._last_msg = message.strip()
        msg = self._last_msg

        # ── 从 context 和记忆中解析当前上下文 ──
        explicit_major_id = self._extract_major_id(msg)
        context_major_id = context.get("major_id")
        student_type = self._extract_student_type(msg) or self.store.normalize_student_type(context.get("student_type"))
        context_teacher_college = context.get("teacher_college")
        context_teacher_q = self._resolve_context_teacher_name(
            context.get("last_teacher_name") or context.get("teacher_q")
        )
        # 如果消息中没有显式提到专业，但 memory 中有，就沿用
        major_id = explicit_major_id or context_major_id or self.memory.last_major_id
        completed_courses = context.get("completed_courses") or []

        # ── 记忆增强：上下文感知 ──
        # 如果有历史课程上下文，且用户用代词指代，带入最近课程
        if self.memory.last_course and (
            "这门课" in msg or "该课程" in msg or "呢" in msg or "它" in msg
            or "这个课" in msg or "那门课" in msg
        ):
            implicit_course = self.memory.last_course
        else:
            implicit_course = None

        # 如果上一轮是 hardness 查询，且现在用户只说了课程名+"呢"，延续 hardness 意图
        last_intent = self.memory.last_intent
        course_only_followup = (
            last_intent == "course_hardness"
            and not self._is_small_talk(msg)
            and self._extract_course(msg)  # 消息中包含某个课程名
            and not self._mentions_teacher_request(msg)
        )

        if not msg:
            return self._local_chat(message, major_id)
        if self._is_small_talk(msg) or self._mentions_self_intro(msg):
            return self._local_chat(message, major_id)
        if self._mentions_teacher_request(msg) or self._extract_teacher_name(msg, allow_guess=False):
            return self._with_memory(message, self._teacher_request(
                message, explicit_major_id, context_major_id,
                context_teacher_college, context_teacher_q
            ))
        if self._mentions_major_choice(msg):
            return self._with_memory(message, self._general_major_choice(message))
        if self._mentions_major_catalog(msg) and not explicit_major_id:
            majors = self.store.list_majors(q=self._catalog_query(msg))[:16]
            if not majors:
                majors = self.store.list_majors()[:16]
            return self._with_memory(message, self._with_llm(message, {
                "intent": "major_catalog",
                "answer": self._major_catalog_answer(majors),
                "data": majors,
                "suggestions": ["计算机相关专业有哪些", "泉州校区有哪些专业", "推荐热门5个专业方向"],
            }, None, include_major_context=False))
        if self._mentions_hot(msg):
            data = self.store.hot_directions()
            return self._with_memory(message, self._with_llm(message, {
                "intent": "hot_directions",
                "answer": self._hot_answer(data),
                "data": data,
                "suggestions": ["按算法工程师生成4年课表", "查看计算机科学与技术", "比较人工智能和软件工程"],
            }, major_id))
        if self._mentions_seats(msg):
            course = self._extract_course(msg) or "机器学习"
            runtime_store = context.get("_runtime_store") or self.store
            data = runtime_store.add_watcher(course)
            return self._with_memory(message, self._with_llm(message, {
                "intent": "seat_watch",
                "answer": data["message"] + " 你也可以点“模拟释放名额”测试自动捡漏流程。",
                "data": data,
                "suggestions": ["模拟释放名额", "查看所有余位", "监控数据结构"],
            }, major_id))
        if self._mentions_professor(msg):
            course = self._extract_course(msg)
            if course and ("老师" in msg or "任课" in msg or "讲课" in msg):
                teachers = self.store.teachers_for_course(course)
                return self._with_memory(message, self._with_llm(message, {
                    "intent": "course_teachers",
                    "answer": self._course_teacher_answer(course, teachers),
                    "data": {"course": course, "teachers": teachers},
                    "suggestions": ["匹配机器学习方向老师", "查看教授论文相似度", "导入真实教师数据"],
                }, major_id))
            interest = msg.replace("教授", "").replace("老师", "").replace("匹配", "")
            data = self.professor_matcher.match(interest or msg, top_k=5)
            return self._with_memory(message, self._with_llm(message, {
                "intent": "professor_match",
                "answer": self._professor_answer(data),
                "data": data,
                "suggestions": ["我对NLP和大模型感兴趣", "我想做集成电路低功耗芯片", "查看机器学习任课老师"],
            }, major_id))
        if self._mentions_hardness(msg) or course_only_followup:
            course = self._extract_course(msg) or implicit_course or self.memory.last_course or "数据结构"
            data = self.course_analyzer.analyze(course)
            # 如果上一轮已经讨论过同一门课，补充一句"我们之前聊过"
            prefix = ""
            if self.memory.has_discussed_course(course):
                prefix = f"（之前讨论过 {course}，这次再深入分析一下）\n"
            answer = prefix + self._hardness_detailed_answer(data, self.memory.get_context_summary())
            return self._with_memory(message, self._with_llm(message, {
                "intent": "course_hardness",
                "answer": answer,
                "data": data,
                "suggestions": self._hardness_suggestions(data, course),
            }, major_id))
        if self._mentions_credit(msg):
            if not major_id:
                return self._with_memory(message, self._with_llm(message, {
                    "intent": "credit_check",
                    "answer": "先选一个专业，我才能按对应毕业学分分类做体检。你也可以直接说“人工智能学分体检”。",
                    "data": {},
                    "suggestions": ["人工智能学分体检", "软件工程毕业学分", "查看热门专业"],
                }, major_id))
            data = self.credit_checker.check(major_id, completed_courses, student_type)
            ui_actions = []
            if self._extract_student_type(msg):
                ui_actions.append({"type": "set_student_type", "student_type": student_type})
            if explicit_major_id:
                ui_actions.extend([{"type": "select_major", "major_id": explicit_major_id}, {"type": "switch_tab", "tab": "credits"}])
            return self._with_memory(message, self._with_llm(message, {
                "intent": "credit_check",
                "answer": self._credit_answer(data),
                "data": data,
                "suggestions": ["输入已修课程再体检", "查看专业必修课", "生成4年课表"],
                "ui_actions": ui_actions,
            }, major_id))
        if self._mentions_career_plan(msg):
            career = self._extract_role(msg)
            # 如果没提取到具体岗位，根据专业自动推断
            if not career and major_id:
                major = self.store.get_major(major_id)
                major_name = major.get("name", "") if major else ""
                # 按学科推断默认岗位
                career = self._infer_career_from_major(major_name)
            if not career:
                career = "软件工程师"
            data = self.career_planner.plan(career, major_id)
            return self._with_memory(message, self._with_llm(message, {
                "intent": "career_plan",
                "answer": self._career_answer(data),
                "data": data,
                "suggestions": ["算法工程师课表", "数据分析师课表", "集成电路工程师课表"],
            }, major_id))
        if explicit_major_id or self._mentions_curriculum_detail(msg) or self._asks_selected_major(msg, context_major_id):
            if not major_id:
                majors = self.store.list_majors(q=msg)[:10]
                return self._with_memory(message, self._with_llm(message, {
                    "intent": "major_search",
                    "answer": self._major_search_answer(majors),
                    "data": majors,
                    "suggestions": ["查看人工智能", "查看计算机科学与技术", "推荐热门5个方向"],
                }, major_id))
            data = self.store.curriculum_for(major_id, student_type)
            ui_actions = []
            if explicit_major_id:
                ui_actions = [{"type": "select_major", "major_id": explicit_major_id}, {"type": "switch_tab", "tab": "profile"}]
            if self._extract_student_type(msg):
                ui_actions.insert(0, {"type": "set_student_type", "student_type": student_type})
            return self._with_memory(message, self._with_llm(message, {
                "intent": "curriculum",
                "answer": self._curriculum_answer(data),
                "data": data,
                "suggestions": ["生成该专业4年课表", "做学分体检", "查看任课老师"],
                "ui_actions": ui_actions,
            }, major_id))
        majors = self.store.list_majors(q=msg)[:10]
        if majors:
            return self._with_memory(message, self._with_llm(message, {
                "intent": "major_search",
                "answer": self._major_search_answer(majors),
                "data": majors,
                "suggestions": ["查看毕业学分", "生成职业课表", "查看分流方向"],
            }, major_id))
        return self._with_memory(message, self._with_llm(message, {
            "intent": "free_chat",
            "answer": "我在。这个问题我可以先陪你聊；如果你想让我结合华侨大学专业、课程、学分或老师数据分析，也可以直接把目标说出来。",
            "data": {},
            "suggestions": ["你能做什么", "我想随便聊聊专业选择", "算法工程师4年课表"],
        }, None, include_major_context=False))

    def llm_status(self) -> dict[str, Any]:
        return self.llm.status()

    def _with_llm(
        self,
        message: str,
        response: dict[str, Any],
        major_id: str | None,
        include_major_context: bool = True,
    ) -> dict[str, Any]:
        persona_id = normalize_persona_id(getattr(self, "_persona_id", "diligent"))
        response = dict(response)
        response["persona"] = public_persona(persona_id)
        request_context = self._request_context.get({})
        if request_context.get("llm_enabled") is False:
            response["llm"] = self.llm.status()
            response["llm"]["used"] = False
            response["llm"]["reason"] = "disabled_for_user"
            return response
        if self._should_keep_exact_answer(response):
            response["llm"] = self.llm.status()
            response["llm"]["used"] = False
            response["llm"]["reason"] = "exact_local_data"
            return response
        major = self.store.get_major(major_id) if major_id and include_major_context else None
        return self.llm.enhance_answer(
            message,
            response,
            major,
            persona_id,
            chat_history=request_context.get("chat_history", []),
            long_term_memory=str(request_context.get("long_term_memory", "")),
        )

    def _with_memory(self, message: str, response: dict[str, Any]) -> dict[str, Any]:
        """记录本轮对话到记忆系统后返回"""
        self.memory.add_turn(message, response)
        return response

    def _hardness_detailed_answer(self, data: dict[str, Any], memory_summary: dict[str, Any]) -> str:
        """
        生成包含多维度解释的详细课程难度回答。
        比单纯的 summary 更丰富：解释每个维度含义、给出对比参考、提供学习建议。
        """
        stars = data.get("stars", 0)
        star_label = data.get("star_label", "未知")
        score = data.get("difficulty_score", 0)
        course = data.get("course") or data.get("name", "该课程")
        dims = data.get("dimensions", {})
        meta = data.get("meta", {})
        review_count = data.get("review_count", 0)

        # ── 各维度的中文解释 ──
        dim_explanations = {
            "credit_intensity": ("学分强度", "反映课业量大小，学分越高通常意味着课时更多、作业更重"),
            "category_difficulty": ("课程类别", "专业必修/学科基础类课程要求更高，通识类相对轻松"),
            "knowledge_complexity": ("知识复杂度", "课程名中专业术语密度，术语越多对背景知识要求越高"),
            "specialization": ("专业化程度", "面向专业越少说明课程越专精，对特定领域要求越深"),
            "teaching_intensity": ("教学强度", "师资投入力度，专业核心课通常有完整教学团队"),
            "review_score": ("评价反馈", "来自论坛/学长学姐的真实体验反馈"),
        }

        # ── 构建详细说明 ──
        lines = [f"{course} · {'⭐' * stars} {star_label}（综合难度 {score}/100）\n"]

        # 维度详情
        dim_lines = []
        for key, (label, desc) in dim_explanations.items():
            val = dims.get(key)
            if val is None:
                continue
            # 可视化指示
            if val >= 70:
                indicator = "🔴 较高"
            elif val >= 50:
                indicator = "🟡 中等"
            elif val >= 30:
                indicator = "🟢 较低"
            else:
                indicator = "⚪ 很低"
            dim_lines.append(
                f"  • {label}（{val}/100 {indicator}）：{desc}"
            )

        if dim_lines:
            lines.append("📊 各维度难度拆解：")
            lines.extend(dim_lines)
            lines.append("")

        # ── 综合评语和选课建议 ──
        advice_parts = []
        credits = meta.get("avg_credits", 0)
        teachers = meta.get("unique_teachers", 0)
        majors = meta.get("unique_majors", 0)
        category = meta.get("category", "")

        if credits:
            if credits >= 4:
                advice_parts.append(f"该课程 {credits} 学分，课业量较大，建议预留充足时间")
            elif credits >= 3:
                advice_parts.append(f"{credits} 学分属于中等偏上，需要保持稳定的学习节奏")
            elif credits <= 1.5:
                advice_parts.append(f"仅 {credits} 学分，课业负担相对轻松")

        if category in ("专业必修", "学科基础"):
            advice_parts.append("属于专业核心课程，对后续学习很重要，建议认真对待")
        elif category == "专业选修":
            advice_parts.append("属于专业选修课，可根据兴趣和职业方向选择性修读")
        elif category in ("通识必修", "通识选修"):
            advice_parts.append("属于通识类课程，跨专业友好，适合拓宽知识面")

        if majors >= 20:
            advice_parts.append(f"面向 {majors} 个专业开设，课程体系成熟，跨专业同学也可以选")
        elif majors <= 2:
            advice_parts.append(f"仅面向 {majors} 个专业，课程内容专精，建议确认有先修基础再选")

        # 星级对应的总结建议
        if stars == 5:
            advice_parts.append("💪 非常高难度的课程，建议做好心理准备，组队学习效果更好")
        elif stars == 4:
            advice_parts.append("📚 有一定挑战性，平时跟上节奏、不懂多问，可以取得不错成绩")
        elif stars == 3:
            advice_parts.append("👍 难度适中，正常投入即可，是积累学分的好选择")
        elif stars <= 2:
            advice_parts.append("😊 课程比较轻松，适合作为调节课业压力的选择")

        if review_count > 0:
            advice_parts.append(f"有 {review_count} 条论坛评价可以参考（见下方证据）")

        if advice_parts:
            lines.append("💡 分析与建议：")
            for part in advice_parts:
                lines.append(f"  • {part}")
            lines.append("")

        # ── 对比参考 ──
        lines.append(f"📈 数据参考：学分 {credits} | 教师 {teachers} 人 | 面向 {majors} 个专业")
        if memory_summary.get("mentioned_courses"):
            prev = memory_summary["mentioned_courses"]
            if len(prev) >= 2 and course not in prev:
                lines.append(f"💬 之前还讨论过：{'、'.join(prev[-3:])}，可以继续对比")

        return "\n".join(lines)

    def _hardness_suggestions(self, data: dict[str, Any], current_course: str) -> list[str]:
        """根据当前课程生成相关的建议选项"""
        suggestions = [
            f"分析另一门课难度",
            f"{current_course} 的任课老师",
            "查看课程评价",
        ]
        dims = data.get("dimensions", {})
        if dims:
            score = data.get("difficulty_score", 50)
            if score >= 60:
                suggestions.insert(0, "有没有轻松一点的同类课")
            elif score <= 40:
                suggestions.insert(0, "有没有类似但更有挑战的课")
        return suggestions

    def _should_keep_exact_answer(self, response: dict[str, Any]) -> bool:
        if response.get("intent") in {"curriculum", "credit_check"}:
            data = response.get("data") or {}
            rule = data.get("credit_rule") or {}
            return bool(rule) and not rule.get("is_template", True)
        if response.get("intent") not in {"teacher_roster_lookup", "faculty_profile_lookup", "course_teachers"}:
            return False
        data = response.get("data") or {}
        if data.get("courses"):
            return True
        return any(teacher.get("majors") for teacher in data.get("teachers", []) if isinstance(teacher, dict))

    def _mentions_hot(self, msg: str) -> bool:
        return any(word in msg for word in ["热门", "最火", "前景", "推荐方向", "5个专业方向", "五个专业方向"])

    def _extract_student_type(self, msg: str) -> str | None:
        if any(word in msg for word in ["境外生", "留学生", "华裔学生", "海外学生"]):
            return "international"
        if "境内生" in msg:
            return "domestic"
        return None

    def _mentions_seats(self, msg: str) -> bool:
        return any(word in msg for word in ["抢课", "捡漏", "余位", "监控", "名额"])

    def _mentions_professor(self, msg: str) -> bool:
        return any(word in msg for word in ["教授", "老师", "任课", "讲课", "论文", "研究方向", "导师"])

    def _mentions_teacher_request(self, msg: str) -> bool:
        teacher_words = [
            "任课老师",
            "任课教师",
            "讲课老师",
            "授课老师",
            "教师名单",
            "老师名单",
            "教师主页",
            "教师职称",
            "职称表",
            "有哪些老师",
            "哪些老师",
            "老师有哪些",
            "有哪些教师",
            "哪些教师",
            "教师有哪些",
        ]
        teacher_marks = ["老师", "教师", "导师"]
        rank_marks = ["职称", "教授", "副教授", "讲师", "研究员", "副研究员", "高级工程师", "实验师", "主页", "博导", "硕导", "博士生导师", "研究生导师"]
        roster_marks = ["哪些", "有哪些", "哪位", "谁", "任课", "讲课", "授课", "学院", "单位", "已排课", "未排课", "排课", *rank_marks]
        pronoun_followup = any(word in msg for word in ["他", "她", "这个老师", "该老师", "这个教师", "该教师"])
        rank_query = any(word in msg for word in rank_marks) and any(word in msg for word in ["哪些", "有哪些", "学院", "单位", "职称", "主页", "导师", "谁", "是"])
        # 单纯的"查看他的主页"这类代词跟进也要算
        simple_pronoun = pronoun_followup and any(word in msg for word in ["查看", "他的", "她的", "主页", "简介", "资料", "信息", "介绍", "学院", "在哪", "什么"])
        return any(word in msg for word in teacher_words) or rank_query or pronoun_followup or simple_pronoun or (
            any(word in msg for word in teacher_marks) and any(word in msg for word in roster_marks)
        )

    def _mentions_hardness(self, msg: str) -> bool:
        return any(word in msg for word in [
            "硬核", "作业", "给分", "干货", "课程评价", "水课", "难吗", "难度",
            "难不难", "好不好学", "好学吗", "容易吗", "轻松吗", "累吗",
            "怎么样", "评价", "怎么样呢",
        ])

    def _mentions_credit(self, msg: str) -> bool:
        return any(word in msg for word in ["学分体检", "毕业学分", "学分缺口", "毕业风险", "还差"])

    def _mentions_career_plan(self, msg: str) -> bool:
        role_names = self.store.career_doc["roles"].keys()
        # 如果消息同时提到"该专业"或"课程规划"，则优先识别为课程查询而非职业规划
        if any(word in msg for word in ["该专业", "这个专业", "课程规划", "课程安排"]):
            return False
        return (any(role in msg for role in role_names)
                or any(word in msg for word in ["岗位", "职业画像", "四年课表", "4年课表", "职业课表", "职业规划", "路线"])
                or (("课表" in msg) and ("四年" in msg or "4年" in msg or "职业" in msg or "岗位" in msg or any(role in msg for role in role_names))))

    def _mentions_curriculum(self, msg: str) -> bool:
        return any(word in msg for word in ["专业", "分流", "必修", "选修", "课程", "培养方案", "大类"])

    def _mentions_curriculum_detail(self, msg: str) -> bool:
        return any(word in msg for word in ["分流", "必修", "选修", "课程", "培养方案", "大类", "核心课", "学什么",
            "在哪个校区", "属于哪个学院", "课程规划", "课程安排", "学期安排", "课表",
            "大一", "大二", "大三", "大四", "大五", "第几学期"])

    def _mentions_major_choice(self, msg: str) -> bool:
        return any(
            word in msg
            for word in [
                "专业选择",
                "选专业",
                "怎么选专业",
                "如何选专业",
                "不知道选什么",
                "不知道学什么",
                "随便聊聊专业",
                "聊聊专业",
                "帮我选专业",
                "专业怎么选",
            ]
        )

    def _mentions_major_catalog(self, msg: str) -> bool:
        return "专业" in msg and any(word in msg for word in ["有哪些", "有什么", "列表", "全部", "所有", "相关"])

    def _catalog_query(self, msg: str) -> str:
        query = msg
        for word in ["有哪些", "有什么", "列表", "全部", "所有", "专业", "相关", "请问", "帮我查"]:
            query = query.replace(word, " ")
        return " ".join(query.split())

    def _asks_selected_major(self, msg: str, major_id: str | None) -> bool:
        if not major_id:
            return False
        if self._mentions_self_intro(msg):
            return False
        return any(word in msg for word in ["这个专业", "该专业", "当前专业", "怎么样", "适合我吗", "前景", "呢", "的课程", "课表"])

    def _mentions_self_intro(self, msg: str) -> bool:
        """检测是否为自我介绍请求"""
        compact = msg.strip().replace(" ", "")
        return any(p in compact for p in ["自我介绍", "介绍你自己", "介绍自己", "你是谁", "你能做什么", "你有什么功能", "你会什么", "能干什么"])

    def _is_small_talk(self, msg: str) -> bool:
        compact = msg.strip().lower().replace(" ", "")
        greetings = {
            "你好",
            "您好",
            "嗨",
            "hi",
            "hello",
            "hey",
            "在吗",
            "你在吗",
            "早上好",
            "下午好",
            "晚上好",
            "谢谢",
            "谢谢你",
            "好的",
            "好",
        }
        if compact in greetings:
            return True
        if compact.endswith("你好") and len(compact) <= 8:
            return True
        return False

    def _mentions_self_intro(self, msg: str) -> bool:
        """检测是否为自我介绍/功能询问"""
        compact = msg.strip().replace(" ", "")
        return any(p in compact for p in ["自我介绍", "介绍你自己", "介绍自己", "你是谁", "你能做什么", "你有什么功能", "你会什么", "能干什么", "介绍一下"])

    def _local_chat(self, message: str, major_id: str | None) -> dict[str, Any]:
        msg = message.strip()
        persona = persona_for(getattr(self, "_persona_id", "diligent"))
        if msg in {"谢谢", "谢谢你"}:
            answer = persona["thanks"]
        elif msg in {"你能做什么", "能做什么"}:
            answer = persona["capability"]
        else:
            answer = persona["hello"]
        return self._with_llm(message, {
            "intent": "small_talk",
            "answer": answer,
            "data": {},
            "suggestions": ["你能做什么", "推荐热门5个专业方向", "算法工程师怎么排课"],
        }, None, include_major_context=False)

    def _general_major_choice(self, message: str) -> dict[str, Any]:
        data = self.store.hot_directions()
        answer = (
            "可以，我们先不绑定某个专业。选专业我建议按四个维度看："
            "兴趣是否能长期投入、课程难度是否能接受、毕业出口是否清晰、是否愿意补对应技能。"
            "如果你偏技术和高薪，可以看人工智能/软件工程/集成电路；如果偏语言和跨文化，可以看日语、英语、汉语国际教育；"
            "如果偏管理和商业，可以看金融、工商管理、信息管理。你也可以告诉我你更喜欢“写代码、语言、设计、医学、管理、硬件”哪一类。"
        )
        return self._with_llm(message, {
            "intent": "general_major_choice",
            "answer": answer,
            "data": data,
            "suggestions": ["我喜欢语言类", "我想高薪就业", "我数学一般怎么选"],
        }, None, include_major_context=False)

    def _teacher_request(
        self,
        message: str,
        explicit_major_id: str | None,
        context_major_id: str | None,
        context_teacher_college: str | None,
        context_teacher_q: str | None,
    ) -> dict[str, Any]:
        msg = message.strip()
        college = self._extract_college(msg)
        scheduled = self._extract_scheduled_filter(msg)
        rank = self._extract_rank(msg)
        tutor = self._extract_tutor_filter(msg)
        teacher_name = self._extract_teacher_name(msg)
        wants_course_detail = self._asks_teacher_course_detail(msg)
        if not teacher_name and context_teacher_q and any(word in msg for word in ["他", "她", "这个老师", "该老师", "这个教师", "该教师"]):
            teacher_name = context_teacher_q
        if not college and scheduled and context_teacher_college and any(word in msg for word in ["这些", "这个学院", "该学院", "他们", "她们", "老师", "教师"]):
            college = context_teacher_college
        faculty_query = rank or tutor or any(word in msg for word in ["职称", "教师主页", "主页", "博导", "硕导", "博士生导师", "研究生导师"])
        if teacher_name and faculty_query:
            rows = self.store.faculty_profiles_by_name(teacher_name)
            courses = self.store.teacher_course_summary(teacher_name)
            response = {
                "intent": "faculty_profile_lookup",
                "answer": self._faculty_name_answer(teacher_name, rows, courses, include_courses=wants_course_detail),
                "data": {"teacher_name": teacher_name, "teachers": rows[:40], "total": len(rows), "courses": courses, "course_total": len(courses)},
                "suggestions": ["查看他的主页", "查看所在学院教授", "计算机学院副教授有哪些"],
                "ui_actions": [{"type": "set_faculty_profiles", "q": teacher_name}],
            }
            return self._with_llm(message, response, None, include_major_context=False)

        if faculty_query and (college or rank or tutor):
            rows = self.store.faculty_profiles(college=college or "", rank=rank, tutor=tutor)
            response = {
                "intent": "faculty_profiles",
                "answer": self._faculty_profiles_answer(college or "", rank, tutor, rows),
                "data": {"college": college or "", "rank": rank, "tutor": tutor, "teachers": rows[:80], "total": len(rows)},
                "suggestions": ["计算机学院教授有哪些", "某老师是什么职称", "博士生导师有哪些"],
                "ui_actions": [{"type": "set_faculty_profiles", "college": college or "", "rank": rank, "tutor": tutor}],
            }
            return self._with_llm(message, response, None, include_major_context=False)

        if college:
            rows = self.store.teacher_roster_by_college(college=college, scheduled=scheduled)
            response = {
                "intent": "college_teacher_roster",
                "answer": self._teacher_roster_answer(college, rows, scheduled),
                "data": {"college": college, "scheduled": scheduled, "teachers": rows[:80], "total": len(rows)},
                "suggestions": ["这些老师哪些已排课", "这些老师哪些未排课", "查某位老师在哪个学院"],
                "ui_actions": [{"type": "set_teacher_roster", "college": college, "scheduled": scheduled}],
            }
            return self._with_llm(message, response, None, include_major_context=False)

        if teacher_name:
            rows = self.store.teacher_roster_by_name(teacher_name)
            courses = self.store.teacher_course_summary(teacher_name)
            response = {
                "intent": "teacher_roster_lookup",
                "answer": self._teacher_name_answer(teacher_name, rows, courses, include_courses=wants_course_detail),
                "data": {"teacher_name": teacher_name, "teachers": rows[:40], "total": len(rows), "courses": courses, "course_total": len(courses)},
                "suggestions": ["查看他的主页", "他/她教哪些课", "查看所在学院老师名单"],
                "ui_actions": [{"type": "set_teacher_roster", "q": teacher_name}],
            }
            return self._with_llm(message, response, None, include_major_context=False)

        if explicit_major_id:
            major = self.store.get_major(explicit_major_id)
            major_college = major.get("college") if major else ""
            if major and major_college in self.store.teacher_roster_colleges():
                rows = self.store.teacher_roster_by_college(college=major_college, scheduled=scheduled)
                base_answer = self._teacher_roster_answer(major_college, rows, scheduled)
                response = {
                    "intent": "major_college_teacher_roster",
                    "answer": f"你问的是 {major['display_name']}。这批 Excel 是学院教师名单和是否已排课，不是具体专业/课程任课表，所以我先按所属学院列真实名单：{base_answer}",
                    "data": {"major": major, "college": major_college, "scheduled": scheduled, "teachers": rows[:80], "total": len(rows)},
                    "suggestions": ["这些老师哪些已排课", "查某位老师在哪个学院", f"{major_college}老师有哪些"],
                    "ui_actions": [{"type": "set_teacher_roster", "college": major_college, "scheduled": scheduled}],
                }
                return self._with_llm(message, response, None, include_major_context=False)

        if scheduled:
            response = {
                "intent": "teacher_roster_need_college",
                "answer": "可以查已排课或未排课老师，但我需要知道学院。你可以说“外国语学院哪些老师已排课”或“计算机学院未排课老师有哪些”。",
                "data": {"scheduled": scheduled},
                "suggestions": ["外国语学院哪些老师已排课", "计算机学院未排课老师有哪些", "医学院老师有哪些"],
            }
            return self._with_llm(message, response, None, include_major_context=False)

        course = self._extract_course(msg)
        if course:
            teachers = self.store.teachers_for_course(course)
            response = {
                "intent": "course_teachers",
                "answer": self._course_teacher_answer(course, teachers),
                "data": {"course": course, "teachers": teachers},
                "suggestions": ["查计算机相关专业老师", "匹配大模型方向老师", "查看教授匹配页"],
                "ui_actions": [{"type": "switch_tab", "tab": "professor"}, {"type": "set_teacher_course", "course": course}],
            }
            return self._with_llm(message, response, explicit_major_id or context_major_id)

        majors = self._majors_for_teacher_question(msg, explicit_major_id, context_major_id)
        rows = self._teacher_rows_for_majors(majors)
        response = {
            "intent": "major_teachers",
            "answer": self._major_teacher_answer(majors, rows),
            "data": {"majors": majors, "teachers": rows},
            "suggestions": ["机器学习是哪位老师", "计算机科学与技术课程有哪些", "匹配NLP方向老师"],
            "ui_actions": [{"type": "switch_tab", "tab": "professor"}],
        }
        return self._with_llm(message, response, explicit_major_id or None, include_major_context=bool(explicit_major_id))

    def _majors_for_teacher_question(
        self,
        msg: str,
        explicit_major_id: str | None,
        context_major_id: str | None,
    ) -> list[dict[str, Any]]:
        if explicit_major_id:
            major = self.store.get_major(explicit_major_id)
            return [major] if major else []
        if any(word in msg for word in ["计算机", "软件", "人工智能", "数据科学", "物联网", "信息安全"]):
            return self.store.list_majors(college="计算机科学与技术学院")
        if any(word in msg for word in ["这个专业", "当前专业", "该专业"]) and context_major_id:
            major = self.store.get_major(context_major_id)
            return [major] if major else []
        query = msg
        for word in ["有哪些", "哪些", "老师", "任课", "教师", "讲课", "授课", "专业"]:
            query = query.replace(word, " ")
        majors = self.store.list_majors(q=" ".join(query.split()))
        if majors:
            return majors[:6]
        if context_major_id:
            major = self.store.get_major(context_major_id)
            return [major] if major else []
        return []

    def _extract_college(self, msg: str) -> str | None:
        colleges = self.store.teacher_query_colleges()
        aliases = {
            "计算机学院": "计算机科学与技术学院",
            "计算机专业": "计算机科学与技术学院",
            "计算机相关": "计算机科学与技术学院",
            "外语学院": "外国语学院",
            "经金学院": "经济与金融学院",
            "工商学院": "工商管理学院",
            "机电学院": "机电及自动化学院",
            "信息学院": "信息科学与工程学院",
            "土木学院": "土木工程学院",
        }
        for alias, college in aliases.items():
            if alias in msg and college in colleges:
                return college
        for college in sorted(colleges, key=len, reverse=True):
            if college in msg:
                return college
        return None

    def _extract_rank(self, msg: str) -> str:
        ranks = sorted(self.store.faculty_profile_ranks(), key=len, reverse=True)
        for rank in ranks:
            if rank and rank in msg:
                return rank
        for rank in ["教授级高级工程师", "教授", "副教授", "讲师", "研究员", "副研究员", "高级工程师", "工程师", "实验师"]:
            if rank in msg:
                return rank
        return ""

    def _extract_tutor_filter(self, msg: str) -> str:
        if any(word in msg for word in ["博士生导师", "博导"]):
            return "doctor"
        if any(word in msg for word in ["研究生导师", "硕导", "导师"]):
            return "graduate"
        return ""

    def _extract_scheduled_filter(self, msg: str) -> str:
        if any(word in msg for word in ["未排课", "没排课", "没有排课", "未安排课", "没安排课"]):
            return "否"
        if any(word in msg for word in ["已排课", "有排课", "已经排课", "排了课", "安排了课"]):
            return "是"
        return ""

    def _asks_teacher_course_detail(self, msg: str) -> bool:
        return any(word in msg for word in ["教什么课", "教哪些课", "课程", "授课", "任课", "讲课", "教的课", "哪些课"])

    def _resolve_context_teacher_name(self, value: Any) -> str | None:
        if not value:
            return None
        text = str(value).strip()
        if not text or any(word in text for word in ["他", "她", "它", "查看", "主页"]):
            return None
        known = self._extract_teacher_name(text, allow_guess=False)
        if known:
            return known
        if self.store.teacher_roster_by_name(text) or self.store.faculty_profiles_by_name(text) or self.store.teacher_course_assignments(text):
            return text
        return None

    def _extract_teacher_name(self, msg: str, allow_guess: bool = True) -> str | None:
        teachers = [{"name": name, "teacher_id": ""} for name in self.store.all_teacher_names()]
        teachers.extend(list(self.store.teacher_roster_doc.get("teachers", [])))
        teachers.extend(list(self.store.faculty_profiles_doc.get("teachers", [])))
        for teacher in sorted(teachers, key=lambda row: len(row.get("name", "")), reverse=True):
            name = teacher.get("name", "").strip()
            teacher_id = teacher.get("teacher_id", "").strip()
            if name and len(name) >= 2 and name in msg:
                return name
            if teacher_id and teacher_id in msg:
                return teacher_id
        if not allow_guess or any(word in msg for word in ["他", "她", "这个老师", "该老师", "这个教师", "该教师"]):
            return None
        cleaned = msg
        for word in [
            "请问",
            "帮我查",
            "查一下",
            "查询",
            "查看",
            "打开",
            "看一下",
            "老师",
            "教师",
            "导师",
            "的",
            "在哪个学院",
            "属于哪个学院",
            "哪个学院",
            "所在单位",
            "是什么职称",
            "职称是什么",
            "什么职称",
            "教师主页",
            "主页",
            "官网吗",
            "是否已排课",
            "有排课吗",
            "已排课吗",
            "排课吗",
            "吗",
            "？",
            "?",
        ]:
            cleaned = cleaned.replace(word, " ")
        cleaned = " ".join(cleaned.split()).strip()
        if 2 <= len(cleaned) <= 16 and not any(
            word in cleaned for word in ["学院", "专业", "课程", "哪些", "有哪些", "哪位", "谁", "任课", "授课", "讲课", "教", "是"]
        ):
            return cleaned
        return None

    def _teacher_rows_for_majors(self, majors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        teacher_map: dict[str, dict[str, Any]] = {}
        for major in majors:
            if not major:
                continue
            try:
                curriculum = self.store.curriculum_for(major["id"])
            except KeyError:
                continue
            for course in curriculum["courses"]:
                for teacher in course.get("teachers", []):
                    if teacher.get("id") == "pending":
                        continue
                    key = teacher["id"]
                    row = teacher_map.setdefault(
                        key,
                        {
                            "id": teacher["id"],
                            "name": teacher["name"],
                            "college": teacher.get("college", ""),
                            "title": teacher.get("title", ""),
                            "courses": set(),
                            "majors": set(),
                        },
                    )
                    row["courses"].add(course["name"])
                    row["majors"].add(major["display_name"])
        rows = []
        for row in teacher_map.values():
            rows.append(
                {
                    **row,
                    "courses": sorted(row["courses"]),
                    "majors": sorted(row["majors"]),
                }
            )
        return sorted(rows, key=lambda item: (item["college"], item["name"]))[:12]

    def _course_teacher_answer(self, course: str, teachers: list[dict[str, str]]) -> str:
        names = [teacher["name"] for teacher in teachers if teacher.get("id") != "pending"]
        if not names:
            return f"{course} 目前没有导入真实任课老师，页面显示的是“待导入任课教师”。你可以导入教务任课表后再查。"
        details = []
        for teacher in teachers:
            if teacher.get("id") == "pending":
                continue
            majors = teacher.get("majors") or []
            major_text = f"，面向{'、'.join(majors)}" if majors else ""
            credits = teacher.get("credits")
            credit_text = f"{credits}学分，" if credits not in (None, "") else ""
            details.append(f"{teacher['name']}（{credit_text}{teacher.get('college', '')}{major_text}）")
        return f"{course} 目前匹配到 {len(details)} 条任课教师记录：{'；'.join(details)}。数据来自你导入的课程信息汇总表，仍建议以教务系统最新排课为准。"

    def _major_teacher_answer(self, majors: list[dict[str, Any]], rows: list[dict[str, Any]]) -> str:
        if not majors:
            return "我还没识别出你想查哪个专业。你可以说“计算机相关专业有哪些任课老师”或“日语专业有哪些老师”。"
        major_names = "、".join(major["display_name"] for major in majors[:6])
        if not rows:
            return f"{major_names} 目前没有导入真实任课老师数据。课程能查到，但老师需要导入教务任课表后才准确。"
        teacher_bits = []
        for row in rows[:8]:
            course_text = "、".join(row["courses"][:4])
            teacher_bits.append(f"{row['name']}({course_text})")
        return f"按当前演示/导入数据，{major_names} 相关任课老师包括：{'；'.join(teacher_bits)}。真实任课安排请以后导入教务任课表校准。"

    def _teacher_roster_answer(self, college: str, rows: list[dict[str, Any]], scheduled_filter: str = "") -> str:
        if not rows:
            label = "已排课" if scheduled_filter == "是" else "未排课" if scheduled_filter == "否" else ""
            return f"我在导入的教师名单里没有找到 {college} 的{label}教师记录。"
        scheduled = sum(1 for row in rows if row.get("scheduled") == "是")
        unique_names = list(dict.fromkeys(row["name"] for row in rows if row.get("name")))
        label = "已排课" if scheduled_filter == "是" else "未排课" if scheduled_filter == "否" else "教师"
        names = "、".join(unique_names[:30])
        suffix = "。" if len(unique_names) <= 30 else f"……（共{len(unique_names)}位）"
        return f"{college} 在你导入的真实教师名单里匹配到 {len(rows)} 条{label}记录，去重后约 {len(unique_names)} 位教师，其中标记已排课 {scheduled} 条。\n\n{names}{suffix}\n\n完整列表可在「教授匹配」页面的教师名单中查看。"

    def _teacher_courses_text(self, courses: list[dict[str, Any]], limit: int | None = None) -> str:
        if not courses:
            return ""
        bits = []
        selected = courses if limit is None else courses[:limit]
        for course in selected:
            majors = course.get("majors", [])
            major_text = "、".join(majors[:5]) if majors else "未标注专业"
            if len(majors) > 5:
                major_text += f"等{len(majors)}个专业"
            bits.append(f"{course.get('course')}（{course.get('credits')}学分，专业：{major_text}）")
        suffix = "" if limit is None or len(courses) <= limit else f"；另外还有 {len(courses) - limit} 门课程"
        return f"课程信息汇总表显示其授课包括：{'；'.join(bits)}{suffix}。"

    def _teacher_name_answer(
        self,
        teacher_name: str,
        rows: list[dict[str, Any]],
        courses: list[dict[str, Any]] | None = None,
        include_courses: bool = False,
    ) -> str:
        courses = courses or []
        course_text = self._teacher_courses_text(courses, limit=10)
        if not rows:
            base = f"我在导入的真实教师名单里没有找到“{teacher_name}”的教师号记录"
            if course_text:
                return f"{base}，但在课程信息汇总表里找到其授课记录：\n{course_text}"
            return f"{base}。你可以换用完整姓名或教师号再查。"
        items = []
        for row in rows[:8]:
            gender = row.get("gender") or "未填性别"
            scheduled = row.get("scheduled") or "未标注"
            items.append(f"{row.get('name')}：{row.get('college')}，教师号 {row.get('teacher_id')}，{gender}，是否已排课：{scheduled}")
        suffix = "" if len(rows) <= 8 else f"\n（另外还有 {len(rows) - 8} 条同名/匹配记录）"
        parts = [f"我在真实教师名单里找到 {len(rows)} 条与“{teacher_name}”相关的记录："]
        parts.append('；'.join(items))
        if suffix:
            parts.append(suffix)
        if course_text:
            parts.append(f"课程数据：\n{course_text}")
        return '\n'.join(parts)

    def _faculty_profiles_answer(self, college: str, rank: str, tutor: str, rows: list[dict[str, Any]]) -> str:
        if not rows:
            parts = [item for item in [college, rank, self._tutor_label(tutor)] if item]
            condition = "、".join(parts) or "该条件"
            return f"我在华侨大学教师主页公开职称表里没有找到“{condition}”对应的教师。"
        parts = [item for item in [college, rank, self._tutor_label(tutor)] if item]
        condition = "、".join(parts) or "全部教师"
        names = []
        for row in rows[:40]:
            college_text = "、".join(row.get("colleges", [])[:2]) or row.get("unit_raw", "")
            tutor_bits = "、".join(bit for bit in [row.get("doctor_tutor"), row.get("graduate_tutor")] if bit)
            extra = f"，{tutor_bits}" if tutor_bits else ""
            names.append(f"{row.get('name')}({row.get('title') or '未标注职称'}，{college_text}{extra})")
        suffix = "。" if len(rows) <= 40 else f"……（只展示前40位，共{len(rows)}条）"
        return f"按华侨大学教师主页公开数据，{condition} 共匹配到 {len(rows)} 位教师：{'；'.join(names)}{suffix}"

    def _faculty_name_answer(
        self,
        teacher_name: str,
        rows: list[dict[str, Any]],
        courses: list[dict[str, Any]] | None = None,
        include_courses: bool = False,
    ) -> str:
        courses = courses or []
        course_text = self._teacher_courses_text(courses, limit=None) if include_courses else ""
        if not rows:
            if course_text:
                return f"我在华侨大学教师主页公开职称表里没有找到“{teacher_name}”，但课程信息汇总表里有授课数据。{course_text}"
            return f"我在华侨大学教师主页公开职称表里没有找到“{teacher_name}”。可以换完整姓名再查。"
        items = []
        for row in rows[:5]:
            colleges = "、".join(row.get("colleges", [])[:3]) or row.get("unit_raw", "") or "未标注单位"
            tutor_bits = "、".join(bit for bit in [row.get("doctor_tutor"), row.get("graduate_tutor")] if bit) or "未标注导师身份"
            homepage = row.get("homepage") or ""
            base_info = f"{row.get('name')}：{row.get('title') or '未标注职称'}，{colleges}，{tutor_bits}"
            if homepage:
                items.append(f"{base_info}\n教师主页：{homepage}")
            else:
                items.append(f"{base_info}（未提供主页）")
        suffix = "" if len(rows) <= 5 else f"\n（另外还有 {len(rows) - 5} 条同名/匹配记录）"
        course_hint = f"\n课程信息汇总表另匹配到 {len(courses)} 门授课课程。" if courses and not include_courses else ""
        return f"我在华侨大学教师主页公开数据里找到 {len(rows)} 条与“{teacher_name}”相关的记录：\n{'；'.join(items)}{suffix}{course_text or course_hint}"

    def _tutor_label(self, tutor: str) -> str:
        if tutor == "doctor":
            return "博士生导师"
        if tutor == "graduate":
            return "研究生导师"
        return ""

    def _extract_role(self, msg: str) -> str:
        # 1. 精确匹配已知岗位
        for role in self.store.career_doc["roles"]:
            if role in msg:
                return role

        # 2. 匹配标记词
        for marker in ["岗位", "职业", "想做", "目标"]:
            if marker in msg:
                return msg.split(marker, 1)[-1].strip(" ：:，。")

        # 3. "课表"查询：提取课表前面的词作为目标岗位
        for marker in ["课表", "路线", "规划"]:
            if marker in msg:
                # 取 marker 前面的内容作为候选
                parts = msg.split(marker, 1)[0].strip("生成该专业四年年 ")
                if parts and len(parts) >= 2:
                    return parts
                break

        return ""

    # ── 专业→默认岗位 全覆盖映射 ──────────────────────────────
    _CAREER_MAP = {
        # ===== 计算机/IT =====
        '计算机科学与技术': '算法工程师',
        '软件工程': '软件工程师',
        '人工智能': '算法工程师',
        '数据科学与大数据技术': '数据分析师',
        '信息安全': '网络安全工程师',
        '物联网工程': '软件工程师',
        '集成电路设计与集成系统': '集成电路工程师',
        '信息管理与信息系统': '数据分析师',
        '数字出版': '新媒体运营',
        # ===== 电子/通信/自动化 =====
        '电子科学与技术': '集成电路工程师',
        '通信工程': '通信工程师',
        '光电信息科学与工程': '通信工程师',
        '电气工程及其自动化': '电气工程师',
        '自动化': '电气工程师',
        '智能制造工程': '智能制造工程师',
        '机器人': '智能制造工程师',
        # ===== 机械/车辆 =====
        '机械工程': '机械工程师',
        '机械设计': '机械工程师',
        '车辆工程': '机械工程师',
        '工业设计': '设计师',
        # ===== 土木/建筑/规划 =====
        '土木工程': '土木工程师',
        '给排水科学与工程': '土木工程师',
        '城市地下空间工程': '土木工程师',
        '建筑学': '建筑师',
        '城乡规划': '建筑师',
        '风景园林': '建筑师',
        '工程管理': '项目经理',
        # ===== 材料/化工/生物 =====
        '材料科学与工程': '材料工程师',
        '高分子材料与工程': '材料工程师',
        '新能源材料与器件': '材料工程师',
        '化学工程与工艺': '化学工程师',
        '应用化学': '化学工程师',
        '制药工程': '化学工程师',
        '生物工程': '医疗健康专员',
        '环境工程': '环境工程师',
        # ===== 数学/物理 =====
        '数学与应用数学': '数据分析师',
        '应用物理学': '科研人员',
        # ===== 金融/经济/管理 =====
        '金融学': '金融分析师',
        '经济学': '金融分析师',
        '国际经济与贸易': '金融分析师',
        '国际商务': '金融分析师',
        '电子商务': '新媒体运营',
        '工商管理': '产品经理',
        '市场营销': '产品经理',
        '人力资源管理': '项目经理',
        '财务管理': '金融分析师',
        '会计学': '金融分析师',
        '行政管理': '项目经理',
        '会展经济与管理': '旅游与酒店管理师',
        '旅游管理': '旅游与酒店管理师',
        '酒店管理': '旅游与酒店管理师',
        # ===== 法学/哲学/国际关系 =====
        '法学': '律师',
        '哲学': '文化创意策划师',
        '国际事务与国际关系': '律师',
        # ===== 文学/语言/教育 =====
        '汉语言文学': '教师',
        '汉语国际教育': '教师',
        '英语': '翻译',
        '翻译': '翻译',
        '日语': '翻译',
        '新闻学': '新媒体运营',
        '广播电视学': '新媒体运营',
        # ===== 艺术/设计/体育 =====
        '美术学': '设计师',
        '视觉传达设计': '设计师',
        '产品设计': '设计师',
        '音乐学': '教师',
        '舞蹈学': '教师',
        '运动训练': '教师',
        # ===== 医学/药学 =====
        '临床医学': '医疗健康专员',
        '药学': '医疗健康专员',
    }

    def _infer_career_from_major(self, major_name: str) -> str:
        """根据专业名称推断默认目标岗位（全覆盖）"""
        # 1. 精确匹配完整专业名（优先）
        if major_name in self._CAREER_MAP:
            return self._CAREER_MAP[major_name]

        # 2. 关键词匹配（按长度降序，避免短词误匹配）
        keywords = sorted(self._CAREER_MAP.keys(), key=len, reverse=True)
        for kw in keywords:
            if kw in major_name:
                return self._CAREER_MAP[kw]

        # 3. 按学科门类兜底
        if any(k in major_name for k in ["工程", "技术", "科学"]):
            return "工程师"
        if any(k in major_name for k in ["管理", "商务", "贸易", "经济"]):
            return "管理/商务专员"
        if any(k in major_name for k in ["文学", "语言", "教育", "新闻"]):
            return "教师/编辑/翻译"
        if any(k in major_name for k in ["设计", "艺术", "视觉", "产品"]):
            return "设计师"
        if any(k in major_name for k in ["医学", "药学", "临床", "制药"]):
            return "医疗/医药专员"

        return "软件工程师"

    def _extract_course(self, msg: str) -> str | None:
        for name in sorted(self.store.all_course_names(), key=len, reverse=True):
            if name and name in msg:
                return name
        return None

    def _extract_major_id(self, msg: str) -> str | None:
        for major in sorted(self.store.majors, key=lambda m: len(m["display_name"]), reverse=True):
            if major["display_name"] in msg or major["name"] in msg:
                return major["id"]
        return None

    def _hot_answer(self, data: list[dict[str, Any]]) -> str:
        names = "、".join(f"{item['rank']}.{item['name']}" for item in data[:5])
        return f"勤勉推荐当前最值得关注的5个方向：{names}。这些方向按产业热度、技能迁移性和华侨大学2026专业覆盖度综合排序。"

    def _professor_answer(self, rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "暂未匹配到教师数据。"
        top = rows[0]
        return f"最匹配的是 {top['name']}，相似度 {top['similarity']}，方向包括：{'、'.join(top['research_interests'])}。"

    def _credit_answer(self, data: dict[str, Any]) -> str:
        risk = "；".join(data["risk_points"][:4]) if data["risk_points"] else "暂无明显缺口"
        rule = data.get("credit_rule", {})
        label = rule.get("student_type_label", "境内生")
        source_text = "真实表格" if not rule.get("is_template", True) else "内置模板"
        validation = rule.get("validation", {})
        source_warning = " 注意：源表分类学分合计与总学分不一致。" if validation.get("matches_graduation_total") is False else ""
        return f"{data['major']['display_name']}（{label}）按{source_text}的毕业总学分要求为 {data['graduation_total']}。当前识别已修 {data['total_earned']} 学分，总缺口 {data['total_gap']} 学分；风险点：{risk}。{source_warning}"

    def _career_answer(self, data: dict[str, Any]) -> str:
        major = data["selected_major"]
        top_majors = "、".join(row["major"]["display_name"] for row in data["recommended_majors"][:4])
        return f"我把你的目标识别为“{data['matched_role']}”。建议优先看：{top_majors}。当前按 {major['display_name']} 生成 {data['semester_count']} 学期路线，核心课包括：{'、'.join(data['must_courses'][:6])}。"

    def _extract_year(self, msg: str) -> int | None:
        """从消息中提取年级/学年（大一=1, 大二=2, ...）"""
        for y in range(1, 6):
            if f"大{'一二三四五'[y-1]}" in msg:
                return y
        return None

    def _extract_semester(self, msg: str) -> int | None:
        """从消息中提取具体学期（第3学期→3）"""
        import re
        m = re.search(r"第(\d+)学期", msg)
        if m:
            return int(m.group(1))
        return None

    def _curriculum_answer(self, data: dict[str, Any]) -> str:
        major = data["major"]
        rule = data["credit_rule"]
        courses = data.get("courses", [])
        label = rule.get("student_type_label", "境内生")
        source_text = "真实表格要求" if not rule.get("is_template", True) else "内置模板（真实表格未匹配）"
        validation = rule.get("validation", {})
        source_warning = " 源表分类学分合计与总学分存在差异，请以学院最终培养方案复核。" if validation.get("matches_graduation_total") is False else ""

        # 详细课程说明 + 难度星级
        course_library = {
            "高等数学A": ("微积分、极限、导数与积分，理工科各专业的核心数学工具，为后续课程奠定计算基础", "⭐⭐⭐⭐"),
            "高等数学B": ("微积分与常微分方程，偏重计算应用，适合工程类专业学生的数学基础课", "⭐⭐⭐"),
            "线性代数": ("向量空间、矩阵运算与线性变换，机器学习与数据科学的重要数学基础", "⭐⭐⭐"),
            "概率论与数理统计": ("随机事件、概率分布与统计推断，数据分析与AI决策的核心数学基础", "⭐⭐⭐"),
            "大学物理": ("经典力学、电磁学、热学与光学，培养科学思维与实验分析能力", "⭐⭐⭐⭐"),
            "大学物理实验": ("通过实验验证物理定律，培养数据采集、误差分析与报告撰写能力", "⭐⭐"),
            "程序设计基础": ("C/C++/Python语言入门，培养编程思维、算法逻辑与代码调试能力", "⭐⭐⭐"),
            "数据结构": ("数组、链表、栈、队列、树、图等核心数据结构及其算法实现", "⭐⭐⭐⭐"),
            "计算机组成原理": ("CPU、内存、IO等硬件体系结构，理解程序在硬件层面的执行过程", "⭐⭐⭐⭐"),
            "操作系统": ("进程管理、内存管理、文件系统，理解计算机系统资源管理核心", "⭐⭐⭐⭐"),
            "计算机网络": ("TCP/IP协议栈、网络拓扑与数据传输原理，掌握网络编程基础", "⭐⭐⭐"),
            "建筑设计基础": ("建筑空间认知与设计表达入门，训练设计思维与手绘表达能力", "⭐⭐⭐"),
            "建筑制图": ("正投影、剖面与透视图绘制规范，掌握建筑设计图纸的专业表达", "⭐⭐⭐"),
            "建筑构造": ("建筑构造原理与施工工艺，连接建筑设计与工程实践的关键课程", "⭐⭐⭐"),
            "城市规划原理": ("城市空间结构、用地规划与交通组织，理解城市发展规律与方法", "⭐⭐"),
            "建筑设计 studio": ("贯穿全年的综合设计实践，从概念到方案完成完整建筑设计项目", "⭐⭐⭐⭐⭐"),
            "建筑物理": ("建筑热工、声学与光学环境分析，掌握绿色建筑与节能设计原理", "⭐⭐⭐"),
            "中外建筑史": ("从古埃及到现代主义建筑的发展历程，理解建筑风格演变脉络", "⭐⭐"),
            "建筑力学": ("静力学与材料力学基础，为建筑结构设计提供理论支撑", "⭐⭐⭐⭐"),
            "大学英语": ("综合英语听说读写训练，提升学术英语交流与文献阅读能力", "⭐⭐"),
            "大学体育": ("各类体育运动项目训练，增强体质并培养团队合作精神", "⭐"),
            "思想道德与法治": ("思想品德修养与法律基础，培养正确的价值观与法治意识", "⭐"),
            "中国近现代史纲要": ("中国近现代历史发展脉络，理解中华民族伟大复兴的历史逻辑", "⭐"),
            "马克思主义基本原理": ("马克思主义哲学与政治经济学基本原理，培养科学世界观", "⭐⭐"),
            "军事理论与训练": ("国防知识教育与基础军事技能训练，增强国家安全意识", "⭐⭐"),
            "创新创业基础": ("创新思维与创业流程训练，培养商业计划书撰写能力", "⭐⭐"),
            "社会实践": ("深入社会开展调研与服务，培养社会责任感与实践能力", "⭐⭐"),
            "海外华文文化": ("中华文化概况与海外传播，拓展跨文化交流视野与全球意识", "⭐"),
            "公共表达与沟通": ("演讲技巧与沟通策略，提升公共场合的表达与说服能力", "⭐⭐"),
            "人工智能伦理": ("AI技术中的隐私与公平议题，培养科技伦理与社会责任意识", "⭐"),
            "科技论文写作": ("学术论文结构与写作规范，为毕业设计与科研论文打下基础", "⭐⭐"),
            "智慧建造专题": ("BIM与智能建造技术前沿，了解建筑行业数字化转型趋势", "⭐⭐"),
            "历史街区保护": ("历史文化遗产保护理论与方法，学习城市更新中的文化保育策略", "⭐⭐"),
            "毕业论文/设计": ("综合运用所学完成独立研究或设计，检验大学阶段的学习成果", "⭐⭐⭐⭐⭐"),
            "建筑学导论": ("建筑学专业概况与职业发展路径，帮助新生建立专业认知框架", "⭐"),
            "建筑学研究方法": ("建筑领域科研方法与论文写作指导，为毕业设计研究做准备", "⭐⭐"),
            "小学期实践": ("短学期实习或社会实践，培养实际操作能力与团队协作精神", "⭐"),
            "毛泽东思想": ("马克思主义中国化的重要理论成果与中国特色社会主义实践", "⭐"),
        }

        # 按学期分组
        semesters = {}
        for c in courses:
            s = c.get("semester", 99)
            semesters.setdefault(s, []).append(c)

        # 检测是否需要按年级或具体学期筛选
        year = self._extract_year(getattr(self, "_last_msg", "")) if hasattr(self, "_last_msg") else None
        semester = self._extract_semester(getattr(self, "_last_msg", "")) if hasattr(self, "_last_msg") else None
        if semester is not None:
            # 具体学期：只显示该学期
            target_sem = semester
            filtered = {}
            if target_sem in semesters:
                filtered[target_sem] = semesters[target_sem]
            semesters = filtered
            year_label = None
            semester_label = f"第{semester}学期"
        elif year is not None:
            # 三年制/学年：除最后一年外每年3个学期（小学期制）
            # 五年制建筑学：大一[1,2,3] 大二[4,5,6] 大三[7,8,9] 大四[10,11,12] 大五[13,14]
            year_sems = {1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12], 5: [13, 14]}
            target = year_sems.get(year, [])
            filtered = {}
            for s in sorted(semesters.keys()):
                if s in target:
                    filtered[s] = semesters[s]
            semesters = filtered
            year_label = f"大{'一二三四五'[year-1]}"
            semester_label = None
        else:
            year_label = None
            semester_label = None
            year_label = None

        def course_desc(c):
            name = c.get("name", "")
            credits = c.get("credits", 0)
            if name in course_library:
                tip, stars = course_library[name]
                return f"{name}（{credits}学分）{stars}\n     {tip}"
            cat = c.get("category", "")
            return f"{name}（{credits}学分，{cat}）"

        # 构建回答（含人格风格）
        persona_id = normalize_persona_id(getattr(self, "_persona_id", "diligent"))
        from .personas import PERSONAS
        p = PERSONAS.get(persona_id, PERSONAS["diligent"])
        persona_tag = f"[{p['name']}]"
        parts = [f"🏛 【{major['display_name']}】专业分析 {persona_tag}"]
        parts.append(f"所属学院：{major['college']}｜校区：{major['campus']}")
        parts.append(f"学制：{major.get('duration', '四年制')}")
        DISPLAY_DISCIPLINES = {
            "computer": "计算机科学与技术",
            "software": "软件工程",
            "ai": "人工智能",
            "electronic": "电子信息",
            "electrical": "电气工程",
            "mechanical": "机械工程",
            "civil": "土木工程",
            "architecture": "建筑学",
            "material": "材料科学",
            "chemistry": "化学化工",
            "medicine": "医学",
            "pharmacy": "药学",
            "business": "工商管理",
            "economics": "经济学",
            "law": "法学",
            "language": "外国语言文学",
            "media": "新闻传播",
            "art": "艺术设计",
            "math": "数学",
            "physics": "物理学",
            "philosophy": "哲学",
            "education": "教育学",
            "sports": "体育学",
        }
        disp = DISPLAY_DISCIPLINES.get(major.get('discipline', ''), major.get('discipline', '未分类'))
        parts.append(f"学科门类：{disp}")
        parts.append(f"毕业学分：{rule['graduation_total']}（{label}，{source_text}）{source_warning}")

        if semester_label:
            parts.append(f"\n📅 【{semester_label}课程详情】")
        elif year_label:
            parts.append(f"\n📅 【{year_label}课程规划】")
        else:
            parts.append("\n📅 【各学期完整课程规划】")

        if semesters:
            # 检查3学期制下是否有缺失的学期（小学期）
            for sem in sorted(semesters.keys()):
                if sem > 15:
                    continue
                clist = semesters[sem]
                parts.append(f"\n  ── 第{sem}学期（{len(clist)}门课）──")
                for c in clist[:10]:
                    parts.append(f"  {course_desc(c)}")
                if len(clist) > 10:
                    parts.append(f"  ...另有{len(clist)-10}门")
            # 如果是按年级查询，补充小学期
            if year_label and year is not None:
                year_third_sem = {1: 3, 2: 6, 3: 9, 4: 12, 5: 14}
                ts = year_third_sem.get(year)
                if ts and ts not in semesters:
                    # 自动插入小学期实践课程
                    summer_course = {
                        "name": "小学期实践",
                        "credits": 2,
                        "category": "实践与创新",
                        "semester": ts,
                    }
                    semesters[ts] = [summer_course]
                    clist = semesters[ts]
                    parts.append(f"\n  ── 第{ts}学期（小学期 · {len(clist)}门课）──")
                    parts.append(f"  {course_desc(summer_course)}")
        else:
            parts.append("  该年级暂无详细课程数据。")

        parts.append("\n📋 【分类学分要求】")
        for cat_name, cat_val in rule.get("categories", {}).items():
            parts.append(f"  {cat_name}：{cat_val}学分")

        return "\n".join(parts)

    def _major_search_answer(self, majors: list[dict[str, Any]]) -> str:
        if not majors:
            return "暂未找到匹配专业。"
        names = "、".join(m["display_name"] for m in majors[:8])
        return f"找到 {len(majors)} 个相关专业：{names}。你可以点开专业查看分流方向、毕业学分、必修课和选修课。"

    def _major_catalog_answer(self, majors: list[dict[str, Any]]) -> str:
        if not majors:
            return "暂时没有筛到专业。你可以换个关键词，比如“计算机相关专业有哪些”或“泉州校区有哪些专业”。"
        names = "、".join(f"{m['display_name']}({m['college']})" for m in majors[:12])
        return f"我先按你的问题列出这些专业：{names}。你想了解哪一个，我再展开讲课程、学分和就业方向。"
