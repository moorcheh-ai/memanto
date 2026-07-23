"""Environment parsing for the example research pipeline chat model."""

from __future__ import annotations

import os
from typing import Any

ATLASCLOUD_API_BASE = "https://api.atlascloud.ai/v1"
ATLASCLOUD_DEFAULT_MODEL = "qwen/qwen3.5-flash"
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def chat_openai_kwargs(*, temperature: float, default_model: str) -> dict[str, Any]:
    """Return ChatOpenAI kwargs for OpenAI, OpenRouter, or Atlas Cloud."""
    model = _first_env("LLM_MODEL", "LANGGRAPH_LLM")
    openai_key = _first_env("OPENAI_API_KEY")
    openrouter_key = _first_env("OPENROUTER_API_KEY")
    atlascloud_key = _first_env("ATLASCLOUD_API_KEY", "ATLAS_CLOUD_API_KEY")

    if openai_key:
        api_key = openai_key
        base_url = _first_env("OPENAI_API_BASE")
        resolved_model = model or default_model
    elif openrouter_key:
        api_key = openrouter_key
        base_url = _first_env("OPENAI_API_BASE") or OPENROUTER_API_BASE
        resolved_model = model or default_model
    elif atlascloud_key:
        api_key = atlascloud_key
        base_url = (
            _first_env(
                "ATLASCLOUD_API_BASE",
                "ATLAS_CLOUD_API_BASE",
                "ATLASCLOUD_BASE_URL",
                "ATLAS_CLOUD_BASE_URL",
            )
            or ATLASCLOUD_API_BASE
        )
        resolved_model = model or ATLASCLOUD_DEFAULT_MODEL
    else:
        raise RuntimeError(
            "OPENAI_API_KEY, OPENROUTER_API_KEY, or ATLASCLOUD_API_KEY is not "
            "set. Copy .env.example to .env and add your API key."
        )

    return {
        "model": resolved_model,
        "temperature": temperature,
        "api_key": api_key,
        "base_url": base_url or None,
    }
