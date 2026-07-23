from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from types import ModuleType

import memanto.app.services as memanto_services

ROOT = Path(__file__).resolve().parents[1]

fake_moorcheh_sdk = types.ModuleType("moorcheh_sdk")
fake_moorcheh_sdk.AsyncMoorchehClient = object
fake_moorcheh_sdk.MoorchehClient = object
sys.modules.setdefault("moorcheh_sdk", fake_moorcheh_sdk)

fake_agent_service = types.ModuleType("memanto.app.services.agent_service")
fake_agent_service.get_moorcheh_client = lambda: None
sys.modules.setdefault("memanto.app.services.agent_service", fake_agent_service)
memanto_services.agent_service = fake_agent_service


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clear_llm_env() -> None:
    for key in (
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "OPENROUTER_API_KEY",
        "ATLASCLOUD_API_KEY",
        "ATLAS_CLOUD_API_KEY",
        "ATLASCLOUD_API_BASE",
        "ATLAS_CLOUD_API_BASE",
        "ATLASCLOUD_BASE_URL",
        "ATLAS_CLOUD_BASE_URL",
        "LLM_MODEL",
        "LANGGRAPH_LLM",
    ):
        os.environ.pop(key, None)


def test_base_store_llm_config_supports_atlascloud(monkeypatch):
    clear_llm_env()
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "atlas-key")
    module = load_module(
        ROOT / "examples/langgraph-memanto/memanto_base_store/llm_config.py",
        "base_store_llm_config",
    )

    kwargs = module.chat_openai_kwargs(temperature=0.2, default_model="fallback")

    assert kwargs == {
        "model": "qwen/qwen3.5-flash",
        "temperature": 0.2,
        "api_key": "atlas-key",
        "base_url": "https://api.atlascloud.ai/v1",
    }


def test_base_store_llm_config_keeps_explicit_openai_precedence(monkeypatch):
    clear_llm_env()
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "atlas-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    module = load_module(
        ROOT / "examples/langgraph-memanto/memanto_base_store/llm_config.py",
        "base_store_llm_config_openai",
    )

    kwargs = module.chat_openai_kwargs(
        temperature=0.1,
        default_model="fallback",
        max_tokens=7000,
    )

    assert kwargs == {
        "model": "gpt-4o-mini",
        "temperature": 0.1,
        "api_key": "openai-key",
        "base_url": None,
        "max_tokens": 7000,
    }


def test_research_pipeline_llm_config_accepts_atlascloud_aliases(monkeypatch):
    clear_llm_env()
    monkeypatch.setenv("ATLAS_CLOUD_API_KEY", "atlas-key")
    monkeypatch.setenv("ATLASCLOUD_BASE_URL", "https://atlas.example/v1")
    monkeypatch.setenv("LLM_MODEL", "deepseek-ai/deepseek-v4-pro")
    module = load_module(
        ROOT
        / "examples/langgraph-memanto/research_pipeline/langgraph_memanto/llm_config.py",
        "research_llm_config",
    )

    kwargs = module.chat_openai_kwargs(temperature=0.7, default_model="fallback")

    assert kwargs == {
        "model": "deepseek-ai/deepseek-v4-pro",
        "temperature": 0.7,
        "api_key": "atlas-key",
        "base_url": "https://atlas.example/v1",
    }
