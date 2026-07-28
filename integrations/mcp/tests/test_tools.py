"""Tool-level regressions for MCP request shaping."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from memanto_mcp.tools import _normalize_tags, register_tools


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, name: str, description: str) -> Any:
        def decorator(fn: Any) -> Any:
            self.tools[name] = fn
            return fn

        return decorator


class FakeLifecycle:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            default_agent_id="agent-1",
            expose_admin_tools=False,
        )
        self.client = MagicMock()
        self.client.batch_remember.return_value = {
            "namespace": "memanto_agent_agent-1",
            "total_submitted": 1,
            "successful": 1,
            "failed": 0,
            "results": [{"id": "mem-1", "status": "ok"}],
        }
        self.client.remember.return_value = {
            "memory_id": "mem-1",
            "namespace": "memanto_agent_agent-1",
            "confidence": 0.85,
        }

    def resolve_agent_id(self, agent_id: str | None) -> str:
        return agent_id or self.settings.default_agent_id

    def ensure_ready(self, agent_id: str) -> str:
        return agent_id


def test_batch_remember_normalizes_comma_separated_tags() -> None:
    mcp = FakeMCP()
    lifecycle = FakeLifecycle()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]
    memories = [
        {
            "content": "Uses Memanto MCP for durable memory.",
            "type": "fact",
            "tags": "mcp, batch, ",
        }
    ]

    result = mcp.tools["batch_remember"](memories=memories)

    assert result.status == "ok"
    sent_memories = lifecycle.client.batch_remember.call_args.kwargs["memories"]
    assert sent_memories[0]["tags"] == ["mcp", "batch"]
    assert memories[0]["tags"] == "mcp, batch, "


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),
        ("", []),
        ("  ", []),
        ("mcp, batch, ", ["mcp", "batch"]),
        (["mcp", "batch"], ["mcp", "batch"]),
        (["", "  ", "mcp"], ["mcp"]),
        (42, ["42"]),
    ],
)
def test_normalize_tags_accepts_mcp_client_shapes(
    raw: Any,
    expected: list[str],
) -> None:
    assert _normalize_tags(raw) == expected


def test_remember_uses_same_tag_normalization_without_mutating_input() -> None:
    mcp = FakeMCP()
    lifecycle = FakeLifecycle()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]
    tags = ["mcp", " ", "remember"]

    result = mcp.tools["remember"](
        content="Uses Memanto MCP for durable memory.",
        tags=tags,
    )

    assert result.status == "ok"
    assert lifecycle.client.remember.call_args.kwargs["tags"] == [
        "mcp",
        "remember",
    ]
    assert tags == ["mcp", " ", "remember"]
