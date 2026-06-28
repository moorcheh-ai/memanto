"""Server assembly: build_server must register every tool we ship.

These tests never call a tool — they only inspect the registered schema, so
no network requests are made.
"""

from __future__ import annotations

import pytest

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
}

ADMIN_TOOL_NAMES = {"create_agent", "list_agents", "get_agent", "delete_agent"}


class FakeAgentListClient:
    """Client stub returning one valid agent plus one malformed row."""

    def list_agents(self) -> list[object]:
        """Return the agent list shape used by the MCP admin tool."""
        return [{"agent_id": "valid-agent", "pattern": "tool"}, "truncated-row"]


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
async def test_list_agents_skips_malformed_agent_entries(
    fake_api_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MCP admin listing keeps valid agents when one backend row is malformed."""
    monkeypatch.setenv("MEMANTO_EXPOSE_ADMIN", "true")
    mcp = build_server(MCPServerSettings())  # type: ignore[call-arg]
    mcp._memanto_lifecycle._client = FakeAgentListClient()  # type: ignore[attr-defined]

    _, payload = await mcp.call_tool("list_agents", {})

    assert payload["status"] == "ok"
    assert payload["count"] == 1
    assert payload["agents"] == [{"agent_id": "valid-agent", "pattern": "tool"}]


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
