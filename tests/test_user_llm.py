from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from qinmian.api_config import normalize_api_base_url, normalize_provider_config
from qinmian.llm import LLMClient
from qinmian.user_llm import UserLLMConfigStore


ALICE_ID = "a" * 16
BOB_ID = "b" * 16


def make_store(tmp_path: Path) -> UserLLMConfigStore:
    return UserLLMConfigStore(
        "unit-test-encryption-secret",
        base_dir=tmp_path,
        use_database=False,
    )


def test_personal_api_key_is_encrypted_and_never_returned(tmp_path: Path):
    store = make_store(tmp_path)
    secret = "sk-test-alice-private-123456"

    public = store.save_settings(ALICE_ID, {
        "provider": "openai",
        "model": "gpt-5.6-terra",
        "api_key": secret,
    })

    raw = (tmp_path / ALICE_ID / "llm_config.json").read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert secret not in raw
    assert payload["encrypted_api_key"] != secret
    assert public["has_api_key"] is True
    assert "api_key" not in public
    assert "encrypted_api_key" not in public

    client = store.get_client(ALICE_ID, server_default=object())
    assert client.api_key == secret
    assert client.provider == "openai"
    assert client.base_url == "https://api.openai.com/v1"


def test_users_have_independent_provider_and_key_settings(tmp_path: Path):
    store = make_store(tmp_path)
    store.save_settings(ALICE_ID, {
        "provider": "openai",
        "model": "gpt-5.6-terra",
        "api_key": "alice-secret-key",
    })
    store.save_settings(BOB_ID, {
        "provider": "deepseek",
        "model": "deepseek-chat",
        "api_key": "bob-secret-key",
    })

    alice = store.get_client(ALICE_ID, server_default=object())
    bob = store.get_client(BOB_ID, server_default=object())
    assert alice.api_key == "alice-secret-key"
    assert bob.api_key == "bob-secret-key"
    assert alice.base_url == "https://api.openai.com/v1"
    assert bob.base_url == "https://api.deepseek.com/v1"
    assert store.public_settings(ALICE_ID)["provider"] == "openai"
    assert store.public_settings(BOB_ID)["provider"] == "deepseek"


def test_blank_key_preserves_existing_encrypted_key(tmp_path: Path):
    store = make_store(tmp_path)
    store.save_settings(ALICE_ID, {
        "provider": "openai",
        "model": "gpt-5.6-terra",
        "api_key": "keep-this-key",
    })
    store.save_settings(ALICE_ID, {
        "provider": "openai",
        "model": "gpt-5.6-luna",
        "api_key": "",
    })

    client = store.get_client(ALICE_ID, server_default=object())
    assert client.api_key == "keep-this-key"
    assert client.model == "gpt-5.6-luna"


def test_server_provider_clears_personal_configuration(tmp_path: Path):
    store = make_store(tmp_path)
    fallback = object()
    store.save_settings(ALICE_ID, {
        "provider": "qwen",
        "model": "qwen-plus",
        "api_key": "qwen-key",
    })
    settings = store.save_settings(ALICE_ID, {"provider": "server"})

    assert settings["source"] == "server"
    assert settings["has_api_key"] is False
    assert store.get_client(ALICE_ID, fallback) is fallback
    assert not (tmp_path / ALICE_ID / "llm_config.json").exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com/v1",
        "https://localhost/v1",
        "https://127.0.0.1/v1",
        "https://10.0.0.8/v1",
        "https://service.internal/v1",
        "https://api.example.com/v1?token=secret",
    ],
)
def test_unsafe_custom_api_urls_are_rejected(url: str):
    with pytest.raises(ValueError):
        normalize_api_base_url(url)


def test_custom_openai_compatible_configuration():
    config = normalize_provider_config(
        "custom",
        "https://models.example.com/openai/v1/",
        "vendor/model-name",
    )
    assert config == {
        "provider": "custom",
        "base_url": "https://models.example.com/openai/v1",
        "model": "vendor/model-name",
        "display_name": "其他 OpenAI 兼容接口 · vendor/model-name",
    }


def test_personal_client_sends_its_own_endpoint_model_and_key(tmp_path: Path):
    store = make_store(tmp_path)
    store.save_settings(ALICE_ID, {
        "provider": "custom",
        "base_url": "https://models.example.com/openai/v1",
        "model": "vendor/student-model",
        "api_key": "alice-request-key",
    })
    client = store.get_client(ALICE_ID, server_default=object())
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "personal response"}}],
            }).encode("utf-8")

    class FakeOpener:
        def open(self, request, timeout):
            captured["url"] = request.full_url
            captured["authorization"] = request.headers["Authorization"]
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

    with (
        patch("qinmian.llm.normalize_api_base_url", return_value=client.base_url),
        patch("urllib.request.build_opener", return_value=FakeOpener()),
    ):
        result = client.request_chat_completion({
            "model": client.model,
            "messages": [{"role": "user", "content": "hello"}],
        })

    assert result["choices"][0]["message"]["content"] == "personal response"
    assert captured["url"] == "https://models.example.com/openai/v1/chat/completions"
    assert captured["authorization"] == "Bearer alice-request-key"
    assert captured["payload"]["model"] == "vendor/student-model"


