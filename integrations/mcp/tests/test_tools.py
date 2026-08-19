"""Tool-level regressions for MCP request shaping."""

from __future__ import annotations

from inspect import signature
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from memanto.app.core import MemoryRecord
from memanto.cli.client.sdk_client import SdkClient

from memanto_mcp.tools import DEFAULT_SOURCE, _normalize_tags, register_tools


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, name: str, description: str) -> Any:
        def decorator(fn: Any) -> Any:
            self.tools[name] = fn
            return fn

        return decorator


class FakeLifecycle:
    def __init__(self, expose_admin_tools: bool = False) -> None:
        self.settings = SimpleNamespace(
            default_agent_id="agent-1",
            expose_admin_tools=expose_admin_tools,
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
        self.client.answer.return_value = {
            "answer": "yes",
            "sources": [],
            "namespace": "memanto_agent_agent-1",
        }
        for recall_method in (
            "recall",
            "recall_recent",
            "recall_as_of",
            "recall_changed_since",
        ):
            getattr(self.client, recall_method).return_value = {"memories": []}
        agent_payload = {
            "agent_id": "agent-1",
            "namespace": "memanto_agent_agent-1",
            "pattern": "tool",
            "description": None,
            "created_at": "2026-01-01T00:00:00Z",
        }
        self.client.create_agent.return_value = agent_payload
        self.client.get_agent.return_value = agent_payload
        self.client.delete_agent.return_value = {
            "status": "deleted",
            "agent_id": "agent-1",
        }
        self.client.list_agents.return_value = {
            "agents": [agent_payload],
            "count": 1,
            "warnings": [],
        }

    def resolve_agent_id(self, agent_id: str | None) -> str:
        return agent_id or self.settings.default_agent_id

    def ensure_ready(self, agent_id: str) -> Any:
        return self.client

    def client_for(self, agent_id: str) -> MagicMock:
        self.ensure_ready(agent_id)
        return self.client


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


def _as_memory_record(call_kwargs: dict[str, Any]) -> MemoryRecord:
    """Rebuild the record the SDK would construct from a `remember` call.

    Mirrors ``SdkClient.remember``. Building the *real* core model is the point:
    the tool schema advertises enums (memory type, provenance, source) that
    Memanto core validates at write time, and mock-only tests cannot see it
    when core narrows one of them.
    """
    return MemoryRecord(
        type=call_kwargs["memory_type"],
        title=call_kwargs["title"],
        content=call_kwargs["content"],
        agent_id=call_kwargs["agent_id"],
        actor_id=call_kwargs["agent_id"],
        confidence=call_kwargs["confidence"],
        tags=call_kwargs["tags"],
        source=call_kwargs["source"],
        provenance=call_kwargs["provenance"],
    )


def _ctx_for_client(name: str | None) -> SimpleNamespace:
    """Fake the slice of Context that carries the initialize handshake info."""
    client_params = (
        SimpleNamespace(clientInfo=SimpleNamespace(name=name))
        if name is not None
        else None
    )
    return SimpleNamespace(session=SimpleNamespace(client_params=client_params))


def test_remember_defaults_are_accepted_by_memanto_core() -> None:
    """Every default the tool ships must survive core's model validation."""
    mcp = FakeMCP()
    lifecycle = FakeLifecycle()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["remember"](content="Prefers concise answers.")

    assert result.status == "ok"
    record = _as_memory_record(lifecycle.client.remember.call_args.kwargs)
    assert record.source == DEFAULT_SOURCE
    assert record.provenance == "explicit_statement"


@pytest.mark.parametrize(
    "source", ["user", "agent", "tool", "system", "cursor", "codex", "claude_code"]
)
def test_remember_accepts_any_writer_label(source: str) -> None:
    """Sources are open: an explicit writer name reaches core unchanged."""
    mcp = FakeMCP()
    lifecycle = FakeLifecycle()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["remember"](content="A stable fact.", source=source)

    assert result.status == "ok"
    assert (
        _as_memory_record(lifecycle.client.remember.call_args.kwargs).source == source
    )


@pytest.mark.parametrize(
    ("client_name", "expected"),
    [
        ("cursor", "cursor"),
        ("Cursor", "cursor"),
        ("claude-ai", "claude-ai"),
        ("Visual Studio Code", "visual-studio-code"),
        ("Claude Code", "claude-code"),
        (None, DEFAULT_SOURCE),
        ("", DEFAULT_SOURCE),
        ("###", DEFAULT_SOURCE),
    ],
)
def test_remember_attributes_the_write_to_the_calling_client(
    client_name: str | None, expected: str
) -> None:
    """Per-client attribution is the point of an open source field."""
    mcp = FakeMCP()
    lifecycle = FakeLifecycle()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["remember"](
        content="A stable fact.", ctx=_ctx_for_client(client_name)
    )

    assert result.status == "ok"
    assert _as_memory_record(lifecycle.client.remember.call_args.kwargs).source == (
        expected
    )


def test_remember_prefers_an_explicit_source_over_the_client_name() -> None:
    mcp = FakeMCP()
    lifecycle = FakeLifecycle()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["remember"](
        content="A stable fact.", source="mem0", ctx=_ctx_for_client("cursor")
    )

    assert result.status == "ok"
    assert lifecycle.client.remember.call_args.kwargs["source"] == "mem0"


def test_batch_remember_rejects_source_core_would_refuse() -> None:
    mcp = FakeMCP()
    lifecycle = FakeLifecycle()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["batch_remember"](
        memories=[{"content": "A fact.", "source": "claude code"}]
    )

    assert result.status == "error"
    assert "source='claude code'" in (result.message or "")
    lifecycle.client.batch_remember.assert_not_called()


def test_batch_remember_attributes_missing_sources_to_the_client() -> None:
    """The SDK defaults an absent source to 'user', losing the writer."""
    mcp = FakeMCP()
    lifecycle = FakeLifecycle()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["batch_remember"](
        memories=[{"content": "A fact."}, {"content": "Another.", "source": "mem0"}],
        ctx=_ctx_for_client("codex"),
    )

    assert result.status == "ok"
    sent = lifecycle.client.batch_remember.call_args.kwargs["memories"]
    assert [m["source"] for m in sent] == ["codex", "mem0"]


def test_recall_delegates_min_similarity_to_the_backend() -> None:
    """Filtering server-side keeps the top-N full; post-filtering shrank it."""
    mcp = FakeMCP()
    lifecycle = FakeLifecycle()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["recall"](query="what do I prefer?", min_similarity=0.4)

    assert result.status == "ok"
    assert lifecycle.client.recall.call_args.kwargs["min_similarity"] == 0.4


def test_answer_leaves_kiosk_mode_to_server_config_by_default() -> None:
    """An explicit False would silently override a configured kiosk_mode."""
    mcp = FakeMCP()
    lifecycle = FakeLifecycle()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["answer"](question="what do I prefer?")

    assert result.status == "ok"
    assert lifecycle.client.answer.call_args.kwargs["kiosk_mode"] is None


def test_list_agents_unwraps_the_sdk_envelope() -> None:
    """After memanto 0.2.12, list_agents returns a dict, not a bare list."""
    mcp = FakeMCP()
    lifecycle = FakeLifecycle(expose_admin_tools=True)
    lifecycle.client.list_agents.return_value = {
        "agents": [{"agent_id": "agent-1"}, {"agent_id": "agent-2"}],
        "count": 2,
        "warnings": ["Skipped unreadable metadata for 'agent-3'"],
    }
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["list_agents"]()

    assert result.status == "ok"
    assert result.count == 2
    assert [a["agent_id"] for a in result.agents] == ["agent-1", "agent-2"]
    assert "agent-3" in (result.message or "")


def test_list_agents_still_accepts_the_pre_0_2_13_list() -> None:
    """memanto <= 0.2.12 is inside our supported floor and returns a list."""
    mcp = FakeMCP()
    lifecycle = FakeLifecycle(expose_admin_tools=True)
    lifecycle.client.list_agents.return_value = [
        {"agent_id": "agent-1"},
        {"agent_id": "agent-2"},
    ]
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["list_agents"]()

    assert result.status == "ok"
    assert result.count == 2
    assert [a["agent_id"] for a in result.agents] == ["agent-1", "agent-2"]


# One minimal invocation per registered tool, admin tools included.
TOOL_INVOCATIONS: list[tuple[str, dict[str, Any]]] = [
    ("remember", {"content": "A fact."}),
    ("batch_remember", {"memories": [{"content": "A fact."}]}),
    ("recall", {"query": "what do I prefer?"}),
    ("recall_recent", {}),
    ("recall_as_of", {"as_of": "2026-01-01"}),
    ("recall_changed_since", {"since": "2026-01-01"}),
    ("answer", {"question": "what do I prefer?"}),
    ("create_agent", {"agent_id": "agent-2"}),
    ("list_agents", {}),
    ("get_agent", {"agent_id": "agent-1"}),
    ("delete_agent", {"agent_id": "agent-1"}),
]


def test_every_tool_succeeds_and_matches_the_sdk_signature() -> None:
    """End-to-end shape check for the whole tool surface.

    The mock accepts any call, so a tool that passes a parameter the SDK
    dropped (or renamed) still "works" here. Binding each recorded call to the
    real ``SdkClient`` signature is what makes this catch upstream drift.
    """
    mcp = FakeMCP()
    lifecycle = FakeLifecycle(expose_admin_tools=True)
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    assert set(mcp.tools) == {name for name, _ in TOOL_INVOCATIONS}

    for tool_name, kwargs in TOOL_INVOCATIONS:
        result = mcp.tools[tool_name](**kwargs)
        assert result.status == "ok", f"{tool_name}: {result.message}"

    for call in lifecycle.client.mock_calls:
        method_name = call[0]
        if "." in method_name:  # a call on a returned value, not on the client
            continue
        sdk_method = getattr(SdkClient, method_name)
        # ``None`` stands in for ``self``; every tool calls by keyword.
        signature(sdk_method).bind(None, *call[1], **call[2])
