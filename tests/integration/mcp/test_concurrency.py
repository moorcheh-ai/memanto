import pytest
from memanto.mcp.lifecycle import McpLifecycle

@pytest.mark.asyncio
async def test_concurrent_agent_sessions():
    lifecycle = McpLifecycle()

    # Simulate concurrent requests for different agents
    client1 = lifecycle.client_for("agent1")
    client2 = lifecycle.client_for("agent2")

    # Activate sessions
    client1.activate("agent1", "session1")
    client2.activate("agent2", "session2")

    # Verify isolation
    assert client1.active_agent == "agent1"
    assert client1.active_session == "session1"
    assert client2.active_agent == "agent2"
    assert client2.active_session == "session2"

    # Verify same-agent client reuse
    assert lifecycle.client_for("agent1") is client1