def test_agent_uses_request_scoped_personal_client():
    from qinmian.agent import QinmianAgent
    from qinmian.data_store import QinmianDataStore

    class PersonalClient:
        def status(self):
            return {"enabled": True, "provider": "personal-test", "model": "user-model"}

        def enhance_answer(self, message, response, *args, **kwargs):
            return {
                **response,
                "answer": f"personal:{message}",
                "llm": {"used": True, **self.status()},
            }

    agent = QinmianAgent(QinmianDataStore())
    agent._request_context.set({"_llm_client": PersonalClient(), "llm_enabled": True})
    result = agent._with_llm(
        "route this user",
        {"intent": "fallback", "answer": "local", "data": {}},
        None,
        include_major_context=False,
    )

    assert result["answer"] == "personal:route this user"
    assert result["llm"]["provider"] == "personal-test"


def test_curriculum_is_sent_to_personal_llm_with_knowledge_context():
    from qinmian.agent import QinmianAgent
    from qinmian.data_store import QinmianDataStore

    captured = {}

    class PersonalClient:
        def status(self):
            return {"enabled": True, "provider": "personal-test", "model": "user-model"}

        def enhance_answer(self, message, response, *args, **kwargs):
            captured["message"] = message
            captured["response"] = response
            captured["kwargs"] = kwargs
            return {
                **response,
                "answer": "这是大模型结合知识库生成的课程分析。",
                "llm": {"used": True, **self.status()},
                "answer_mode": "llm_knowledge_hybrid",
            }

    local_table = (
        "## 临床医学课程规划\n\n"
        "| 学期 | 课程 | 学分 | 类别 | 学习重点 |\n"
        "|---|---|---:|---|---|\n"
        "| 第1学期 | 系统解剖学 | 6 | 学科基础 | 结构与定位 |"
    )
    agent = QinmianAgent(QinmianDataStore())
    agent._request_context.set({
        "_llm_client": PersonalClient(),
        "llm_enabled": True,
        "long_term_memory": "【知识库】临床医学为五年制，课程需按先修关系安排。",
    })
    result = agent._with_llm(
        "临床医学大一课程规划",
        {
            "intent": "curriculum",
            "answer": local_table,
            "data": {"major": {"display_name": "临床医学（五年）"}},
        },
        None,
        include_major_context=False,
    )

    assert result["llm"]["used"] is True
    assert result["answer_mode"] == "llm_knowledge_hybrid"
    assert captured["response"]["intent"] == "curriculum"
    assert "系统解剖学" in captured["response"]["answer"]
    assert "临床医学为五年制" in captured["kwargs"]["long_term_memory"]


def test_llm_prompt_combines_knowledge_and_structured_data_and_guarantees_table(monkeypatch):
    client = LLMClient({
        "provider": "openai",
        "api_key": "unit-test-key",
        "model": "unit-test-model",
        "base_url": "https://api.openai.com/v1",
    })
    captured = {}

    def fake_completion(payload, **_kwargs):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": "大一应先完成医学基础课，再逐步进入临床核心课。"}}]}

    monkeypatch.setattr(client, "request_chat_completion", fake_completion)
    local_response = {
        "intent": "curriculum",
        "answer": (
            "## 临床医学课程规划\n\n"
            "| 学期 | 课程 | 学分 | 类别 | 学习重点 |\n"
            "|---|---|---:|---|---|\n"
            "| 第1学期 | 系统解剖学 | 6 | 学科基础 | 掌握人体结构 |\n"
            "| 第2学期 | 组织学与胚胎学 | 4 | 学科基础 | 衔接生理学 |"
        ),
        "data": {"major": {"display_name": "临床医学（五年）"}},
    }

    result = client.enhance_answer(
        "临床医学大一课程规划",
        local_response,
        long_term_memory="知识库证据：临床医学学制五年，共十个学期。",
    )

    messages = captured["payload"]["messages"]
    assert "结构化工具结果和检索到的知识库上下文" in messages[0]["content"]
    assert "知识库证据：临床医学学制五年" in messages[0]["content"]
    user_payload = json.loads(messages[-1]["content"])
    assert user_payload["output_contract"]["grounding"] == "structured_data_plus_knowledge_base"
    assert user_payload["output_contract"]["markdown_table_for_multi_item_results"] is True
    assert result["answer_mode"] == "llm_knowledge_hybrid"
    assert result["grounding"] == {
        "structured_data": True,
        "knowledge_base": True,
        "llm": True,
    }
    assert "大一应先完成医学基础课" in result["answer"]
    assert "| 学期 | 课程 | 学分 | 类别 | 学习重点 |" in result["answer"]
    assert "系统解剖学" in result["answer"]


def test_llm_failure_returns_labeled_knowledge_fallback(monkeypatch):
    client = LLMClient({
        "provider": "openai",
        "api_key": "unit-test-key",
        "model": "unit-test-model",
        "base_url": "https://api.openai.com/v1",
    })

    def fail_completion(_payload, **_kwargs):
        raise RuntimeError("temporary model failure")

    monkeypatch.setattr(client, "request_chat_completion", fail_completion)
    result = client.enhance_answer(
        "课程规划",
        {"intent": "curriculum", "answer": "本地可核验课程表", "data": {}},
        long_term_memory="知识库课程证据",
    )

    assert result["answer"] == "本地可核验课程表"
    assert result["answer_mode"] == "knowledge_fallback"
    assert result["llm"]["used"] is False
    assert result["llm"]["reason"] == "call_failed"
