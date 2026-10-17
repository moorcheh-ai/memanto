"""
OrcaRouter LLM factory for the Memanto + LangGraph examples.

This module lets any example opt into [OrcaRouter](https://www.orcarouter.ai)
as a **named** OpenAI-compatible provider, without losing the existing
OpenRouter / OpenAI fallbacks.

How it works
------------
- If ``ORCAROUTER_API_KEY`` is set, every ``build_orcarouter_llm()`` call
  returns a ``ChatOpenAI`` pointed at OrcaRouter's OpenAI-compatible gateway
  (``https://api.orcarouter.ai/v1``), with the smart-routing model
  ``orcarouter/auto`` by default.
- Otherwise it falls back to the exact behaviour the examples had before:
  OpenRouter (default) or OpenAI, overridable via ``LLM_MODEL`` /
  ``OPENAI_API_BASE``.

OrcaRouter routes ``orcarouter/auto`` to the best available upstream model
for the request (smart routing), so the model id must keep the
``orcarouter/`` prefix — it is sent to the gateway verbatim.
"""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

# Named OrcaRouter gateway constants.
ORCAROUTER_API_BASE = "https://api.orcarouter.ai/v1"
ORCAROUTER_MODEL = "orcarouter/auto"

# Gateway models offered through OrcaRouter's smart routing.
ORCAROUTER_MODELS = (
    "orcarouter/auto",
    "orcarouter/fusion",
    "orcarouter/fusion-flash",
    "orcarouter/fusion-mini",
)


def orcarouter_configured() -> bool:
    """Return True when the user has opted into OrcaRouter."""
    return bool(os.environ.get("ORCAROUTER_API_KEY"))


def build_orcarouter_llm(
    *,
    model: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> ChatOpenAI:
    """Build a ``ChatOpenAI`` preferring OrcaRouter when configured.

    When ``ORCAROUTER_API_KEY`` is set the model defaults to
    ``orcarouter/auto`` (smart routing) and the base URL to OrcaRouter's
    OpenAI-compatible endpoint. Otherwise the legacy OpenRouter/OpenAI
    resolution is used so existing demos keep working unchanged.

    Args:
        model: Model override. When OrcaRouter is active this should be a
            full ``orcarouter/...`` id; default ``orcarouter/auto``.
        temperature: Sampling temperature.
        max_tokens: Optional max output tokens (reasoning upstreams need a cap).
        api_key: Explicit key override (defaults to env resolution).
        base_url: Explicit base URL override (defaults to env resolution).
    """
    if api_key is None:
        api_key = os.environ.get("ORCAROUTER_API_KEY")
    if base_url is None:
        base_url = os.environ.get("ORCAROUTER_API_BASE", ORCAROUTER_API_BASE)

    if api_key:
        return ChatOpenAI(
            model=model or os.environ.get("ORCAROUTER_MODEL", ORCAROUTER_MODEL),
            temperature=temperature,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
        )

    # Legacy fallback: OpenRouter (default) or OpenAI, as before.
    return ChatOpenAI(
        model=model or os.environ.get("LLM_MODEL", "openai/gpt-4o-mini"),
        temperature=temperature,
        api_key=os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY"),
        base_url=os.environ.get("OPENAI_API_BASE", "https://openrouter.ai/api/v1"),
        max_tokens=max_tokens,
    )
