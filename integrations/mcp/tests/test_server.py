"""Server assembly: build_server must register every tool we ship.

These tests inspect the registered schema, or drive a tool over an in-memory
MCP session with the SDK client patched out, so no network requests are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import Implementation
from memanto.app.constants import (
    VALID_MEMORY_TYPES,
    VALID_PROVENANCE_TYPES,
)
from memanto.app.core import SOURCE_MAX_LENGTH, SOURCE_PATTERN

from memanto_mcp.config import MCPServerSettings
from memanto_mcp.server import build_server

MAIN_TOOL_NAMES = {
    "remember",
    "batch_remember",
    "recall",
    "recall_recent",
    "recall_as_of",
    "recall_changed_since",
    "answer",
    "login",
}

ADMIN_TOOL_NAMES = {"create_agent", "list_agents", "get_agent", "delete_agent"}


@pytest.mark.asyncio
async def test_build_server_registers_main_tools(fake_api_key: str) -> None:
    mcp = build_server(MCPServerSettings())  # type: ignore[call-arg]
    tools = {t.name for t in await mcp.list_tools()}
    assert MAIN_TOOL_NAMES.issubset(tools), (
        f"Missing main tools: {MAIN_TOOL_NAMES - tools}"
    )
    # Admin tools are off by default.
    assert tools.isdisjoint(ADMIN_TOOL_NAMES), (
        f"Admin tools leaked into default surface: {tools & ADMIN_TOOL_NAMES}"
    )


@pytest.mark.asyncio
async def test_admin_tools_registered_when_enabled(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MEMANTO_EXPOSE_ADMIN", "true")
    mcp = build_server(MCPServerSettings())  # type: ignore[call-arg]
    tools = {t.name for t in await mcp.list_tools()}
    assert ADMIN_TOOL_NAMES.issubset(tools), (
        f"Missing admin tools: {ADMIN_TOOL_NAMES - tools}"
    )


@pytest.mark.asyncio
async def test_advertised_constraints_match_memanto_core(fake_api_key: str) -> None:
    """The tool schema is a contract with the calling model.

    Memanto core validates these fields at write time, so a constraint that
    drifts from core hands the model a value guaranteed to fail on write.
    """
    mcp = build_server(MCPServerSettings())  # type: ignore[call-arg]
    tools = {t.name: t for t in await mcp.list_tools()}
    props = tools["remember"].inputSchema["properties"]

    assert set(props["type"]["enum"]) == VALID_MEMORY_TYPES
    assert set(props["provenance"]["enum"]) == VALID_PROVENANCE_TYPES

    # Source is open (no enum) but bounded to core's label shape. It is
    # optional, so the constraints sit in the string branch of the union.
    source_schema = props["source"]
    assert "enum" not in source_schema
    string_branch = next(
        branch for branch in source_schema["anyOf"] if branch.get("type") == "string"
    )
    assert string_branch["pattern"] == SOURCE_PATTERN
    assert string_branch["maxLength"] == SOURCE_MAX_LENGTH

    # batch_remember item schema exposes required fields to calling models
    batch_schema = tools["batch_remember"].inputSchema
    item_schema = batch_schema["$defs"]["BatchMemoryItem"]
    assert set(item_schema["required"]) == {
        "content",
        "type",
        "confidence",
        "provenance",
    }
    assert set(item_schema["properties"]["type"]["enum"]) == VALID_MEMORY_TYPES
    assert (
        set(item_schema["properties"]["provenance"]["enum"]) == VALID_PROVENANCE_TYPES
    )


@pytest.mark.asyncio
async def test_remember_records_the_connected_client_as_source(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The handshake identity must survive the real FastMCP call path.

    The unit tests hand the tool a hand-built context; only a live session
    proves FastMCP injects one at all.
    """
    monkeypatch.setenv("MEMANTO_DEFAULT_AGENT_ID", "probe-agent")
    sdk_client = MagicMock()
    sdk_client.remember.return_value = {"memory_id": "mem-1", "namespace": "ns"}

    with patch(
        "memanto_mcp.lifecycle.MemantoLifecycle.ensure_ready", return_value=sdk_client
    ):
        mcp = build_server(MCPServerSettings())  # type: ignore[call-arg]
        async with create_connected_server_and_client_session(
            mcp._mcp_server,
            client_info=Implementation(name="Cursor", version="1.0.0"),
        ) as session:
            await session.initialize()
            result = await session.call_tool(
                "remember",
                {
                    "content": "Prefers concise answers.",
                    "type": "preference",
                    "confidence": 0.9,
                    "provenance": "explicit_statement",
                },
            )

    assert not result.isError
    assert sdk_client.remember.call_args.kwargs["source"] == "cursor"


