"""
勤勉 AI — Flask 应用入口 v4
============================
新增功能：
  - 知识库长期记忆（KnowledgeBase）
  - 对话持久化存储（ConversationStore）
  - 知识库/大模型独立开关
  - 对话历史管理（创建、查询、删除）
  - 全屏 AI 助手页面（赛博朋克风格）
"""

from __future__ import annotations

import base64
import binascii
import datetime
import io
import json
import mimetypes
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import flask
from flask import Flask, Response, g, jsonify, request, session, stream_with_context
from flask_cors import CORS

from qinmian.agent import QinmianAgent
from qinmian.analytics import (
    ConflictResolver,
    CourseDifficultyDB,
    CourseHardnessAnalyzer,
    CreditChecker,
    ProfessorMatcher,
)
from qinmian.auth_store import (
    UserStore,
    load_or_create_session_secret,
    user_data_path,
)
from qinmian.conversation_store import (
    add_message,
    create_conversation,
    delete_conversation,
    delete_message,
    get_conversation,
    get_or_create_active,
    list_conversations,
    rename_conversation,
)
from qinmian.data_store import PROJECT_ROOT, QinmianDataStore
from qinmian.knowledge_base import KnowledgeBase
from qinmian.personas import public_personas
from qinmian.planner import CareerPlanner
from qinmian.tools import FunctionCallExecutor, get_function_schemas
from qinmian.user_runtime import UserRuntimeStoreManager

# ── Flask 应用 ───────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(PROJECT_ROOT / "static"), static_url_path="")
app.config.update(
    SECRET_KEY=load_or_create_session_secret(),
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=14),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("QINMIAN_COOKIE_SECURE", "0").lower()
    in {"1", "true", "yes", "on"},
)

