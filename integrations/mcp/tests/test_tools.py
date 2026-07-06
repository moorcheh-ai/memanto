"""Behavior tests for MCP tool wrappers."""

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
    def __init__(self) -> None:
        self.recall_calls: list[dict[str, Any]] = []

    def recall(self, **kwargs: Any) -> dict[str, Any]:
        self.recall_calls.append(kwargs)
        return {
            "memories": [
                {
                    "id": "memory-1",
                    "content": "The user prefers terse answers.",
                    "score": 0.91,
                }
            ]
        }


class FakeLifecycle:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            default_agent_id="agent-1",
            expose_admin_tools=False,
        )
        self.client = FakeClient()

    def resolve_agent_id(self, agent_id: str | None) -> str:
        return agent_id or self.settings.default_agent_id

    def ensure_ready(self, agent_id: str) -> str:
        return agent_id


def test_recall_forwards_min_similarity_to_sdk_client() -> None:
    mcp = FakeMCP()
    lifecycle = FakeLifecycle()
    register_tools(mcp, lifecycle)

    result = mcp.tools["recall"](
        query="answer style",
        limit=5,
        min_similarity=0.73,
    )

    assert result.status == "ok"
    assert lifecycle.client.recall_calls == [
        {
            "agent_id": "agent-1",
            "query": "answer style",
            "limit": 5,
            "type": None,
            "min_similarity": 0.73,
        }
    ]