@pytest.mark.asyncio
async def test_handshake_reports_our_version_not_the_sdk_version(
    fake_api_key: str,
) -> None:
    """Clients display serverInfo, so it must identify memanto-mcp.

    FastMCP leaves the low-level version unset, which makes the server
    announce the MCP SDK's version instead of its own.
    """
    from importlib.metadata import version

    from memanto_mcp import __version__

    server = build_server(MCPServerSettings())  # type: ignore[call-arg]
    async with create_connected_server_and_client_session(
        server._mcp_server
    ) as session:
        info = (await session.initialize()).serverInfo

    assert info.name == "memanto"
    assert info.version == __version__
    assert info.version != version("mcp")


@pytest.mark.asyncio
async def test_context_parameter_is_hidden_from_the_model(fake_api_key: str) -> None:
    """`ctx` is injected by FastMCP; exposing it would invite bogus arguments."""
    mcp = build_server(MCPServerSettings())  # type: ignore[call-arg]
    tools = {t.name: t for t in await mcp.list_tools()}

    for name in ("remember", "batch_remember"):
        assert "ctx" not in tools[name].inputSchema["properties"]


@pytest.mark.asyncio
async def test_server_name_and_instructions(fake_api_key: str) -> None:
    mcp = build_server(MCPServerSettings())  # type: ignore[call-arg]
    assert mcp.name == "memanto"
    # Instructions guide the model toward correct memory usage; they must be
    # non-empty and mention the core verbs so clients surface useful prompts.
    instructions = (mcp.instructions or "").lower()
    assert "remember" in instructions
    assert "recall" in instructions


@pytest.mark.asyncio
async def test_tool_descriptions_non_empty(fake_api_key: str) -> None:
    """Marketplace listings rely on tool descriptions; none should be blank."""
    mcp = build_server(MCPServerSettings())  # type: ignore[call-arg]
    for tool in await mcp.list_tools():
        assert tool.description and tool.description.strip(), (
            f"Tool {tool.name!r} has an empty description"
        )


