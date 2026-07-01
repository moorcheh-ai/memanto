"""Tool behavior tests that avoid starting a real MCP server."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from memanto_mcp.tools import register_tools


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, *, name: str, description: str):
        def decorator(fn):
            self.tools[name] = fn
            return fn

        return decorator


class FakeClient:
    def __init__(self, batch_result: dict[str, Any]) -> None:
        self.batch_result = batch_result

    def batch_remember(self, *, agent_id: str, memories: list[dict[str, Any]]):
        return self.batch_result


class FakeLifecycle:
    def __init__(self, batch_result: dict[str, Any]) -> None:
        self.settings = SimpleNamespace(default_agent_id=None, expose_admin_tools=False)
        self.client = FakeClient(batch_result)

    def resolve_agent_id(self, agent_id: str | None) -> str:
        assert agent_id is not None
        return agent_id

    def ensure_ready(self, agent_id: str) -> str:
        return agent_id


def test_batch_remember_skips_malformed_item_results() -> None:
    mcp = FakeMCP()
    lifecycle = FakeLifecycle(
        {
            "namespace": "memanto_agent_test-agent",
            "total_submitted": 4,
            "successful": 3,
            "failed": 1,
            "results": [
                "stored",
                {"id": "mem-2", "status": "queued"},
                {"id": "mem-3", "status": "failed", "error": "backend rejected"},
                {"id": 123, "status": None, "error": {"reason": "coerced"}},
            ],
        }
    )
    register_tools(mcp, lifecycle)

    result = mcp.tools["batch_remember"](
        memories=[
            {"content": "First memory"},
            {"content": "Second memory"},
            {"content": "Third memory"},
            {"content": "Fourth memory"},
        ],
        agent_id="test-agent",
    )

    assert result.status == "ok"
    assert result.total_submitted == 4
    assert result.successful == 3
    assert result.failed == 1
    assert [item.id for item in result.results] == ["mem-2", "mem-3", "123"]
    assert result.results[1].error == "backend rejected"
    assert result.results[2].status == "queued"
    assert result.results[2].error == "{'reason': 'coerced'}"
