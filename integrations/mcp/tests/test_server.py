"""Server assembly: build_server must register every tool we ship.

These tests never call a tool — they only inspect the registered schema, so
no network requests are made.
"""

from __future__ import annotations

import pytest
from memanto.app.constants import (
    VALID_MEMORY_TYPES,
    VALID_PROVENANCE_TYPES,
)

from memanto_mcp.config import MCPServerSettings
from memanto_mcp.server import build_server
from memanto_mcp.tools import VALID_SOURCE_TYPES

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
async def test_advertised_enums_match_memanto_core(fake_api_key: str) -> None:
    """The tool schema is a contract with the calling model.

    Memanto core validates these fields at write time, so an enum that drifts
    from core hands the model a value that is guaranteed to fail on write.
    Every advertised source is separately round-tripped through a real
    MemoryRecord in test_tools.py, which is what pins the source list.
    """
    mcp = build_server(MCPServerSettings())  # type: ignore[call-arg]
    tools = {t.name: t for t in await mcp.list_tools()}
    props = tools["remember"].inputSchema["properties"]

    assert set(props["type"]["enum"]) == VALID_MEMORY_TYPES
    assert set(props["provenance"]["enum"]) == VALID_PROVENANCE_TYPES
    assert set(props["source"]["enum"]) == VALID_SOURCE_TYPES


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