cors_origins = [
    origin.strip()
    for origin in os.getenv("QINMIAN_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if cors_origins:
    CORS(
        app,
        resources={r"/api/*": {"origins": cors_origins}},
        supports_credentials=True,
    )

# ── 全局单例 ─────────────────────────────────────────────────────────
STORE = QinmianDataStore()
AGENT = QinmianAgent(STORE)
USER_STORE = UserStore()
_KNOWLEDGE_BASES: dict[str, KnowledgeBase] = {}
_KNOWLEDGE_LOCK = threading.RLock()
COURSE_ANALYZER = CourseHardnessAnalyzer(STORE)
COURSE_DIFFICULTY = CourseDifficultyDB()
PROF_MATCHER = ProfessorMatcher(STORE)
CREDIT_CHECKER = CreditChecker(STORE)
CONFLICT_RESOLVER = ConflictResolver(STORE)
CAREER_PLANNER = CareerPlanner(STORE)
FC_EXECUTOR = FunctionCallExecutor(STORE)
USER_RUNTIME_STORES = UserRuntimeStoreManager(STORE)


# ═════════════════════════════════════════════════════════════════════
# 工具函数
# ═════════════════════════════════════════════════════════════════════

def _query_arg(key: str, default: str = "") -> str:
    return request.args.get(key, default)


def _query_int(key: str, default: int = 0) -> int:
    try:
        return int(request.args.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _body_json() -> dict[str, Any]:
    return request.get_json(silent=True) or {}


def _langchain_available() -> bool:
    try:
        import langchain  # noqa
        return True
    except ImportError:
        return False


def _current_user_id() -> str:
    user = getattr(g, "current_user", None)
    if not user:
        raise RuntimeError("authentication required")
    return str(user["id"])


def _knowledge_base_for(user_id: str | None = None) -> KnowledgeBase:
    owner_id = user_id or _current_user_id()
    with _KNOWLEDGE_LOCK:
        knowledge_base = _KNOWLEDGE_BASES.get(owner_id)
        if knowledge_base is None:
            store_path = user_data_path(owner_id) / "knowledge_base" / "records.json"
            knowledge_base = KnowledgeBase(store_path, owner_id=owner_id)
            knowledge_base.index_major_catalog(STORE)
            _KNOWLEDGE_BASES[owner_id] = knowledge_base
        return knowledge_base


def _llm_status_for_user() -> dict[str, Any]:
    status = dict(AGENT.llm_status())
    configured = bool(status.get("enabled"))
    user_enabled = bool(session.get("llm_enabled", True))
    status["configured"] = configured
    status["user_enabled"] = user_enabled
    status["enabled"] = configured and user_enabled
    return status


@app.before_request
def load_authenticated_user():
    user_id = str(session.get("user_id", ""))
    g.current_user = USER_STORE.get(user_id) if user_id else None
    if user_id and not g.current_user:
        session.clear()

    if not request.path.startswith("/api/"):
        return None
    if request.path.startswith("/api/auth/"):
        return None
    if not g.current_user:
        return jsonify({"error": "请先登录", "code": "authentication_required"}), 401
    return None


# ═════════════════════════════════════════════════════════════════════
# 静态文件与前端入口
# ═════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return flask.send_from_directory(app.static_folder, "index.html")


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "qinmian-ai-v4",
        "major_count": len(STORE.majors),
        "model_configured": AGENT.llm_status().get("enabled", False),
    })


# ═════════════════════════════════════════════════════════════════════
# API: 用户认证
# ═════════════════════════════════════════════════════════════════════

def _start_user_session(user: dict[str, Any]) -> None:
    session.clear()
    session.permanent = True
    session["user_id"] = user["id"]
    session["llm_enabled"] = True


@app.route("/api/auth/me")
def api_auth_me():
    if not g.current_user:
        return jsonify({
            "authenticated": False,
            "registration_available": True,
            "user_count": USER_STORE.count(),
        })
    return jsonify({
        "authenticated": True,
        "user": g.current_user,
    })


@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    body = _body_json()
    password = str(body.get("password", ""))
    confirmation = str(body.get("password_confirm", password))
    if password != confirmation:
        return jsonify({"error": "两次输入的密码不一致"}), 400
    try:
        user, _ = USER_STORE.register(body.get("username", ""), password)
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if message == "用户名已存在" else 400
        return jsonify({"error": message}), status_code
    _start_user_session(user)
    return jsonify({
        "status": "ok",
        "user": user,
        "inherited_legacy_data": False,
    }), 201


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    body = _body_json()
    user = USER_STORE.authenticate(body.get("username", ""), body.get("password", ""))
    if not user:
        return jsonify({"error": "用户名或密码错误"}), 401
    _start_user_session(user)
    return jsonify({"status": "ok", "user": user})


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    session.clear()
    return jsonify({"status": "ok"})


# ═════════════════════════════════════════════════════════════════════
# API: 元数据
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/meta")
def api_meta():
    knowledge_base = _knowledge_base_for()
    llm_status = _llm_status_for_user()
    return jsonify({
        "name": "勤勉",
        "source": STORE.majors_doc["source"],
        "campuses": STORE.campuses(),
        "colleges": STORE.colleges(),
        "disciplines": STORE.disciplines(),
        "major_count": len(STORE.majors),
        "faculty": STORE.faculty_profiles_doc.get("source", {}),
        "personas": public_personas(),
        "llm": llm_status,
        "knowledge_base": knowledge_base.status(),
        "user": g.current_user,
        "features": {
            "flask": True,
            "sse": True,
            "function_calling": bool(llm_status.get("enabled")),
            "langchain_available": _langchain_available(),
            "knowledge_base": True,
            "conversations": True,
        },
    })


# ═════════════════════════════════════════════════════════════════════
# API: 专业
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/majors")
def api_majors():
    return jsonify(
        STORE.list_majors(
            q=_query_arg("q"),
            campus=_query_arg("campus"),
            college=_query_arg("college"),
            discipline=_query_arg("discipline"),
        )
    )


@app.route("/api/majors/<path:major_id>")
def api_major(major_id: str):
    major = STORE.get_major(major_id)
    if not major:
        return jsonify({"error": "major not found"}), 404
    return jsonify(major)


@app.route("/api/curriculum/<path:major_id>")
def api_curriculum(major_id: str):
    try:
        return jsonify(STORE.curriculum_for(major_id, _query_arg("student_type", "domestic")))
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


# ═════════════════════════════════════════════════════════════════════
# API: 热门方向
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/hot")
def api_hot():
    return jsonify(STORE.hot_directions())


# ═════════════════════════════════════════════════════════════════════
# API: 余位监控
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/seats")
def api_seats():
    user_store = USER_RUNTIME_STORES.get(_current_user_id())
    return jsonify({
        "offerings": user_store.offerings(),
        "watchers": user_store.watchers,
        "events": user_store.events[-12:],
    })


@app.route("/api/seats/watch", methods=["POST"])
def api_seats_watch():
    body = _body_json()
    user_id = _current_user_id()
    user_store = USER_RUNTIME_STORES.get(user_id)
    result = user_store.add_watcher(
        body.get("course", "机器学习"),
        body.get("student", g.current_user["username"]),
    )
    USER_RUNTIME_STORES.save(user_id)
    return jsonify(result)


@app.route("/api/seats/tick", methods=["POST"])
def api_seats_tick():
    user_id = _current_user_id()
    user_store = USER_RUNTIME_STORES.get(user_id)
    result = user_store.tick_seats()
    USER_RUNTIME_STORES.save(user_id)
    return jsonify(result)


# ═════════════════════════════════════════════════════════════════════
# API: 教师信息
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/professors")
def api_professors():
    course = _query_arg("course")
    if course:
        return jsonify({"course": course, "teachers": STORE.teachers_for_course(course)})
    return jsonify(STORE.professors_doc)


@app.route("/api/teacher-roster")
def api_teacher_roster():
    rows = STORE.teacher_roster_by_college(
        college=_query_arg("college"),
        q=_query_arg("q"),
        scheduled=_query_arg("scheduled"),
    )
    limit = _query_int("limit", 200)
    teachers = rows if limit < 0 else rows[:limit]
    q = _query_arg("q")
    if q:
        teachers = [STORE.enrich_teacher_row(row) for row in teachers]
    return jsonify({
        "colleges": STORE.teacher_roster_colleges(),
        "teachers": teachers,
        "total": len(rows),
    })


@app.route("/api/faculty-profiles")
def api_faculty_profiles():
    rows = STORE.faculty_profiles(
        college=_query_arg("college"),
        rank=_query_arg("rank"),
        q=_query_arg("q"),
        tutor=_query_arg("tutor"),
    )
    limit = _query_int("limit", 200)
    teachers = rows if limit < 0 else rows[:limit]
    return jsonify({
        "source": STORE.faculty_profiles_doc.get("source", {}),
        "colleges": STORE.faculty_profile_colleges(),
        "ranks": STORE.faculty_profile_ranks(),
        "teachers": teachers,
        "total": len(rows),
    })


# ═════════════════════════════════════════════════════════════════════
# API: 课程难度
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/difficulty")
def api_difficulty():
    course = _query_arg("course")
    if course:
        return jsonify(COURSE_DIFFICULTY.for_course_detail(course))
    return jsonify(COURSE_DIFFICULTY.full_stats())


@app.route("/api/difficulty/search")
def api_difficulty_search():
    q = _query_arg("q")
    top_k = _query_int("top_k", 20)
    return jsonify(COURSE_DIFFICULTY.search(q, top_k) if q else [])


@app.route("/api/difficulty/top")
def api_difficulty_top():
    k = _query_int("k", 20)
    return jsonify(COURSE_DIFFICULTY.top_hardest(k))


# ═════════════════════════════════════════════════════════════════════
# API: LLM / 知识库 状态与开关
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/llm/status")
def api_llm_status():
    return jsonify(_llm_status_for_user())


@app.route("/api/llm/toggle", methods=["POST"])
def api_llm_toggle():
    """切换当前登录用户的大模型启用状态"""
    body = _body_json()
    enabled = body.get("enabled")
    if enabled is not None:
        session["llm_enabled"] = bool(enabled)
    return jsonify(_llm_status_for_user())


@app.route("/api/knowledge/status")
def api_knowledge_status():
    status = _knowledge_base_for().status()
    status.update({
        "total_majors": len(STORE.majors),
        "coverage_complete": status.get("majors_indexed") == len(STORE.majors),
    })
    return jsonify(status)


@app.route("/api/knowledge/toggle", methods=["POST"])
def api_knowledge_toggle():
    """切换知识库（长期记忆）启用状态"""
    body = _body_json()
    enabled = body.get("enabled")
    knowledge_base = _knowledge_base_for()
    if enabled is not None:
        knowledge_base.set_enabled(bool(enabled))
    return jsonify(knowledge_base.status())


@app.route("/api/knowledge/search")
def api_knowledge_search():
    """搜索知识库"""
    q = _query_arg("q", "")
    top_k = _query_int("top_k", 5)
    results = _knowledge_base_for().search(q, top_k=top_k)
    return jsonify({
        "query": q,
        "results": results,
        "total": len(results),
    })


@app.route("/api/knowledge/records")
def api_knowledge_records():
    """列出知识库所有记录"""
    limit = _query_int("limit", 100)
    knowledge_base = _knowledge_base_for()
    return jsonify({
        "records": knowledge_base.all_records(limit=limit),
        "total": knowledge_base.count(),
    })


@app.route("/api/knowledge/clear", methods=["POST"])
def api_knowledge_clear():
    """清空当前用户的对话记忆，保留公共专业知识索引"""
    knowledge_base = _knowledge_base_for()
    count = knowledge_base.clear_conversation_memories()
    return jsonify({"status": "ok", "cleared": count})


# ═════════════════════════════════════════════════════════════════════
# API: 对话管理 (Conversations)
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/conversations")
def api_conversations():
    """列出所有会话"""
    limit = _query_int("limit", 50)
    user_id = _current_user_id()
    conversations = list_conversations(limit=limit, user_id=user_id)
    return jsonify({
        "conversations": conversations,
        "total": len(list_conversations(limit=500, user_id=user_id)),
    })


@app.route("/api/conversations", methods=["POST"])
def api_conversations_create():
    """创建新会话"""
    body = _body_json()
    title = body.get("title", "")
    conv = create_conversation(title=title, user_id=_current_user_id())
    return jsonify(conv), 201


@app.route("/api/conversations/<conv_id>")
def api_conversations_get(conv_id: str):
    """获取单条会话"""
    conv = get_conversation(conv_id, user_id=_current_user_id())
    if not conv:
        return jsonify({"error": "conversation not found"}), 404
    return jsonify(conv)


@app.route("/api/conversations/<conv_id>", methods=["DELETE"])
def api_conversations_delete(conv_id: str):
    """删除会话"""
    user_id = _current_user_id()
    ok = delete_conversation(conv_id, user_id=user_id)
    if not ok:
        return jsonify({"error": "conversation not found"}), 404
    _knowledge_base_for().delete_conversation_memories(conv_id)
    return jsonify({"status": "ok", "deleted": conv_id})


@app.route("/api/conversations/<conv_id>/rename", methods=["POST"])
def api_conversations_rename(conv_id: str):
    """重命名会话"""
    body = _body_json()
    new_title = body.get("title", "").strip()
    if not new_title:
        return jsonify({"error": "title is required"}), 400
    result = rename_conversation(conv_id, new_title, user_id=_current_user_id())
    if not result:
        return jsonify({"error": "conversation not found"}), 404
    return jsonify(result)


@app.route("/api/conversations/<conv_id>/messages", methods=["POST"])
def api_conversations_add_message(conv_id: str):
    """向会话追加消息"""
    body = _body_json()
    role = body.get("role", "user")
    content = body.get("content", "")
    if not content:
        return jsonify({"error": "content is required"}), 400
    result = add_message(conv_id, role, content, user_id=_current_user_id())
    if not result:
        return jsonify({"error": "conversation not found"}), 404
    return jsonify(result)


@app.route("/api/conversations/<conv_id>/messages/<int:msg_index>", methods=["DELETE"])
def api_conversations_delete_message(conv_id: str, msg_index: int):
    """删除会话中的单条消息"""
    result = delete_message(conv_id, msg_index, user_id=_current_user_id())
    if not result:
        return jsonify({"error": "message or conversation not found"}), 404
    return jsonify(result)


# ═════════════════════════════════════════════════════════════════════
# API: 静态数据
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/static-data/<name>")
def api_static_data(name: str):
    safe = Path(name).name
    return jsonify(STORE.__dict__.get(safe, {}))


# ═════════════════════════════════════════════════════════════════════
# API: Function Calling Schema
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/functions")
def api_functions():
    return jsonify({
        "functions": get_function_schemas(),
        "langchain_available": _langchain_available(),
    })


@app.route("/api/functions/execute", methods=["POST"])
def api_functions_execute():
    body = _body_json()
    name = body.get("name", "")
    arguments = body.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid arguments JSON"}), 400

    result = FC_EXECUTOR.execute(name, arguments)
    try:
        return jsonify(json.loads(result))
    except (json.JSONDecodeError, TypeError):
        return jsonify({"result": result})


# ═════════════════════════════════════════════════════════════════════
# API: 聊天端点（增强版 — 集成知识库长期记忆）
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    标准聊天端点（非流式）。
    
    新增特性：
    - 支持 conversation_id 实现多会话管理
    - 集成知识库长期记忆（自动检索相关上下文）
    - 自动存储对话到知识库
    """
    body = _body_json()
    message = body.get("message", "")
    context = body.get("context", {})
    conv_id = body.get("conversation_id", "") or context.get("conversation_id", "")
    user_id = _current_user_id()
    knowledge_base = _knowledge_base_for(user_id)

    # 获取或创建活跃会话
    conv = get_or_create_active(conv_id if conv_id else None, user_id=user_id)
    conv_id = conv["id"]

    # 增强上下文：注入知识库长期记忆
    kb_enabled = knowledge_base.enabled and bool(context.get("knowledge_base_enabled", True))
    kb_context = ""
    if kb_enabled and len(message.strip()) > 4:
        kb_context = knowledge_base.get_relevant_context(
            message,
            max_items=3,
            conversation_id=conv_id,
        )

    # 将知识库记忆注入上下文
    enhanced_context = dict(context)
    if kb_context:
        enhanced_context["long_term_memory"] = kb_context
    enhanced_context["conversation_id"] = conv_id
    enhanced_context["user_id"] = user_id
    enhanced_context["knowledge_base_enabled"] = kb_enabled
    enhanced_context["llm_enabled"] = bool(session.get("llm_enabled", True))
    enhanced_context["_runtime_store"] = USER_RUNTIME_STORES.get(user_id)

    # 调用 Agent
    result = AGENT.respond(message, enhanced_context)
    if result.get("intent") == "seat_watch":
        USER_RUNTIME_STORES.save(user_id)

    # 存储到对话记录
    add_message(conv_id, "user", message, user_id=user_id)
    add_message(
        conv_id,
        "assistant",
        result.get("answer", ""),
        user_id=user_id,
    )

    # 存储到知识库（长期记忆）
    if kb_enabled:
        knowledge_base.store(
            user_message=message,
            assistant_answer=result.get("answer", ""),
            conversation_id=conv_id,
            metadata={
                "intent": result.get("intent", ""),
                "major_id": enhanced_context.get("major_id", ""),
            },
        )

    result["conversation_id"] = conv_id
    return jsonify(result)


@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    """
    SSE 流式聊天端点。
    支持多会话 + 知识库长期记忆。
    """
    body = _body_json()
    message = body.get("message", "")
    context = body.get("context", {})
    conv_id = body.get("conversation_id", "") or context.get("conversation_id", "")
    user_id = _current_user_id()
    knowledge_base = _knowledge_base_for(user_id)

    conv = get_or_create_active(conv_id if conv_id else None, user_id=user_id)
    conv_id = conv["id"]

    # 知识库上下文
    kb_context = ""
    kb_enabled = knowledge_base.enabled and bool(context.get("knowledge_base_enabled", True))
    if kb_enabled and len(message.strip()) > 4:
        kb_context = knowledge_base.get_relevant_context(
            message,
            max_items=3,
            conversation_id=conv_id,
        )

    enhanced_context = dict(context)
    if kb_context:
        enhanced_context["long_term_memory"] = kb_context
    enhanced_context["conversation_id"] = conv_id
    enhanced_context["user_id"] = user_id
    enhanced_context["knowledge_base_enabled"] = kb_enabled
    enhanced_context["llm_enabled"] = bool(session.get("llm_enabled", True))
    enhanced_context["_runtime_store"] = USER_RUNTIME_STORES.get(user_id)

    def generate():
        yield _sse("meta", {"status": "started", "message": message, "conversation_id": conv_id})

        add_message(conv_id, "user", message, user_id=user_id)

        llm_status = _llm_status_for_user()
        if llm_status.get("enabled") and _langchain_available():
            yield from _stream_with_agent(
                message,
                enhanced_context,
                llm_status,
                conv_id,
                user_id,
                knowledge_base,
            )
        else:
            yield from _stream_local(
                message,
                enhanced_context,
                conv_id,
                user_id,
                knowledge_base,
            )

        yield _sse("meta", {"status": "done"})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _stream_local(
    message: str,
    context: dict[str, Any],
    conv_id: str,
    user_id: str,
    knowledge_base: KnowledgeBase,
):
    """本地模式流式响应"""
    result = AGENT.respond(message, context)
    if result.get("intent") == "seat_watch":
        USER_RUNTIME_STORES.save(user_id)
    answer = result.get("answer", "")
    intent = result.get("intent", "")
    data = result.get("data", {})

    yield _sse("intent", {"intent": intent})

    import re
    sentences = re.split(r"(?<=[。！？\n])", answer)
    for sentence in sentences:
        if sentence.strip():
            yield _sse("token", {"token": sentence})
            time.sleep(0.05)

    yield _sse("result", {
        "intent": intent,
        "data": data,
        "answer": answer,
    })

    # 存储到知识库
    if context.get("knowledge_base_enabled"):
        knowledge_base.store(
            message,
            answer,
            conversation_id=conv_id,
            metadata={"intent": intent},
        )
    add_message(conv_id, "assistant", answer, user_id=user_id)


def _stream_with_agent(
    message: str,
    context: dict[str, Any],
    llm_status: dict[str, Any],
    conv_id: str,
    user_id: str,
    knowledge_base: KnowledgeBase,
):
    """LLM 模式流式响应"""
    try:
        from langchain.agents import AgentExecutor, create_openai_functions_agent
        from langchain.schema import SystemMessage, HumanMessage, AIMessage
        from langchain_openai import ChatOpenAI
        from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder

        llm = ChatOpenAI(
            model=llm_status.get("model", "gpt-4o-mini"),
            openai_api_key=AGENT.llm.api_key,
            openai_api_base=AGENT.llm.base_url,
            temperature=0.3,
            streaming=True,
        )

        tools = _build_langchain_tools()
        if not tools:
            yield _sse("error", {"error": "无法初始化 LangChain 工具"})
            return

        # 构建带有知识库记忆的系统提示
        kb_context = context.get("long_term_memory", "")
        memory_section = (
            f"\n\n【长期记忆参考】\n{kb_context}\n"
            if kb_context else ""
        )
        system_prompt = (
            "你是华侨大学学业规划 AI「勤勉」。你可以使用以下工具来回答用户的问题。\n"
            "工具会返回 JSON 结果，请根据结果用中文给出自然、清晰的回答。\n"
            "不要编造未提供的数据。如果工具返回空结果，诚实地告诉用户。\n"
            "回答要简短、清晰、适合学生继续追问。\n"
            f"{memory_section}"
        )

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            HumanMessage(content="{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_openai_functions_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            max_iterations=5,
            handle_parsing_errors=True,
        )

        chat_history = context.get("chat_history", [])
        messages = [SystemMessage(content=system_prompt)]
        for turn in chat_history[-6:]:
            if turn.get("role") == "user":
                messages.append(HumanMessage(content=turn.get("text", "")))
            elif turn.get("role") == "assistant":
                messages.append(AIMessage(content=turn.get("text", "")))

        messages.append(HumanMessage(content=message))

        full_answer = ""
        for chunk in agent_executor.stream({"input": message, "chat_history": chat_history[-6:]}):
            if "output" in chunk:
                token = chunk["output"]
                if token and len(token) > len(full_answer):
                    new_part = token[len(full_answer):]
                    if new_part:
                        yield _sse("token", {"token": new_part})
                    full_answer = token
            elif "intermediate_step" in chunk:
                for step in chunk["intermediate_step"]:
                    if len(step) >= 2:
                        tool_name = step[0].tool if hasattr(step[0], "tool") else ""
                        tool_input = step[0].tool_input if hasattr(step[0], "tool_input") else ""
                        yield _sse("function_call", {
                            "tool": str(tool_name),
                            "input": str(tool_input)[:200],
                        })

        yield _sse("result", {"answer": full_answer})

        if context.get("knowledge_base_enabled"):
            knowledge_base.store(
                message,
                full_answer,
                conversation_id=conv_id,
                metadata={"intent": "agent"},
            )
        add_message(conv_id, "assistant", full_answer, user_id=user_id)

    except ImportError as e:
        yield _sse("error", {
            "error": f"LangChain 未安装或导入失败: {str(e)}",
            "hint": "请安装: pip install langchain langchain-openai",
        })
    except Exception as e:
        yield _sse("error", {"error": f"Agent 执行异常: {str(e)}"})


def _build_langchain_tools() -> list:
    try:
        from langchain.tools import Tool
        return [
            Tool(
                name="analyze_course_hardness",
                func=lambda c="": FC_EXECUTOR.execute("analyze_course_hardness", {"course_name": c}),
                description="分析课程难度 (输入: 课程名称)",
            ),
            Tool(
                name="search_majors",
                func=lambda q="": FC_EXECUTOR.execute("search_majors", {"query": q}),
                description="搜索专业 (输入: 关键词)",
            ),
            Tool(
                name="get_curriculum",
                func=lambda m="": FC_EXECUTOR.execute("get_curriculum", {"major_id": m}),
                description="查询培养方案 (输入: 专业ID)",
            ),
            Tool(
                name="match_professor",
                func=lambda i="": FC_EXECUTOR.execute("match_professor", {"interest": i}),
                description="匹配研究方向对应的老师 (输入: 研究方向)",
            ),
            Tool(
                name="plan_career",
                func=lambda c="": FC_EXECUTOR.execute("plan_career", {"career": c}),
                description="职业规划 (输入: 目标岗位)",
            ),
            Tool(
                name="get_course_teachers",
                func=lambda c="": FC_EXECUTOR.execute("get_course_teachers", {"course_name": c}),
                description="查询课程任课老师 (输入: 课程名称)",
            ),
            Tool(
                name="search_course_difficulty",
                func=lambda k="": FC_EXECUTOR.execute("search_course_difficulty", {"keyword": k}),
                description="按关键词搜索课程难度",
            ),
        ]
    except ImportError:
        return []


# ═════════════════════════════════════════════════════════════════════
# API: 其他 POST 端点
# ═════════════════════════════════════════════════════════════════════

@app.route("/api/plan", methods=["POST"])
def api_plan():
    body = _body_json()
    return jsonify(
        CAREER_PLANNER.plan(body.get("career", "算法工程师"), body.get("major_id"))
    )


@app.route("/api/course/analyze", methods=["POST"])
def api_course_analyze():
    body = _body_json()
    return jsonify(
        COURSE_ANALYZER.analyze(body.get("course", "数据结构"), body.get("reviews") or [])
    )


@app.route("/api/conflicts", methods=["POST"])
def api_conflicts():
    body = _body_json()
    return jsonify(
        CONFLICT_RESOLVER.resolve(body.get("major_id", ""), body.get("selected_courses", []))
    )


@app.route("/api/professors/match", methods=["POST"])
def api_professors_match():
    body = _body_json()
    return jsonify(
        PROF_MATCHER.match(body.get("interest_text", ""), int(body.get("top_k", 5)))
    )


@app.route("/api/credits/check", methods=["POST"])
def api_credits_check():
    body = _body_json()
    return jsonify(
        CREDIT_CHECKER.check(
            body.get("major_id", ""),
            body.get("completed_courses", []),
            body.get("student_type", "domestic"),
        )
    )


@app.route("/api/import/teacher-schedule", methods=["POST"])
def api_import_teacher_schedule():
    body = _body_json()
    return jsonify(
        STORE.import_teacher_schedule_text(body.get("text", ""), bool(body.get("replace", False)))
    )


@app.route("/api/import/demo", methods=["POST"])
def api_import_demo():
    body = _body_json()
    imported = {}
    if "reviews" in body:
        STORE.reviews_doc["reviews"].extend(body["reviews"])
        imported["reviews"] = len(body["reviews"])
    if "professors" in body:
        STORE.professors_doc["professors"].extend(body["professors"])
        imported["professors"] = len(body["professors"])
    if "offerings" in body:
        STORE.seat_doc["offerings"].extend(body["offerings"])
        imported["offerings"] = len(body["offerings"])
    return jsonify({"status": "ok", "imported": imported})


# ═════════════════════════════════════════════════════════════════════
# 错误处理
# ═════════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": str(e)}), 500


# ═════════════════════════════════════════════════════════════════════
# API: 图片/文件上传分析
# ═════════════════════════════════════════════════════════════════════

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
TIMETABLE_PROMPT = (
    "你是华侨大学课表与学业文件分析助手。请读取用户上传的内容，提取所有能确认的课程信息。\n"
    "要求：\n"
    "1. 课程字段包含 name、day、start、end、category、semester。\n"
    "2. day 统一为周一到周日，时间统一为 HH:MM；无法确认的字段留空，不要编造。\n"
    "3. intent 只能是 conflict、career_plan、curriculum、credit_check、general 之一。\n"
    "4. summary 简要说明识别结果和不确定项。\n"
    "5. 只返回一个合法 JSON 对象，不要使用 Markdown 代码块。\n"
    '返回格式：{"intent":"conflict","courses":[{"name":"课程名","day":"周一",'
    '"start":"08:00","end":"09:40","category":"专业必修","semester":1}],'
    '"summary":"...","career":"","major":""}'
)


def _parse_llm_json(answer: str) -> dict[str, Any]:
    cleaned = answer.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        try:
            parsed, _ = decoder.raw_decode(cleaned[match.start():])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return {"intent": "general", "summary": cleaned, "courses": []}


def _normalize_analysis_result(result: dict[str, Any]) -> dict[str, Any]:
    normalized_courses = []
    day_aliases = {
        "星期一": "周一", "星期二": "周二", "星期三": "周三", "星期四": "周四",
        "星期五": "周五", "星期六": "周六", "星期日": "周日", "星期天": "周日",
        "Monday": "周一", "Tuesday": "周二", "Wednesday": "周三", "Thursday": "周四",
        "Friday": "周五", "Saturday": "周六", "Sunday": "周日",
    }
    for course in result.get("courses", []) if isinstance(result.get("courses"), list) else []:
        if not isinstance(course, dict) or not str(course.get("name", "")).strip():
            continue
        day = str(course.get("day", "")).strip()
        normalized_courses.append({
            "name": str(course.get("name", "")).strip(),
            "day": day_aliases.get(day, day),
            "start": str(course.get("start", "")).strip(),
            "end": str(course.get("end", "")).strip(),
            "category": str(course.get("category", "")).strip() or "未分类",
            "semester": course.get("semester", ""),
        })
    intent = result.get("intent", "general")
    if intent not in {"conflict", "career_plan", "curriculum", "credit_check", "general"}:
        intent = "general"
    return {
        "intent": intent,
        "courses": normalized_courses,
        "summary": str(result.get("summary", "")).strip(),
        "career": str(result.get("career", "")).strip(),
        "major": str(result.get("major", "")).strip(),
    }


def _call_file_analysis(content: Any, prompt: str = "") -> dict[str, Any]:
    llm = AGENT.llm
    if not llm.api_key:
        raise RuntimeError("未配置大模型 API Key")
    payload = {
        "model": llm.vision_model or llm.model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 3000,
    }
    req = urllib.request.Request(
        f"{llm.base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {llm.api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=max(llm.timeout, 60)) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"模型接口返回 HTTP {exc.code}: {detail[:300]}") from exc
    response_data = json.loads(raw)
    answer = response_data["choices"][0]["message"]["content"]
    return _normalize_analysis_result(_parse_llm_json(answer))


def _decode_text_file(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_document_text(data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json"}:
        return _decode_text_file(data)
    if suffix in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        lines = []
        for sheet in workbook.worksheets[:8]:
            lines.append(f"工作表：{sheet.title}")
            for row in sheet.iter_rows(max_row=300, values_only=True):
                values = [str(value).strip() for value in row if value not in (None, "")]
                if values:
                    lines.append("\t".join(values))
        return "\n".join(lines)
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:30])
    if suffix == ".docx":
        from docx import Document
        document = Document(io.BytesIO(data))
        lines = [p.text for p in document.paragraphs if p.text.strip()]
        for table in document.tables:
            for row in table.rows:
                lines.append("\t".join(cell.text.strip() for cell in row.cells))
        return "\n".join(lines)
    raise ValueError("暂不支持该文件格式。支持图片、PDF、DOCX、XLSX、CSV、TXT、JSON。")


def _analyze_image_bytes(data: bytes, filename: str, mime_type: str, prompt: str = "") -> dict[str, Any]:
    encoded = base64.b64encode(data).decode("ascii")
    analysis_prompt = TIMETABLE_PROMPT
    if prompt:
        analysis_prompt += f"\n\n用户补充要求：{prompt}"
    content = [
        {"type": "text", "text": analysis_prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}", "detail": "high"}},
    ]
    return _call_file_analysis(content, prompt)


@app.route("/api/files/analyze", methods=["POST"])
def api_file_analyze():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "请选择要上传的文件"}), 400
    data = uploaded.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return jsonify({"error": "文件不能超过 15 MB"}), 413
    prompt = request.form.get("prompt", "").strip()
    mime_type = uploaded.mimetype or mimetypes.guess_type(uploaded.filename)[0] or "application/octet-stream"
    try:
        if mime_type.startswith("image/"):
            result = _analyze_image_bytes(data, uploaded.filename, mime_type, prompt)
        else:
            document_text = _extract_document_text(data, uploaded.filename).strip()
            if not document_text:
                return jsonify({"error": "文件中没有可读取的文字，请上传清晰截图或可复制文本的文件"}), 400
            analysis_prompt = TIMETABLE_PROMPT
            if prompt:
                analysis_prompt += f"\n\n用户补充要求：{prompt}"
            content = f"{analysis_prompt}\n\n文件名：{uploaded.filename}\n文件内容：\n{document_text[:60000]}"
            result = _call_file_analysis(content, prompt)
        result["filename"] = uploaded.filename
        result["file_type"] = mime_type
        return jsonify(result)
    except (ValueError, ImportError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"文件识别失败：{str(exc)[:300]}"}), 502

@app.route("/api/vision/analyze", methods=["POST"])
def api_vision_analyze():
    """
    接收上传的图片（课表截图等）并通过 LLM 分析。
    
    请求体：
    {
        "image": "base64编码的图片数据",
        "filename": "文件名",
        "prompt": "可选，自定义分析提示"
    }
    
    返回：
    {
        "intent": "conflict|career_plan|curriculum|credit_check|general",
        "courses": [{"name": "...", "day": "...", "start": "...", "end": "...", "category": "..."}],
        "summary": "分析总结文字",
        "career": "识别的岗位（如果是职业规划）",
        "major": "识别的专业"
    }
    """
    body = _body_json()
    image_b64 = body.get("image", "")
    filename = body.get("filename", "image.jpg")
    user_prompt = body.get("prompt", "")
    
    if not image_b64:
        return jsonify({"error": "no image data"}), 400
    
    try:
        if image_b64.startswith("data:"):
            header, image_b64 = image_b64.split(",", 1)
            mime_type = header.split(";")[0].replace("data:", "")
        else:
            mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
        image_data = base64.b64decode(image_b64, validate=True)
        if len(image_data) > MAX_UPLOAD_BYTES:
            return jsonify({"error": "图片不能超过 15 MB"}), 413
        return jsonify(_analyze_image_bytes(image_data, filename, mime_type, user_prompt))
    except (binascii.Error, ValueError):
        return jsonify({"error": "图片数据格式无效"}), 400
    except Exception as exc:
        return jsonify({"error": f"图片识别失败：{str(exc)[:300]}"}), 502


def main() -> None:
    port = int(os.getenv("PORT", "8765"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    print(f"[勤勉 v4] Flask server starting on http://127.0.0.1:{port}")
    print(f"[勤勉 v4] SSE streaming: http://127.0.0.1:{port}/api/chat/stream")
    print(f"[勤勉 v4] Conversations: http://127.0.0.1:{port}/api/conversations")
    print(f"[勤勉 v4] Knowledge Base: http://127.0.0.1:{port}/api/knowledge/status")
    app.run(host=os.getenv("HOST", "0.0.0.0"), port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
