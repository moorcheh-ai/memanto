"""Session isolation tests for the MCP lifecycle."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from memanto.app.utils.errors import AgentNotFoundError, SessionError

import memanto_mcp.lifecycle as lifecycle_module
from memanto_mcp.config import MCPServerSettings
from memanto_mcp.lifecycle import MemantoLifecycle
from memanto_mcp.tools import register_tools


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
    errors: list[Exception] = []

    def recall_first_agent() -> None:
        try:
            first_client = lifecycle.client_for("agent-a")
            first_ready.set()
            assert second_ready.wait(timeout=2)
            assert first_client.recall(agent_id="agent-a") == {"agent_id": "agent-a"}
        except Exception as exc:  # pragma: no cover - reported in main thread
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


def test_unique_agent_ids_cannot_grow_session_registry_without_bound(
    lifecycle: MemantoLifecycle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Capacity pressure rejects new IDs without disturbing existing clients."""
    monkeypatch.setattr(lifecycle, "_MAX_SESSION_CLIENTS", 2)

    first_client = lifecycle.client_for("agent-a")
    lifecycle.client_for("agent-b")

    with pytest.raises(SessionError, match=r"capacity reached \(2\)"):
        lifecycle.client_for("agent-c")

    assert lifecycle.client_for("agent-a") is first_client
    assert set(lifecycle._session_clients) == {"agent-a", "agent-b"}
    assert set(lifecycle._agent_locks) == {"agent-a", "agent-b"}
    assert lifecycle._ensured_agents == {"agent-a", "agent-b"}
    assert len(_FakeSdkClient.instances) == 3  # admin + two bounded sessions


def test_different_agents_initialize_in_parallel(
    lifecycle: MemantoLifecycle, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Network setup for one agent must not block an unrelated agent."""
    activation_barrier = threading.Barrier(2)
    original_activate = _FakeSdkClient.activate_agent
    clients: list[_FakeSdkClient] = []
    errors: list[Exception] = []

    def synchronized_activate(
        client: _FakeSdkClient,
        agent_id: str,
        duration_hours: int | None = None,
    ) -> dict[str, Any]:
        activation_barrier.wait(timeout=2)
        return original_activate(client, agent_id, duration_hours)

    monkeypatch.setattr(_FakeSdkClient, "activate_agent", synchronized_activate)

    def initialize(agent_id: str) -> None:
        try:
            clients.append(lifecycle.client_for(agent_id))
        except Exception as exc:  # pragma: no cover - reported in main thread
            errors.append(exc)

    workers = [
        threading.Thread(target=initialize, args=("agent-a",)),
        threading.Thread(target=initialize, args=("agent-b",)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)

    assert all(not worker.is_alive() for worker in workers)
    assert not errors
    assert {client.agent_id for client in clients} == {"agent-a", "agent-b"}


class FakeSdkClient:
    """Small stateful stand-in for SdkClient.

    The real SdkClient stores ``agent_id`` and ``session_token`` on the client
    instance. These tests make that mutable state visible without hitting the
    network.
    """

    instances: list[FakeSdkClient] = []
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

    def remember(
        self, content: str, role: str, *, agent_id: str, **_: Any
    ) -> dict[str, str]:
        """Fail if a memory call uses a client scoped to another agent."""
        if self.agent_id != agent_id:
            raise AssertionError(f"client for {self.agent_id!r} used for {agent_id!r}")
        return {"memory_id": f"mem-{agent_id}", "status": "ok"}


class ToolRegistry:
    """Tiny FastMCP stand-in that captures decorated tool functions."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self.tools: dict[str, Any] = {}

    def tool(self, name: str, description: str):
        """Return a decorator that stores the tool by name."""

        def decorator(fn):
            """Store one decorated tool function and return it unchanged."""
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
    assert (
        agent_a_client.remember("test", "user", agent_id="agent-a")["memory_id"]
        == "mem-agent-a"
    )
    assert (
        agent_b_client.remember("test", "user", agent_id="agent-b")["memory_id"]
        == "mem-agent-b"
    )


def test_repeated_agent_reuses_its_scoped_client(
    fake_api_key: str, monkeypatch
) -> None:
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

    monkeypatch.setenv("MEMANTO_DEFAULT_AGENT_ID", "agent-a")
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

    with pytest.raises(Exception, match="Failed to activate Memanto session"):
        lifecycle.ensure_ready("agent-a")

    failed_client = FakeSdkClient.instances[-1]
    FakeSdkClient.fail_activate_agents = set()
    recovered_client = lifecycle.ensure_ready("agent-a")
    cached_client = lifecycle.ensure_ready("agent-a")

    assert recovered_client is not failed_client
    assert cached_client is recovered_client
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
    assert FakeSdkClient.instances[0].created_agents == []
    assert FakeSdkClient.instances[0].activated_agents == []


def test_auto_create_is_limited_to_default_agent(
    fake_api_key: str, monkeypatch
) -> None:
    """Only the configured default agent can be auto-created; arbitrary IDs fail."""
    monkeypatch.setattr("memanto_mcp.lifecycle.SdkClient", FakeSdkClient)
    FakeSdkClient.instances = []
    FakeSdkClient.missing_agents = {"project-agent", "attacker-agent"}
    FakeSdkClient.fail_activate_agents = set()

    monkeypatch.setenv("MEMANTO_DEFAULT_AGENT_ID", "project-agent")
    lifecycle = MemantoLifecycle(MCPServerSettings())  # type: ignore[call-arg]

    # 1. Arbitrary agent fails and does not auto-create
    with pytest.raises(AgentNotFoundError, match="Only the configured default agent"):
        lifecycle.ensure_ready("attacker-agent")

    # Ensure no client recorded the creation of "attacker-agent"
    assert not any(
        "attacker-agent" in c.created_agents for c in FakeSdkClient.instances
    )

    # 2. Configured default agent succeeds and auto-creates
    client = lifecycle.ensure_ready("project-agent")
    assert client.created_agents == ["project-agent"]
    assert client.activated_agents == ["project-agent"]
