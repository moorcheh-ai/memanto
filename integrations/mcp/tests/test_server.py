"""Server assembly: build_server must register every tool we ship.

These tests inspect the registered schema, or drive a tool over an in-memory
MCP session with the SDK client patched out, so no network requests are made.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import Implementation
from memanto.app.constants import (
    VALID_MEMORY_TYPES,
    VALID_PROVENANCE_TYPES,
)
from memanto.app.core import SOURCE_MAX_LENGTH, SOURCE_PATTERN

from memanto_mcp.config import MCPServerSettings, TransportType
from memanto_mcp.server import _build_network_app, build_server

MAIN_TOOL_NAMES = {
    "remember",
    "batch_remember",
    "recall",
    "recall_recent",
    "recall_as_of",
    "recall_changed_since",
    "answer",
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
                "remember", {"content": "Prefers concise answers."}
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
@pytest.mark.parametrize(
    ("transport", "path"),
    [
        (TransportType.SSE, "/sse"),
        (TransportType.STREAMABLE_HTTP, "/mcp"),
    ],
)
async def test_network_transport_app_is_guarded_before_mcp_routes(
    fake_api_key: str,
    monkeypatch: pytest.MonkeyPatch,
    transport: TransportType,
    path: str,
) -> None:
    """The auth boundary must wrap the real FastMCP transport app."""
    monkeypatch.setenv("MEMANTO_MCP_TRANSPORT", transport.value)
    monkeypatch.setenv("MEMANTO_MCP_AUTH_TOKEN", "network-test-token")

    settings = MCPServerSettings()  # type: ignore[call-arg]
    mcp = build_server(settings)
    app = _build_network_app(mcp, settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
    ) as client:
        response = await client.get(path)

    assert response.status_code == 401
