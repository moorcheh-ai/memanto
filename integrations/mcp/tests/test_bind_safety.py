"""Refuse non-loopback MCP HTTP/SSE binds (TLS proxy + loopback only)."""

from __future__ import annotations

import pytest

from memanto_mcp.config import MCPServerSettings, TransportType


def test_non_loopback_http_refused_without_token(fake_api_key: str) -> None:
    settings = MCPServerSettings(
        transport=TransportType.STREAMABLE_HTTP,
        host="0.0.0.0",
    )
    with pytest.raises(RuntimeError, match="beyond loopback"):
        settings.require_safe_network_bind()


def test_non_loopback_refused_even_with_auth_token(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEMANTO_MCP_AUTH_TOKEN", "shared-secret")
    settings = MCPServerSettings(
        transport=TransportType.SSE,
        host="0.0.0.0",
    )
    with pytest.raises(RuntimeError, match="beyond loopback"):
        settings.require_safe_network_bind()


def test_loopback_http_ok_without_token(fake_api_key: str) -> None:
    settings = MCPServerSettings(
        transport=TransportType.STREAMABLE_HTTP,
        host="127.0.0.1",
    )
    settings.require_safe_network_bind()


def test_stdio_ok_without_token(fake_api_key: str) -> None:
    settings = MCPServerSettings(transport=TransportType.STDIO, host="0.0.0.0")
    settings.require_safe_network_bind()
