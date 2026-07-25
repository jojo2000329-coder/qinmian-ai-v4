from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .api_config import normalize_api_base_url
from .personas import persona_for, public_persona


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Do not let a validated public API URL redirect the server elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LLMClient:
    """Small OpenAI-compatible chat client using only the Python standard library."""

    def __init__(self, overrides: dict[str, Any] | None = None) -> None:
        config = self._load_config()
        self.provider = os.getenv("QINMIAN_LLM_PROVIDER", str(config.get("provider", "openai_compatible"))).strip()
        self.api_key = (
            os.getenv("QINMIAN_LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or str(config.get("gateway_api_key", ""))
            or str(config.get("api_key", ""))
            or ""
        ).strip()
        if self.api_key in {"把你的 API Key 填在这里", "你的 API Key", "YOUR_API_KEY"}:
            self.api_key = ""
        self.model = os.getenv("QINMIAN_LLM_MODEL", str(config.get("model", ""))).strip()
        self.vision_model = os.getenv(
            "QINMIAN_VISION_MODEL", str(config.get("vision_model", self.model))
        ).strip()
        self.display_name = str(config.get("display_name", "")).strip()
        self.base_url = os.getenv("QINMIAN_LLM_BASE_URL", str(config.get("base_url", ""))).strip().rstrip("/")
        self.timeout = int(os.getenv("QINMIAN_LLM_TIMEOUT", str(config.get("timeout", 20))))
        self.last_error = ""
        self._apply_provider_defaults()
        if overrides:
            self.provider = str(overrides.get("provider", self.provider)).strip()
            self.api_key = str(overrides.get("api_key", self.api_key)).strip()
            self.model = str(overrides.get("model", self.model)).strip()
            self.vision_model = str(
                overrides.get("vision_model", overrides.get("model", self.vision_model))
            ).strip()
            self.display_name = str(overrides.get("display_name", self.display_name)).strip()
            self.base_url = str(overrides.get("base_url", self.base_url)).strip().rstrip("/")
            self.timeout = int(overrides.get("timeout", self.timeout))
            self._apply_provider_defaults()
        if os.getenv("QINMIAN_LLM_DISABLED", "0").lower() in {"1", "true", "yes", "on"}:
            self.api_key = ""

    def _load_config(self) -> dict[str, Any]:
        data_dir = Path(__file__).resolve().parents[1] / "data"
        config: dict[str, Any] = {}
        for filename in ("llm_config.json", "llm_config.local.json"):
            path = data_dir / filename
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    config.update(json.load(f))
        return config

    def _apply_provider_defaults(self) -> None:
        provider = self.provider.lower()
        if not self.base_url:
            if provider == "deepseek":
                self.base_url = "https://api.deepseek.com/v1"
            elif provider in {"qwen", "dashscope", "tongyi"}:
                self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            else:
                self.base_url = "https://api.openai.com/v1"
        if not self.model:
            if provider == "deepseek":
                self.model = "deepseek-chat"
            elif provider in {"qwen", "dashscope", "tongyi"}:
                self.model = "qwen-plus"
            else:
                self.model = "gpt-4.1-mini"

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.api_key),
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "vision_model": self.vision_model or self.model,
            "display_name": self.display_name or f"{self.provider} / {self.model}",
            "last_error": self.last_error,
        }

    def validate_endpoint(self) -> str:
        """Validate the outbound endpoint immediately before a server-side request."""
        self.base_url = normalize_api_base_url(self.base_url, resolve_dns=True)
        return self.base_url

    def enhance_answer(
        self,
        message: str,
        local_response: dict[str, Any],
        major: dict[str, Any] | None = None,
        persona_id: str = "diligent",
        chat_history: list[dict[str, Any]] | None = None,
        long_term_memory: str = "",
    ) -> dict[str, Any]:
        local_response = dict(local_response)
        local_response["persona"] = public_persona(persona_id)
        if not self.api_key:
            return local_response
        try:
            answer = self.chat(
                message,
                local_response,
                major,
                persona_id,
                chat_history=chat_history,
                long_term_memory=long_term_memory,
            )
        except Exception as exc:
            self.last_error = str(exc)
            local_response["llm"] = self.status()
            return local_response
        enhanced = dict(local_response)
        enhanced["answer"] = answer
        enhanced["llm"] = self.status()
        enhanced["llm"]["used"] = True
        return enhanced

    def chat(
        self,
        message: str,
        local_response: dict[str, Any],
        major: dict[str, Any] | None = None,
        persona_id: str = "diligent",
        chat_history: list[dict[str, Any]] | None = None,
        long_term_memory: str = "",
    ) -> str:
        persona = persona_for(persona_id)
        memory_section = (
            "\n以下是当前用户的相关长期记忆，仅在确实相关时参考：\n"
            f"{long_term_memory[:3000]}"
            if long_term_memory else ""
        )
        system_prompt = (
            "你是华侨大学学业规划 AI“勤勉”，也是当前选课规划程序的智能控制助手。"
            "你能理解用户自然语言，并基于工具结果解释专业、课程、学分、老师、抢课、冲突和职业规划。"
            "你必须基于工具返回的 JSON 回答，"
            "不要编造未提供的培养方案、教师或教务信息。遇到模板数据要明确说是模板/演示数据。"
            "如果用户只是寒暄或闲聊，可以自然、亲切地回应，不要硬讲专业信息。"
            "如果工具结果包含 ui_actions，说明页面会自动执行这些动作，你可以简短说明已经帮用户切到相应功能。"
            "回答要短、清晰、适合学生继续追问。"
            f"当前对话人格是“{persona['name']}”：{persona['system_prompt']}"
            f"{memory_section}"
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for turn in (chat_history or [])[-12:]:
            role = str(turn.get("role", ""))
            content = str(turn.get("text", turn.get("content", ""))).strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content[:4000]})
        messages.append({
            "role": "user",
            "content": json.dumps(
                {
                    "student_question": message,
                    "persona": public_persona(persona_id),
                    "selected_major": major,
                    "tool_result": self._compact(local_response),
                },
                ensure_ascii=False,
            ),
        })
        payload = {
            "model": self.model,
            "messages": messages,
        }
        result = self.request_chat_completion(payload)
        return result["choices"][0]["message"]["content"].strip()

    def request_chat_completion(
        self,
        payload: dict[str, Any],
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Send one safe OpenAI-compatible chat completion request."""
        self.validate_endpoint()
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            opener = urllib.request.build_opener(_NoRedirectHandler())
            with opener.open(request, timeout=timeout or self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail[:500]}") from exc
        return json.loads(raw)

    def _compact(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data")
        if isinstance(data, dict):
            compact_data = self._limit(data)
        elif isinstance(data, list):
            compact_data = [self._limit(item) for item in data[:8]]
        else:
            compact_data = data
        return {
            "intent": payload.get("intent"),
            "local_answer": payload.get("answer"),
            "data": compact_data,
            "suggestions": payload.get("suggestions", []),
        }

    def _limit(self, value: Any, depth: int = 0) -> Any:
        if depth > 3:
            return "..."
        if isinstance(value, dict):
            keys = list(value.keys())[:16]
            return {key: self._limit(value[key], depth + 1) for key in keys}
        if isinstance(value, list):
            return [self._limit(item, depth + 1) for item in value[:8]]
        return value
