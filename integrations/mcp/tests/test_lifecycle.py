"""Lifecycle tests for agent-scoped MCP clients."""

from __future__ import annotations

from typing import Any

from memanto.app.utils.errors import AgentNotFoundError
from memanto_mcp.config import MCPServerSettings
from memanto_mcp.lifecycle import MemantoLifecycle
from memanto_mcp.tools import register_tools


class FakeSdkClient:
    """Small stateful stand-in for SdkClient.

    The real SdkClient stores ``agent_id`` and ``session_token`` on the client
    instance. These tests make that mutable state visible without hitting the
    network.
    """

    instances: list["FakeSdkClient"] = []
    missing_agents: set[str] = set()
    fail_activate_agents: set[str] = set()

    def __init__(self, api_key: str) -> None:
        """Record constructor calls and initialize mutable session state."""
        self.api_key = api_key
        self.agent_id: str | None = None
        self.session_token: str | None = None
        self.created_agents: list[str] = []
        self.activated_agents: list[str] = []
        FakeSdkClient.instances.append(self)

    def get_agent(self, agent_id: str) -> dict[str, str]:
        """Pretend the requested agent exists unless configured missing."""
        if agent_id in FakeSdkClient.missing_agents:
            raise AgentNotFoundError(f"Agent '{agent_id}' not found")
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
        if agent_id in FakeSdkClient.fail_activate_agents:
            raise RuntimeError("activation failed")
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


class ToolRegistry:
    """Tiny FastMCP stand-in that captures decorated tool functions."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self.tools: dict[str, Any] = {}

    def tool(self, name: str, description: str):
        """Return a decorator that stores the tool by name."""

        def decorator(fn):
            self.tools[name] = fn
            return fn

        return decorator


def test_ensure_ready_uses_distinct_clients_per_agent(
    fake_api_key: str, monkeypatch
) -> None:
    """Different MCP agents must not share SdkClient session state."""
    monkeypatch.setattr("memanto_mcp.lifecycle.SdkClient", FakeSdkClient)
    FakeSdkClient.instances = []
    FakeSdkClient.missing_agents = set()
    FakeSdkClient.fail_activate_agents = set()

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
    FakeSdkClient.missing_agents = set()
    FakeSdkClient.fail_activate_agents = set()

    lifecycle = MemantoLifecycle(MCPServerSettings())  # type: ignore[call-arg]

    first = lifecycle.ensure_ready("agent-a")
    second = lifecycle.ensure_ready("agent-a")

    assert first is second
    assert first.activated_agents == ["agent-a"]


def test_missing_agent_is_created_with_scoped_client(
    fake_api_key: str, monkeypatch
) -> None:
    """Auto-create should happen on the same scoped client returned later."""
    monkeypatch.setattr("memanto_mcp.lifecycle.SdkClient", FakeSdkClient)
    FakeSdkClient.instances = []
    FakeSdkClient.missing_agents = {"agent-a"}
    FakeSdkClient.fail_activate_agents = set()

    lifecycle = MemantoLifecycle(MCPServerSettings())  # type: ignore[call-arg]

    client = lifecycle.ensure_ready("agent-a")

    assert client.created_agents == ["agent-a"]
    assert client.activated_agents == ["agent-a"]
    assert lifecycle.ensure_ready("agent-a") is client


def test_failed_first_activation_does_not_cache_new_client(
    fake_api_key: str, monkeypatch
) -> None:
    """A failed readiness check should not leave a new scoped client cached."""
    monkeypatch.setattr("memanto_mcp.lifecycle.SdkClient", FakeSdkClient)
    FakeSdkClient.instances = []
    FakeSdkClient.missing_agents = set()
    FakeSdkClient.fail_activate_agents = {"agent-a"}

    lifecycle = MemantoLifecycle(MCPServerSettings())  # type: ignore[call-arg]

    try:
        lifecycle.ensure_ready("agent-a")
    except Exception:
        pass

    failed_client = FakeSdkClient.instances[-1]
    FakeSdkClient.fail_activate_agents = set()
    recovered_client = lifecycle.ensure_ready("agent-a")

    assert recovered_client is not failed_client
    assert recovered_client.activated_agents == ["agent-a"]


def test_batch_remember_validates_before_lifecycle_side_effects(
    fake_api_key: str, monkeypatch
) -> None:
    """Invalid batch payloads should fail before creating or activating agents."""
    monkeypatch.setattr("memanto_mcp.lifecycle.SdkClient", FakeSdkClient)
    FakeSdkClient.instances = []
    FakeSdkClient.missing_agents = set()
    FakeSdkClient.fail_activate_agents = set()

    lifecycle = MemantoLifecycle(MCPServerSettings())  # type: ignore[call-arg]
    registry = ToolRegistry()
    register_tools(registry, lifecycle)

    result = registry.tools["batch_remember"](
        memories=[{"content": "   "}],
        agent_id="agent-a",
    )

    assert result.status == "error"
    # Only the admin client from lifecycle construction should exist.
    assert len(FakeSdkClient.instances) == 1
