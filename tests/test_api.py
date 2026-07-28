"""
Flask API 集成测试
==================
测试所有 API 端点的基本可用性。

运行:
    cd qinmian-ai
    pip install pytest pytest-flask
    pytest tests/ -v
"""

from __future__ import annotations

import json
import io
import os
import sys
from pathlib import Path

import pytest

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    """创建使用临时可变数据目录的 Flask 测试应用。"""
    mutable_dir = tmp_path_factory.mktemp("qinmian-user-data")
    legacy_conversations = mutable_dir / "conversations"
    legacy_conversations.mkdir(parents=True)
    (legacy_conversations / "aaaaaaaaaaaa.json").write_text(
        json.dumps({
            "id": "aaaaaaaaaaaa",
            "title": "旧版对话不应继承",
            "messages": [],
            "message_count": 0,
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    legacy_knowledge = mutable_dir / "knowledge_base"
    legacy_knowledge.mkdir(parents=True)
    (legacy_knowledge / "records.json").write_text(
        json.dumps({
            "version": 2,
            "records": [{
                "id": "legacy-private-memory",
                "text": "旧版私人记忆不应继承",
                "vector": [1.0],
                "metadata": {"conversation_id": "aaaaaaaaaaaa"},
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    os.environ["QINMIAN_MUTABLE_DATA_DIR"] = str(mutable_dir)
    os.environ["QINMIAN_SECRET_KEY"] = "test-only-session-secret"
    os.environ["QINMIAN_LLM_DISABLED"] = "1"
    os.environ["QINMIAN_EMBEDDING_ENABLED"] = "0"
    # 延迟导入确保路径设置生效
    from app import app as flask_app
    flask_app.config.update({
        "TESTING": True,
    })
    with flask_app.test_client() as setup_client:
        response = setup_client.post(
            "/api/auth/register",
            json={
                "username": "test_user",
                "password": "test-password-123",
                "password_confirm": "test-password-123",
            },
        )
        assert response.status_code == 201
        user_id = response.get_json()["user"]["id"]
        user_root = mutable_dir / "user_data" / user_id
        assert list((user_root / "conversations").glob("*.json")) == []
        assert not (user_root / "knowledge_base" / "records.json").exists()
    return flask_app


@pytest.fixture
def client(app):
    test_client = app.test_client()
    response = test_client.post(
        "/api/auth/login",
        json={"username": "test_user", "password": "test-password-123"},
    )
    assert response.status_code == 200
    return test_client


# ═════════════════════════════════════════════════════════════════════
# 用户认证与隔离
# ═════════════════════════════════════════════════════════════════════

class TestAuth:
    def test_business_api_requires_login(self, app):
        anonymous = app.test_client()
        resp = anonymous.get("/api/conversations")
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "authentication_required"

    def test_login_logout_roundtrip(self, app):
        browser = app.test_client()
        login = browser.post(
            "/api/auth/login",
            json={"username": "test_user", "password": "test-password-123"},
        )
        assert login.status_code == 200
        assert browser.get("/api/auth/me").get_json()["authenticated"] is True
        assert browser.post("/api/auth/logout", json={}).status_code == 200
        assert browser.get("/api/auth/me").get_json()["authenticated"] is False

    def test_user_conversations_and_knowledge_are_isolated(self, app):
        alice = app.test_client()
        bob = app.test_client()
        for browser, username in ((alice, "alice_user"), (bob, "bob_user")):
            registered = browser.post(
                "/api/auth/register",
                json={
                    "username": username,
                    "password": "separate-password-123",
                    "password_confirm": "separate-password-123",
                },
            )
            assert registered.status_code == 201

        conv = alice.post("/api/conversations", json={"title": "Alice 私有对话"}).get_json()
        alice.post(
            "/api/chat",
            json={
                "conversation_id": conv["id"],
                "message": "ALICE_ONLY_MEMORY_92731 数据结构难吗",
                "context": {},
            },
        )

        assert alice.get(f"/api/conversations/{conv['id']}").status_code == 200
        assert bob.get(f"/api/conversations/{conv['id']}").status_code == 404
        bob_records = bob.get("/api/knowledge/records?limit=500").get_json()["records"]
        assert all("ALICE_ONLY_MEMORY_92731" not in item["text"] for item in bob_records)
        alice_records = alice.get("/api/knowledge/records?limit=500").get_json()["records"]
        assert any("ALICE_ONLY_MEMORY_92731" in item["text"] for item in alice_records)

        alice.post("/api/seats/watch", json={"course": "不存在的隔离测试课程"})
        assert alice.get("/api/seats").get_json()["events"]
        assert bob.get("/api/seats").get_json()["events"] == []

    def test_short_term_memory_is_scoped_by_user_and_conversation(self):
        from qinmian.agent import QinmianAgent
        from qinmian.data_store import QinmianDataStore

        agent = QinmianAgent(QinmianDataStore())
        first = agent.respond(
            "机器学习难吗",
            {"user_id": "user-a", "conversation_id": "conversation-a", "llm_enabled": False},
        )
        second = agent.respond(
            "它难吗",
            {"user_id": "user-b", "conversation_id": "conversation-b", "llm_enabled": False},
        )
        assert first["data"]["course"] == "机器学习"
        assert second["data"]["course"] == "数据结构"
        assert agent.memories["user-a:conversation-a"] is not agent.memories["user-b:conversation-b"]


# ═════════════════════════════════════════════════════════════════════
# 元数据
# ═════════════════════════════════════════════════════════════════════

class TestMeta:
    def test_meta_endpoint(self, client):
        resp = client.get("/api/meta")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "勤勉"
        assert data["major_count"] > 0
        assert "campuses" in data
        assert "features" in data
        assert data["features"]["flask"] is True
        assert data["features"]["sse"] is True

    def test_llm_status(self, client):
        resp = client.get("/api/llm/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "enabled" in data

    def test_knowledge_covers_all_majors(self, client):
        resp = client.get("/api/knowledge/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["coverage_complete"] is True
        assert data["majors_indexed"] == data["total_majors"]
        assert {"overview", "curriculum", "credits"}.issubset(data["major_aspects"])

    def test_major_knowledge_is_prioritized(self, client):
        resp = client.get("/api/knowledge/search?q=信息安全专业毕业学分&top_k=3")
        assert resp.status_code == 200
        first = resp.get_json()["results"][0]
        assert first["metadata"]["major_name"] == "信息安全"
        assert first["metadata"]["aspect"] == "credits"


# ═════════════════════════════════════════════════════════════════════
# 专业
# ═════════════════════════════════════════════════════════════════════

class TestMajors:
    def test_list_majors(self, client):
        resp = client.get("/api/majors")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "name" in data[0]
        assert "id" in data[0]

    def test_search_majors(self, client):
        resp = client.get("/api/majors?q=计算机")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_get_major(self, client):
        # 先获取列表取第一个 major_id
        resp = client.get("/api/majors")
        majors = resp.get_json()
        if majors:
            major_id = majors[0]["id"]
            resp = client.get(f"/api/majors/{major_id}")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["id"] == major_id

    def test_get_major_not_found(self, client):
        resp = client.get("/api/majors/nonexistent-id")
        assert resp.status_code == 404

    def test_curriculum(self, client):
        resp = client.get("/api/majors")
        majors = resp.get_json()
        if majors:
            major_id = majors[0]["id"]
            resp = client.get(f"/api/curriculum/{major_id}")
            if resp.status_code == 200:
                data = resp.get_json()
                assert "courses" in data or "major" in data

    def test_real_graduation_credits_for_ai(self, client):
        majors = client.get("/api/majors?q=人工智能").get_json()
        major = next(item for item in majors if item["name"] == "人工智能")

        domestic = client.get(f"/api/curriculum/{major['id']}?student_type=domestic").get_json()
        assert domestic["credit_rule"]["graduation_total"] == 160
        assert domestic["credit_rule"]["categories"]["专业核心课"] == 26
        assert domestic["credit_rule"]["is_template"] is False

        international = client.get(f"/api/curriculum/{major['id']}?student_type=international").get_json()
        assert international["credit_rule"]["graduation_total"] == 160
        assert international["credit_rule"]["categories"]["通识教育必修"] == 29
        assert international["credit_rule"]["is_template"] is False

    def test_real_graduation_credits_for_clinical_medicine(self, client):
        majors = client.get("/api/majors?q=临床医学").get_json()
        major = next(item for item in majors if item["name"] == "临床医学")
        data = client.get(f"/api/curriculum/{major['id']}?student_type=domestic").get_json()
        assert data["credit_rule"]["graduation_total"] == 225
        assert data["credit_rule"]["is_template"] is False

    def test_complete_international_credit_rows(self, client):
        software = next(item for item in client.get("/api/majors?q=软件工程").get_json() if item["name"] == "软件工程")
        software_data = client.get(f"/api/curriculum/{software['id']}?student_type=international").get_json()
        assert software_data["credit_rule"]["categories"]["专业基础课"] == 17
        assert software_data["credit_rule"]["categories"]["专业核心课"] == "16.5-34.5"
        assert software_data["credit_rule"]["categories"]["专业实践"] == 14

        bio = next(item for item in client.get("/api/majors?q=生物工程").get_json() if item["name"] == "生物工程")
        bio_data = client.get(f"/api/curriculum/{bio['id']}?student_type=international").get_json()
        assert bio_data["credit_rule"]["graduation_total"] == 175
        assert bio_data["credit_rule"]["is_template"] is False


# ═════════════════════════════════════════════════════════════════════
# 课程难度
# ═════════════════════════════════════════════════════════════════════

class TestDifficulty:
    def test_difficulty_stats(self, client):
        resp = client.get("/api/difficulty")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_courses"] > 0
        assert "distribution" in data
        assert "star_distribution" in data["distribution"]

    def test_difficulty_course(self, client):
        resp = client.get("/api/difficulty?course=数据结构")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["available"] is True
        assert data["stars"] >= 1
        assert data["stars"] <= 5
        assert "dimensions" in data

    def test_difficulty_search(self, client):
        resp = client.get("/api/difficulty/search?q=机器")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_difficulty_top(self, client):
        resp = client.get("/api/difficulty/top?k=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) <= 5
        if data:
            assert data[0]["difficulty_score"] >= data[-1]["difficulty_score"]


# ═════════════════════════════════════════════════════════════════════
# 教师
# ═════════════════════════════════════════════════════════════════════

class TestTeachers:
    def test_professors(self, client):
        resp = client.get("/api/professors")
        assert resp.status_code == 200

    def test_professors_by_course(self, client):
        resp = client.get("/api/professors?course=数据结构")
        assert resp.status_code == 200

    def test_teacher_roster(self, client):
        resp = client.get("/api/teacher-roster")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "teachers" in data

    def test_faculty_profiles(self, client):
        resp = client.get("/api/faculty-profiles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "teachers" in data


# ═════════════════════════════════════════════════════════════════════
# POST 端点
# ═════════════════════════════════════════════════════════════════════

class TestPost:
    def test_chat(self, client):
        resp = client.post(
            "/api/chat",
            data=json.dumps({"message": "你好", "context": {}}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "answer" in data
        assert "intent" in data

    def test_chat_uses_international_credit_data(self, client):
        resp = client.post(
            "/api/chat",
            data=json.dumps({"message": "境外生人工智能毕业学分是多少", "context": {}}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["graduation_total"] == 160
        assert data["data"]["credit_rule"]["student_type"] == "international"
        assert "境外生" in data["answer"]

    def test_clinical_medicine_followups_use_ten_semester_context(self, client):
        resp = client.post(
            "/api/chat",
            json={
                "message": "临床医学第1-8学期精排优化",
                "context": {},
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["intent"] == "curriculum"
        assert data["data"]["major"]["name"] == "临床医学"
        suggestions = " ".join(data["suggestions"])
        assert "临床医学" in suggestions
        assert "第9-10学期" in suggestions
        assert "4年课表" not in suggestions

    def test_clinical_medicine_plain_question_uses_five_year_program(self, client):
        resp = client.post(
            "/api/chat",
            json={"message": "临床医学", "context": {}},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["program_years"] == 5
        assert data["data"]["semester_count"] == 10
        assert "学制：5年制（共10个学期）" in data["answer"]
        assert "四年制" not in data["answer"]
        assert any("五年10学期" in item for item in data["suggestions"])

    def test_pharmacy_is_not_misclassified_as_five_year_program(self, client):
        major = next(row for row in client.get("/api/majors").get_json() if row["name"] == "药学")
        data = client.get(f"/api/curriculum/{major['id']}").get_json()
        assert data["program_years"] == 4
        assert data["semester_count"] == 8

    def test_chat_hardness(self, client):
        resp = client.post(
            "/api/course/analyze",
            data=json.dumps({"course": "数据结构"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["course"] == "数据结构"
        assert data["stars"] >= 1

    def test_plan(self, client):
        resp = client.post(
            "/api/plan",
            data=json.dumps({"career": "算法工程师"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["selected_major_fit"]["level"]
        assert 0 <= data["selected_major_fit"]["score"] <= 100
        assert data["salary_range"]
        assert data["planning_note"]
        assert all(len(semester["courses"]) >= 5 for semester in data["semesters"])

    def test_plan_evaluates_every_major_and_enriches_each_semester(self, client):
        majors = client.get("/api/majors").get_json()
        assert len(majors) >= 60
        for major in majors:
            resp = client.post(
                "/api/plan",
                json={"career": "算法工程师", "major_id": major["id"]},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["selected_major"]["id"] == major["id"]
            assert data["selected_major_fit"]["level"] in {
                "高度匹配",
                "比较匹配",
                "可迁移发展",
                "专业跨度较大",
            }
            assert all(len(semester["courses"]) >= 5 for semester in data["semesters"])
            assert any(
                course["origin"] == "career"
                for semester in data["semesters"]
                for course in semester["courses"]
            )

    def test_professors_match(self, client):
        resp = client.post(
            "/api/professors/match",
            data=json.dumps({"interest_text": "机器学习"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_conflict_resolver_validates_deduplicates_and_builds_applicable_change(self, client):
        major = client.get("/api/majors").get_json()[0]
        courses = [
            {"name": "数据结构", "day": "周一", "start": "08:00", "end": "09:40", "category": "专业必修"},
            {"name": "机器学习", "day": "星期一", "start": "08:30", "end": "10:00", "category": "专业选修"},
            {"name": "机器学习", "day": "星期一", "start": "08:30", "end": "10:00", "category": "专业选修"},
            {"name": "无效课程", "day": "周二", "start": "12:00", "end": "11:00", "category": "专业选修"},
        ]
        resp = client.post(
            "/api/conflicts",
            json={"major_id": major["id"], "selected_courses": courses},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "conflict"
        assert data["course_count"] == 2
        assert len(data["duplicate_entries"]) == 1
        assert len(data["invalid_entries"]) == 1
        assert data["conflicts"][0]["overlap_minutes"] == 70
        assert data["recommended_changes"][0]["action"] == "reschedule"

    @pytest.mark.parametrize(
        ("export_format", "signature"),
        [
            ("docx", b"PK"),
            ("pdf", b"%PDF"),
            ("xls", b"\xd0\xcf\x11\xe0"),
        ],
    )
    def test_conversation_export_formats(self, client, export_format, signature):
        resp = client.post(
            "/api/exports",
            json={
                "kind": "conversation",
                "format": export_format,
                "title": "临床医学五年规划",
                "data": {
                    "messages": [
                        {"role": "user", "content": "临床医学五年如何安排？"},
                        {"role": "assistant", "content": "按10个学期规划。"},
                    ]
                },
            },
        )
        assert resp.status_code == 200
        assert resp.data.startswith(signature)
        assert "attachment" in resp.headers["Content-Disposition"]

    def test_career_plan_docx_export(self, client):
        plan = client.post(
            "/api/plan",
            json={"career": "临床医生", "major_id": "hqu-2026-qz-med-clinical"},
        ).get_json()
        resp = client.post(
            "/api/exports",
            json={
                "kind": "career_plan",
                "format": "docx",
                "title": "临床医学五年课表",
                "data": plan,
            },
        )
        assert resp.status_code == 200
        assert resp.data.startswith(b"PK")

    def test_not_found(self, client):
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404

    def test_file_upload_analysis(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(
            app_module,
            "_call_file_analysis",
            lambda content, prompt="": {
                "intent": "conflict",
                "courses": [{
                    "name": "数据结构",
                    "day": "周一",
                    "start": "08:00",
                    "end": "09:40",
                    "category": "专业必修",
                    "semester": 3,
                }],
                "summary": "识别成功",
                "career": "",
                "major": "计算机科学与技术",
            },
        )
        resp = client.post(
            "/api/files/analyze",
            data={"file": (io.BytesIO("课程,星期,开始,结束\n数据结构,周一,08:00,09:40".encode()), "课表.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["courses"][0]["name"] == "数据结构"

    def test_nested_model_json_parser(self):
        from app import _parse_llm_json

        parsed = _parse_llm_json(
            '```json\n{"intent":"conflict","courses":[{"name":"高数","day":"周二"}]}\n```'
        )
        assert parsed["courses"][0]["name"] == "高数"


# ═════════════════════════════════════════════════════════════════════
# Function Calling
# ═════════════════════════════════════════════════════════════════════

class TestFunctionCalling:
    def test_function_schemas(self, client):
        resp = client.get("/api/functions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "functions" in data
        assert len(data["functions"]) >= 5

    def test_execute_hardness(self, client):
        resp = client.post(
            "/api/functions/execute",
            data=json.dumps({
                "name": "analyze_course_hardness",
                "arguments": {"course_name": "数据结构"},
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("stars") is not None
        assert data.get("difficulty_score") is not None

    def test_execute_search_majors(self, client):
        resp = client.post(
            "/api/functions/execute",
            data=json.dumps({
                "name": "search_majors",
                "arguments": {"query": "计算机"},
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_execute_unknown(self, client):
        resp = client.post(
            "/api/functions/execute",
            data=json.dumps({
                "name": "unknown_tool",
                "arguments": {},
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "error" in data


# ═════════════════════════════════════════════════════════════════════
# SSE 流式端点
# ═════════════════════════════════════════════════════════════════════

class TestSSE:
    def test_chat_stream(self, client):
        """测试 SSE 流式端点能正常返回 event-stream"""
        resp = client.post(
            "/api/chat/stream",
            data=json.dumps({"message": "数据结构难吗", "context": {}}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"
        # 验证 SSE 格式
        text = resp.get_data(as_text=True)
        assert "event:" in text
        assert "data:" in text
        assert "token" in text or "result" in text or "error" in text

    def test_chat_stream_meta(self, client):
        """验证 SSE 包含起始和结束 meta"""
        resp = client.post(
            "/api/chat/stream",
            data=json.dumps({"message": "你好", "context": {}}),
            content_type="application/json",
        )
        text = resp.get_data(as_text=True)
        assert '"status": "started"' in text
        assert '"status": "done"' in text


# ═════════════════════════════════════════════════════════════════════
# LangChain / FunctionCallExecutor 单元测试
# ═════════════════════════════════════════════════════════════════════

class TestFunctionCallExecutor:
    def setup_method(self):
        from qinmian.data_store import QinmianDataStore
        from qinmian.tools import FunctionCallExecutor
        self.store = QinmianDataStore()
        self.executor = FunctionCallExecutor(self.store)

    def test_analyze_hardness(self):
        result = json.loads(
            self.executor.execute("analyze_course_hardness", {"course_name": "数据结构"})
        )
        assert result.get("stars") is not None
        assert result.get("difficulty_score") is not None

    def test_search_majors(self):
        result = json.loads(
            self.executor.execute("search_majors", {"query": "计算机"})
        )
        assert isinstance(result, list)

    def test_unknown_tool(self):
        result = json.loads(
            self.executor.execute("unknown_tool", {})
        )
        assert "error" in result

    def test_schemas_contain_all_tools(self):
        from qinmian.tools import get_function_schemas
        schemas = get_function_schemas()
        names = [s["function"]["name"] for s in schemas]
        assert "analyze_course_hardness" in names
        assert "search_majors" in names
        assert "match_professor" in names
        assert "plan_career" in names
        assert "search_course_difficulty" in names
        assert len(schemas) >= 8
