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


def _ctx(user_id: str, tenant_id: str | None = "acme", agent: str = "support"):
    return TurnContext(
        runtime_session_id="rt",
        user_id=user_id,
        agent_name=agent,
        tenant_id=tenant_id,
    )


@pytest.mark.parametrize(
    ("victim", "attacker"),
    [
        # Punctuation used to be folded to "_".
        (_ctx("john.doe@acme.com"), _ctx("john_doe@acme.com")),
        (_ctx("john.doe@acme.com"), _ctx("john@doe.acme.com")),
        (_ctx("alice.smith"), _ctx("alice smith")),
        # Runs of non-ASCII characters used to collapse to a single "_".
        (_ctx("Мария"), _ctx("Иван")),
        (_ctx("田中"), _ctx("佐藤")),
        # Delimiters inside a component used to shift the tenant/user split.
        (_ctx("c", tenant_id="a-user-b"), _ctx("b-user-c", tenant_id="a")),
        (_ctx("user-b", tenant_id="a"), _ctx("b", tenant_id="a-user")),
        (_ctx("u", agent="x-agent-y"), _ctx("u-agent-x", agent="y")),
        # Surrounding whitespace is part of the identity, not normalized away.
        (_ctx("alice "), _ctx(" alice")),
    ],
)
def test_default_agent_id_resolver_keeps_distinct_identities_apart(victim, attacker):
    assert default_agent_id_resolver(victim) != default_agent_id_resolver(attacker)


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        (_ctx("u42"), "tenant-acme-user-u42-agent-support"),
        (
            _ctx("u42", agent="support-agent"),
            "tenant-acme-user-u42-agent-support-agent",
        ),
        (_ctx("user_42", tenant_id=None), "tenant-default-user-user_42-agent-support"),
        (
            _ctx("3f2a9c1e-7b4d", tenant_id="t-1"),
            "tenant-t-1-user-3f2a9c1e-7b4d-agent-support",
        ),
    ],
)
def test_default_agent_id_resolver_keeps_unambiguous_ids_stable(context, expected):
    # IDs that were already collision-free keep their existing namespace.
    assert default_agent_id_resolver(context) == expected


def test_default_agent_id_resolver_hashes_to_valid_agent_ids():
    agent_id = default_agent_id_resolver(_ctx("john.doe@acme.com"))
    assert len(agent_id) == 64
    assert all(ch in "0123456789abcdef" for ch in agent_id)


def test_default_agent_id_resolver_rejects_structured_separator():
    with pytest.raises(AgentResolutionError):
        default_agent_id_resolver(_ctx("a\x1fb"))


def test_default_agent_id_resolver_is_injective_over_fuzzed_identities():
    import random

    rng = random.Random(1852)
    alphabet = "ab-_.@ ü田"
    delimiters = ["", "-user-", "-agent-", "user", "agent", "-"]
    seen: dict[str, tuple] = {}
    for _ in range(20_000):
        parts = []
        for _ in range(3):
            chunks = [
                rng.choice(delimiters)
                + "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 3)))
                for _ in range(rng.randint(1, 2))
            ]
            parts.append("".join(chunks))
        tenant, user, agent = parts
        if not user.strip() or not agent.strip():
            continue
        key = (tenant or "default", user, agent)
        agent_id = default_agent_id_resolver(_ctx(user, tenant or None, agent))
        assert seen.setdefault(agent_id, key) == key, (agent_id, key, seen[agent_id])
