"""Settings validation: misconfiguration must fail fast at startup."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from memanto_mcp.config import MCPServerSettings, TransportType


def test_missing_api_key_raises() -> None:
    with pytest.raises(ValidationError) as exc:
        MCPServerSettings()  # type: ignore[call-arg]
    assert "moorcheh_api_key" in str(exc.value).lower()


def test_empty_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOORCHEH_API_KEY", "   ")
    with pytest.raises(ValidationError) as exc:
        MCPServerSettings()  # type: ignore[call-arg]
    assert "moorcheh_api_key" in str(exc.value).lower()


def test_minimal_valid_settings(fake_api_key: str) -> None:
    settings = MCPServerSettings()  # type: ignore[call-arg]
    assert settings.api_key_value() == fake_api_key
    assert settings.transport is TransportType.STDIO
    assert settings.default_agent_id is None
    assert settings.expose_admin_tools is False
    assert settings.agent_auto_create is True
    assert settings.agent_pattern == "tool"


def test_secret_key_not_in_repr(fake_api_key: str) -> None:
    settings = MCPServerSettings()  # type: ignore[call-arg]
    assert fake_api_key not in repr(settings)
    assert fake_api_key not in str(settings)


def test_default_agent_loaded_from_env(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEMANTO_DEFAULT_AGENT_ID", "my-assistant")
    settings = MCPServerSettings()  # type: ignore[call-arg]
    assert settings.default_agent_id == "my-assistant"


@pytest.mark.parametrize("pattern", ["support", "project", "tool"])
def test_valid_agent_patterns(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch, pattern: str
) -> None:
    monkeypatch.setenv("MEMANTO_AGENT_PATTERN", pattern)
    assert MCPServerSettings().agent_pattern == pattern  # type: ignore[call-arg]


def test_invalid_agent_pattern_rejected(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEMANTO_AGENT_PATTERN", "nonsense")
    with pytest.raises(ValidationError) as exc:
        MCPServerSettings()  # type: ignore[call-arg]
    assert "agent_pattern" in str(exc.value).lower()


@pytest.mark.parametrize(
    "level,expected",
    [("debug", "DEBUG"), ("info", "INFO"), ("WARNING", "WARNING")],
)
def test_log_level_normalized(
    fake_api_key: str,
    monkeypatch: pytest.MonkeyPatch,
    level: str,
    expected: str,
) -> None:
    monkeypatch.setenv("MEMANTO_MCP_LOG_LEVEL", level)
    assert MCPServerSettings().log_level == expected  # type: ignore[call-arg]


def test_invalid_log_level_rejected(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEMANTO_MCP_LOG_LEVEL", "LOUD")
    with pytest.raises(ValidationError):
        MCPServerSettings()  # type: ignore[call-arg]


@pytest.mark.parametrize("port", [0, 65536, 100000])
def test_invalid_port_rejected(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch, port: int
) -> None:
    monkeypatch.setenv("MEMANTO_MCP_PORT", str(port))
    with pytest.raises(ValidationError):
        MCPServerSettings()  # type: ignore[call-arg]


def test_transport_enum_from_env(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEMANTO_MCP_TRANSPORT", "sse")
    assert MCPServerSettings().transport is TransportType.SSE  # type: ignore[call-arg]
