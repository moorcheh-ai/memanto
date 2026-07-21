import pytest
from memanto.mcp.lifecycle import McpLifecycle

def test_client_for_creates_new_client():
    lifecycle = McpLifecycle()
    client1 = lifecycle.client_for("agent1")
    client2 = lifecycle.client_for("agent2")

    assert client1 is not client2
    assert lifecycle.client_for("agent1") is client1

def test_admin_client_is_shared():
    lifecycle = McpLifecycle()
    admin_client = lifecycle.client

    assert lifecycle.client is admin_client

def test_cleanup_closes_all_clients():
    lifecycle = McpLifecycle()
    client1 = lifecycle.client_for("agent1")
    client2 = lifecycle.client_for("agent2")

    lifecycle.cleanup()

    assert client1.active_agent is None
    assert client2.active_agent is None
    assert len(lifecycle._agent_clients) == 0