@pytest.mark.asyncio
async def test_local_login_tool_automatically_sets_memanto_api_key_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """Local MCP login starts /cli/device-code, polls /cli/token, and automatically sets MEMANTO_API_KEY."""
    import json
    import os
    from pathlib import Path

    from memanto_mcp.cloud_client import (
        CloudPublicApiClient,
        _auth_cache,
        local_login_manager,
    )

    _auth_cache.clear()
    local_login_manager.clear()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    monkeypatch.setattr(
        CloudPublicApiClient,
        "request_device_code",
        classmethod(
            lambda cls, **kw: (
                200,
                {
                    "device_code": "dc_local_123",
                    "user_code": "JKLM-NPQR",
                    "verification_uri": "https://console.memanto.ai/cli/authorize",
                    "verification_uri_complete": "https://console.memanto.ai/cli/authorize?code=JKLM-NPQR",
                    "interval": 5,
                    "expires_in": 600,
                },
            )
        ),
    )
    monkeypatch.setattr(
        CloudPublicApiClient,
        "poll_device_token",
        classmethod(
            lambda cls, *, device_code, **kw: (
                200,
                {
                    "api_key": "mk_local_auto_env_key",
                    "user_email": "local@memanto.ai",
                    "plan": "pro",
                },
            )
        ),
    )

    def fake_request(
        self, method: str, path: str, *, json_body=None, params=None, source=None
    ):
        assert self.api_key == "mk_local_auto_env_key"
        if path == "/me":
            return 200, {"user_id": "u_local", "email": "local@memanto.ai", "plan": "pro"}
        if method == "GET" and path.startswith("/agents/"):
            return 200, {"agent_id": path.split("/")[-1], "pattern": "tool"}
        if method == "POST" and path.endswith("/remember"):
            return 200, {"memory_id": "mem_local_1", "confidence": 1.0}
        if method == "POST" and path.endswith("/recall/recent"):
            return 200, {"memories": [{"id": "mem_local_1", "type": "fact", "content": "Local MCP auto-configured MEMANTO_API_KEY."}]}
        raise AssertionError(f"Unexpected call: {method} {path}")

    monkeypatch.setattr(CloudPublicApiClient, "_request", fake_request)

    # Start server in pending-login state (no API key yet)
    settings = MCPServerSettings(
        moorcheh_api_key="__pending_local_login__",  # type: ignore[arg-type]
        default_agent_id="local-agent",
    )
    mcp = build_server(settings)

    async with create_connected_server_and_client_session(
        mcp._mcp_server,
        client_info=Implementation(name="Cursor", version="1.0.0"),
    ) as session:
        await session.initialize()

        # 1. First login call starts device-code flow
        login1 = await session.call_tool("login", {})
        payload1 = json.loads(login1.content[0].text)
        assert payload1["status"] == "pending"
        assert payload1["user_code"] == "JKLM-NPQR"
        assert "code=JKLM-NPQR" in payload1["verification_uri"]

        # 2. Second login call (or background poll) collects token and auto-sets MEMANTO_API_KEY
        login2 = await session.call_tool("login", {})
        payload2 = json.loads(login2.content[0].text)
        assert payload2["status"] == "authenticated"
        assert payload2["env_configured"] is True
        assert os.environ.get("MEMANTO_API_KEY") == "mk_local_auto_env_key"
        dotenv_file = Path(str(tmp_path)) / ".memanto" / ".env"
        assert dotenv_file.exists()
        assert "mk_local_auto_env_key" in dotenv_file.read_text(encoding="utf-8")

        # 3. Subsequent remember call works automatically using the newly set MEMANTO_API_KEY
        rem = await session.call_tool(
            "remember",
            {
                "content": "Local MCP auto-configured MEMANTO_API_KEY.",
                "type": "fact",
                "confidence": 1.0,
                "provenance": "explicit_statement",
            },
        )
        rem_payload = json.loads(rem.content[0].text)
        assert rem_payload["status"] == "ok"
        assert rem_payload["memory_id"] == "mem_local_1"

        rec = await session.call_tool("recall_recent", {"limit": 5})
        rec_payload = json.loads(rec.content[0].text)
        assert rec_payload["status"] == "ok"
        assert rec_payload["count"] == 1


@pytest.mark.asyncio
async def test_pending_login_returns_actionable_unauthorized_error_before_login() -> None:
    """Calling a memory tool before login returns a clear error instructing to call login."""
    import json

    from memanto_mcp.cloud_client import local_login_manager

    local_login_manager.clear()
    settings = MCPServerSettings(
        moorcheh_api_key="__pending_local_login__",  # type: ignore[arg-type]
        default_agent_id="local-agent",
    )
    mcp = build_server(settings)

    async with create_connected_server_and_client_session(
        mcp._mcp_server,
        client_info=Implementation(name="Cursor", version="1.0.0"),
    ) as session:
        await session.initialize()
        res = await session.call_tool("recall_recent", {"limit": 1})
        payload = json.loads(res.content[0].text)
        assert payload["status"] == "error"
        assert "login" in payload["message"].lower()


