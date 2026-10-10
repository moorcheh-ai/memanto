from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import ModuleType

import pytest

import memanto.app.services as memanto_services

ROOT = Path(__file__).resolve().parents[1]

LLM_ENV_KEYS = (
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
)

CONFIG_MODULES = (
    (
        "examples/langgraph-memanto/memanto_base_store/llm_config.py",
        "base_store_llm_config",
    ),
    (
        "examples/langgraph-memanto/research_pipeline/langgraph_memanto/llm_config.py",
        "research_llm_config",
    ),
)


def clear_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in LLM_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def isolate_sdk_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_moorcheh_sdk = types.ModuleType("moorcheh_sdk")
    fake_moorcheh_sdk.AsyncMoorchehClient = object
    fake_moorcheh_sdk.MoorchehClient = object
    monkeypatch.setitem(sys.modules, "moorcheh_sdk", fake_moorcheh_sdk)

    fake_agent_service = types.ModuleType("memanto.app.services.agent_service")
    fake_agent_service.get_moorcheh_client = lambda: None
    monkeypatch.setitem(
        sys.modules,
        "memanto.app.services.agent_service",
        fake_agent_service,
    )
    monkeypatch.setattr(
        memanto_services,
        "agent_service",
        fake_agent_service,
        raising=False,
    )
    clear_llm_env(monkeypatch)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_base_store_llm_config_supports_atlascloud(monkeypatch):
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "atlas-key")
    module = load_module(
        ROOT / "examples/langgraph-memanto/memanto_base_store/llm_config.py",
        "base_store_llm_config",
    )

    kwargs = module.chat_openai_kwargs(temperature=0.2)

    assert kwargs == {
        "model": "qwen/qwen3.5-flash",
        "temperature": 0.2,
        "api_key": "atlas-key",
        "base_url": "https://api.atlascloud.ai/v1",
    }


def test_base_store_llm_config_keeps_explicit_openai_precedence(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("ATLASCLOUD_API_KEY", "atlas-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    module = load_module(
        ROOT / "examples/langgraph-memanto/memanto_base_store/llm_config.py",
        "base_store_llm_config_openai",
    )

    kwargs = module.chat_openai_kwargs(
        temperature=0.1,
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
    monkeypatch.setenv("ATLAS_CLOUD_API_KEY", "atlas-key")
    monkeypatch.setenv("ATLASCLOUD_BASE_URL", "https://atlas.example/v1")
    monkeypatch.setenv("LLM_MODEL", "deepseek-ai/deepseek-v4-pro")
    module = load_module(
        ROOT
        / "examples/langgraph-memanto/research_pipeline/langgraph_memanto/llm_config.py",
        "research_llm_config",
    )

    kwargs = module.chat_openai_kwargs(temperature=0.7)

    assert kwargs == {
        "model": "deepseek-ai/deepseek-v4-pro",
        "temperature": 0.7,
        "api_key": "atlas-key",
        "base_url": "https://atlas.example/v1",
    }


@pytest.mark.parametrize(("relative_path", "module_name"), CONFIG_MODULES)
def test_llm_config_uses_provider_specific_defaults(
    monkeypatch,
    relative_path,
    module_name,
):
    module = load_module(ROOT / relative_path, f"{module_name}_defaults")

    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    openai_kwargs = module.chat_openai_kwargs(temperature=0.3)

    assert openai_kwargs["model"] == "gpt-4o-mini"
    assert openai_kwargs["api_key"] == "openai-key"
    assert openai_kwargs["base_url"] is None

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-key")
    openrouter_kwargs = module.chat_openai_kwargs(temperature=0.3)

    assert openrouter_kwargs["model"] == "openai/gpt-4o-mini"
    assert openrouter_kwargs["api_key"] == "openrouter-key"
    assert openrouter_kwargs["base_url"] == "https://openrouter.ai/api/v1"


@pytest.mark.parametrize(("relative_path", "module_name"), CONFIG_MODULES)
def test_llm_config_uses_langgraph_llm_fallback(
    monkeypatch,
    relative_path,
    module_name,
):
    monkeypatch.setenv("ATLAS_CLOUD_API_KEY", "atlas-key")
    monkeypatch.setenv("ATLASCLOUD_BASE_URL", "https://atlas.example/v1")
    monkeypatch.setenv("LANGGRAPH_LLM", "deepseek-ai/deepseek-v4-pro")
    module = load_module(ROOT / relative_path, f"{module_name}_langgraph_fallback")

    kwargs = module.chat_openai_kwargs(temperature=0.4)

    assert kwargs == {
        "model": "deepseek-ai/deepseek-v4-pro",
        "temperature": 0.4,
        "api_key": "atlas-key",
        "base_url": "https://atlas.example/v1",
    }
