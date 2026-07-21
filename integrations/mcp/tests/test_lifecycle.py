"""Session isolation tests for the MCP lifecycle."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from memanto.app.utils.errors import SessionError

import memanto_mcp.lifecycle as lifecycle_module
from memanto_mcp.config import MCPServerSettings
from memanto_mcp.lifecycle import MemantoLifecycle


class _FakeSdkClient:
    """Minimal client that enforces the same single-session scope as SdkClient."""

    instances: list[_FakeSdkClient] = []

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.agent_id: str | None = None
        self.activation_calls = 0
        self.instances.append(self)

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        return {"agent_id": agent_id}

    def activate_agent(
        self, agent_id: str, duration_hours: int | None = None
    ) -> dict[str, Any]:
        self.activation_calls += 1
        self.agent_id = agent_id
        return {"agent_id": agent_id}

    def recall(self, *, agent_id: str) -> dict[str, Any]:
        if self.agent_id != agent_id:
            raise SessionError(
                f"Active session is for agent '{self.agent_id}', "
                f"cannot access '{agent_id}'"
            )
        return {"agent_id": agent_id}


@pytest.fixture
def lifecycle(fake_api_key: str, monkeypatch: pytest.MonkeyPatch) -> MemantoLifecycle:
    _FakeSdkClient.instances.clear()
    monkeypatch.setattr(lifecycle_module, "SdkClient", _FakeSdkClient)
    return MemantoLifecycle(MCPServerSettings())  # type: ignore[call-arg]


def test_different_agents_keep_independent_session_clients(
    lifecycle: MemantoLifecycle,
) -> None:
    """A second agent becoming ready must not invalidate the first client."""
    first_ready = threading.Event()
    second_ready = threading.Event()
    errors: list[BaseException] = []

    def recall_first_agent() -> None:
        try:
            first_client = lifecycle.client_for("agent-a")
            first_ready.set()
            assert second_ready.wait(timeout=2)
            assert first_client.recall(agent_id="agent-a") == {"agent_id": "agent-a"}
        except BaseException as exc:  # pragma: no cover - reported in main thread
            errors.append(exc)

    worker = threading.Thread(target=recall_first_agent)
    worker.start()
    assert first_ready.wait(timeout=2)

    second_client = lifecycle.client_for("agent-b")
    assert second_client.recall(agent_id="agent-b") == {"agent_id": "agent-b"}
    second_ready.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert not errors
    assert len(_FakeSdkClient.instances) == 3  # admin + one per active agent


def test_same_agent_reuses_activated_session_client(
    lifecycle: MemantoLifecycle,
) -> None:
    """Repeated calls for one agent should reuse its activated client."""
    first_client = lifecycle.client_for("agent-a")
    second_client = lifecycle.client_for("agent-a")

    assert first_client is second_client
    assert first_client.activation_calls == 1
    assert len(_FakeSdkClient.instances) == 2  # admin + one agent session
