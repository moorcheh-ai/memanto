"""Lifecycle tests for agent-scoped MCP clients."""

from __future__ import annotations

from typing import Any

from memanto_mcp.config import MCPServerSettings
from memanto_mcp.lifecycle import MemantoLifecycle


class FakeSdkClient:
    """Small stateful stand-in for SdkClient.

    The real SdkClient stores ``agent_id`` and ``session_token`` on the client
    instance. These tests make that mutable state visible without hitting the
    network.
    """

    instances: list["FakeSdkClient"] = []

    def __init__(self, api_key: str) -> None:
        """Record constructor calls and initialize mutable session state."""
        self.api_key = api_key
        self.agent_id: str | None = None
        self.session_token: str | None = None
        self.created_agents: list[str] = []
        self.activated_agents: list[str] = []
        FakeSdkClient.instances.append(self)

    def get_agent(self, agent_id: str) -> dict[str, str]:
        """Pretend the requested agent already exists."""
        return {"agent_id": agent_id}

    def create_agent(
        self, agent_id: str, pattern: str = "tool", description: str | None = None
    ) -> dict[str, str]:
        """Record auto-created agents for future assertions."""
        self.created_agents.append(agent_id)
        return {"agent_id": agent_id, "pattern": pattern}

    def activate_agent(
        self, agent_id: str, duration_hours: int | None = None
    ) -> dict[str, str]:
        """Mutate instance session state like the real SdkClient does."""
        self.agent_id = agent_id
        self.session_token = f"token-for-{agent_id}"
        self.activated_agents.append(agent_id)
        return {"agent_id": agent_id, "session_token": self.session_token}

    def remember(self, *, agent_id: str, **_: Any) -> dict[str, str]:
        """Fail if a memory call uses a client scoped to another agent."""
        if self.agent_id != agent_id:
            raise AssertionError(
                f"client for {self.agent_id!r} used for {agent_id!r}"
            )
        return {"memory_id": f"mem-{agent_id}", "status": "ok"}


def test_ensure_ready_uses_distinct_clients_per_agent(
    fake_api_key: str, monkeypatch
) -> None:
    """Different MCP agents must not share SdkClient session state."""
    monkeypatch.setattr("memanto_mcp.lifecycle.SdkClient", FakeSdkClient)
    FakeSdkClient.instances = []

    lifecycle = MemantoLifecycle(MCPServerSettings())  # type: ignore[call-arg]

    agent_a_client = lifecycle.ensure_ready("agent-a")
    agent_b_client = lifecycle.ensure_ready("agent-b")

    assert agent_a_client is not agent_b_client
    assert agent_a_client.agent_id == "agent-a"
    assert agent_b_client.agent_id == "agent-b"
    assert agent_a_client.remember(agent_id="agent-a")["memory_id"] == "mem-agent-a"
    assert agent_b_client.remember(agent_id="agent-b")["memory_id"] == "mem-agent-b"


def test_repeated_agent_reuses_its_scoped_client(fake_api_key: str, monkeypatch) -> None:
    """Repeated calls for one agent should reuse that agent's client."""
    monkeypatch.setattr("memanto_mcp.lifecycle.SdkClient", FakeSdkClient)
    FakeSdkClient.instances = []

    lifecycle = MemantoLifecycle(MCPServerSettings())  # type: ignore[call-arg]

    first = lifecycle.ensure_ready("agent-a")
    second = lifecycle.ensure_ready("agent-a")

    assert first is second
    assert first.activated_agents == ["agent-a"]
