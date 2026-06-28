"""Tool output normalization helpers."""

from __future__ import annotations

from types import SimpleNamespace

from memanto_mcp.tools import BatchRememberResult, _to_memory_hit, register_tools


class _FakeMCP:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self, name: str, description: str):
        def decorator(func):
            self.tools[name] = func
            return func

        return decorator


class _FakeClient:
    def __init__(self) -> None:
        self.batch_calls = []

    def batch_remember(self, agent_id: str, memories: list[dict]) -> dict:
        self.batch_calls.append((agent_id, memories))
        return {
            "namespace": f"memanto_agent_{agent_id}",
            "total_submitted": len(memories),
            "successful": len(memories),
            "failed": 0,
            "results": [{"id": "memory-1", "status": "queued"}],
        }


class _FakeLifecycle:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            default_agent_id="default-agent",
            expose_admin_tools=False,
        )
        self.client = _FakeClient()
        self.ensure_ready_calls = []

    def resolve_agent_id(self, agent_id: str | None) -> str:
        return agent_id or self.settings.default_agent_id

    def ensure_ready(self, agent_id: str) -> str:
        self.ensure_ready_calls.append(agent_id)
        return agent_id


def test_to_memory_hit_splits_comma_separated_tags() -> None:
    hit = _to_memory_hit(
        {
            "id": "memory-1",
            "title": "Client preference",
            "content": "Use the enterprise workspace.",
            "tags": "urgent, client , ,enterprise",
            "score": 0.91,
        }
    )

    assert hit.tags == ["urgent", "client", "enterprise"]


def test_to_memory_hit_preserves_list_tags() -> None:
    hit = _to_memory_hit(
        {
            "id": "memory-2",
            "tags": ["support", " escalation ", ""],
            "similarity_score": 0.73,
        }
    )

    assert hit.tags == ["support", "escalation"]


def test_batch_remember_validates_before_lifecycle_side_effects() -> None:
    lifecycle = _FakeLifecycle()
    mcp = _FakeMCP()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["batch_remember"](
        memories=[{"content": "This should not be stored.", "type": "invalid"}]
    )

    assert isinstance(result, BatchRememberResult)
    assert result.status == "error"
    assert "not a valid memory type" in (result.message or "")
    assert lifecycle.ensure_ready_calls == []
    assert lifecycle.client.batch_calls == []


def test_batch_remember_calls_client_after_valid_input() -> None:
    lifecycle = _FakeLifecycle()
    mcp = _FakeMCP()
    register_tools(mcp, lifecycle)  # type: ignore[arg-type]

    result = mcp.tools["batch_remember"](
        memories=[{"content": "Store this memory.", "type": "fact"}]
    )

    assert result.status == "ok"
    assert lifecycle.ensure_ready_calls == ["default-agent"]
    assert lifecycle.client.batch_calls == [
        ("default-agent", [{"content": "Store this memory.", "type": "fact"}])
    ]
