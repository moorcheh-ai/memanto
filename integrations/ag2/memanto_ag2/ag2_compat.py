"""AG2 version differences (LLMConfig API changed in 0.14+)."""

from __future__ import annotations

from typing import Any


def openai_llm_config(model: str = "gpt-4o-mini") -> Any:
    """
    Build an ``LLMConfig`` for OpenAI using the installed AG2 version.

    AG2 0.14+ expects ``LLMConfig(OpenAILLMConfigEntry(model=...))`` and
    ``AssistantAgent(..., llm_config=...)`` (not ``with llm_config:``).
    Older 0.9.x releases accept ``LLMConfig(api_type=..., model=...)``.
    """
    from autogen import LLMConfig

    try:
        from autogen.oai.client import OpenAILLMConfigEntry

        return LLMConfig(OpenAILLMConfigEntry(model=model))
    except ImportError:
        return LLMConfig(api_type="openai", model=model)
