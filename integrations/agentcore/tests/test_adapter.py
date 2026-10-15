from unittest.mock import MagicMock

import pytest
from memanto_agentcore.adapter import (
    AgentResolutionError,
    MemantoRuntimeAdapter,
    TurnContext,
    default_agent_id_resolver,
)


def test_default_agent_id_resolver_requires_user_id():
    ctx = TurnContext(
        runtime_session_id="sess-1",
        user_id="",
        agent_name="bot",
    )
    with pytest.raises(AgentResolutionError):
        default_agent_id_resolver(ctx)


def test_default_agent_id_resolver_stable_across_sessions():
    base = TurnContext(
        runtime_session_id="session-A",
        user_id="user-42",
        agent_name="support",
        tenant_id="acme",
    )
    same_user = TurnContext(
        runtime_session_id="session-B",
        user_id="user-42",
        agent_name="support",
        tenant_id="acme",
    )
    assert default_agent_id_resolver(base) == default_agent_id_resolver(same_user)


@pytest.mark.asyncio
async def test_before_turn_formats_memories():
    client = MagicMock()
    client.recall.return_value = {
        "memories": [
            {"title": "Pref", "content": "Email only", "type": "preference"},
        ]
    }
    adapter = MemantoRuntimeAdapter(client, agent_name="support")
    ctx = TurnContext(
        runtime_session_id="rt-1",
        user_id="u1",
        agent_name="support",
    )

    text = await adapter.before_turn(ctx, query="contact preference")

    assert "Relevant memories:" in text
    assert "Email only" in text
    client.recall.assert_called_once()
    assert client.recall.call_args.kwargs["agent_id"].startswith("tenant-")


@pytest.mark.asyncio
async def test_before_turn_empty_on_recall_failure():
    client = MagicMock()
    client.recall.side_effect = RuntimeError("network down")
    adapter = MemantoRuntimeAdapter(client, agent_name="support")
    ctx = TurnContext(
        runtime_session_id="rt-1",
        user_id="u1",
        agent_name="support",
    )

    assert await adapter.before_turn(ctx, query="hello") == ""


@pytest.mark.asyncio
async def test_run_turn_calls_agent_and_retains():
    client = MagicMock()
    client.recall.return_value = {"memories": []}

    adapter = MemantoRuntimeAdapter(client, agent_name="support", retain_async=False)
    ctx = TurnContext(
        runtime_session_id="rt-1",
        user_id="u1",
        agent_name="support",
    )

    async def fake_agent(payload, memory_context):
        assert payload["prompt"] == "Hi"
        return {"output": "Hello there"}

    result = await adapter.run_turn(
        ctx,
        payload={"prompt": "Hi"},
        agent_callable=fake_agent,
    )

    assert result["output"] == "Hello there"
    client.remember.assert_called_once()
    remember_kwargs = client.remember.call_args.kwargs
    assert "Hi" in remember_kwargs["content"]
    assert "Hello there" in remember_kwargs["content"]


def test_resolve_fails_without_user_id():
    client = MagicMock()
    adapter = MemantoRuntimeAdapter(client, agent_name="support")
    ctx = TurnContext(runtime_session_id="x", user_id="  ", agent_name="support")
    with pytest.raises(AgentResolutionError):
        adapter.resolve_agent_id(ctx)
