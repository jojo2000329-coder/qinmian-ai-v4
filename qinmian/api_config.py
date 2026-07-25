"""Validation and presets for user-supplied OpenAI-compatible API endpoints."""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urlsplit, urlunsplit


PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "server": {
        "label": "平台默认配置",
        "base_url": "",
        "model": "",
        "requires_key": False,
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5.6-terra",
        "requires_key": True,
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "requires_key": True,
    },
    "qwen": {
        "label": "通义千问（DashScope）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "requires_key": True,
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o-mini",
        "requires_key": True,
    },
    "custom": {
        "label": "其他 OpenAI 兼容接口",
        "base_url": "",
        "model": "",
        "requires_key": True,
    },
}

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localhost")


def public_provider_presets() -> list[dict[str, Any]]:
    """Return UI-safe provider defaults."""
    return [
        {
            "id": provider_id,
            "label": preset["label"],
            "base_url": preset["base_url"],
            "model": preset["model"],
            "requires_key": preset["requires_key"],
        }
        for provider_id, preset in PROVIDER_PRESETS.items()
    ]


def validate_model_name(value: Any) -> str:
    model = str(value or "").strip()
    if not _MODEL_RE.fullmatch(model):
        raise ValueError("模型名称需为 1–128 个字符，可使用字母、数字、点、横线、下划线、斜线或冒号")
    return model


def normalize_api_base_url(value: Any, *, resolve_dns: bool = False) -> str:
    """Accept only public HTTPS API base URLs and return a normalized value."""
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        raise ValueError("请填写 API Base URL")
    if len(raw) > 512:
        raise ValueError("API Base URL 过长")

    parsed = urlsplit(raw)
    if parsed.scheme.lower() != "https":
        raise ValueError("API Base URL 必须使用 HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("API Base URL 格式不正确")
    if parsed.query or parsed.fragment:
        raise ValueError("API Base URL 不能包含查询参数或片段")

    hostname = parsed.hostname.rstrip(".").lower()
    if (
        hostname == "localhost"
        or hostname.endswith(_BLOCKED_HOST_SUFFIXES)
        or "." not in hostname
    ):
        raise ValueError("API Base URL 必须指向公开互联网地址")

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and not literal_ip.is_global:
        raise ValueError("API Base URL 不能指向私有或本机网络")

    if resolve_dns:
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    hostname,
                    parsed.port or 443,
                    type=socket.SOCK_STREAM,
                )
            }
        except socket.gaierror as exc:
            raise ValueError("API Base URL 域名无法解析") from exc
        if not addresses:
            raise ValueError("API Base URL 域名无法解析")
        for address in addresses:
            try:
                resolved_ip = ipaddress.ip_address(address)
            except ValueError as exc:
                raise ValueError("API Base URL 解析结果无效") from exc
            if not resolved_ip.is_global:
                raise ValueError("API Base URL 解析到了私有或本机网络")

    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    netloc = f"{hostname}{port}"
    return urlunsplit(("https", netloc, parsed.path.rstrip("/"), "", ""))


def normalize_provider_config(
    provider: Any,
    base_url: Any,
    model: Any,
) -> dict[str, str]:
    provider_id = str(provider or "").strip().lower()
    if provider_id not in PROVIDER_PRESETS or provider_id == "server":
        raise ValueError("不支持的大模型提供商")

    preset = PROVIDER_PRESETS[provider_id]
    effective_base_url = preset["base_url"] if provider_id != "custom" else base_url
    effective_model = str(model or "").strip() or str(preset["model"])
    return {
        "provider": provider_id,
        "base_url": normalize_api_base_url(effective_base_url),
        "model": validate_model_name(effective_model),
        "display_name": f"{preset['label']} · {effective_model}",
    }
