import threading
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph_memanto.nodes import (
    _PerAgentClientCache,
    create_recall_node,
    create_remember_node,
)

from memanto.app.utils.errors import SessionError as MementoSessionError

# All tests that use a MagicMock client need to patch the SdkClient constructor
# inside nodes.py so that _PerAgentClientCache returns the original mock instead
# of trying to create a real SdkClient (which would raise SessionError).
_PATCH = "langgraph_memanto.nodes.SdkClient"


def test_recall_node():
    client = MagicMock()
    client.activate_agent.return_value = {"session_token": "mock-token"}
    client.recall.return_value = {
        "memories": [{"title": "Test Title", "content": "Test Content", "type": "fact"}]
    }

    node = create_recall_node(client=client, agent_id="test-agent")

    state = {"messages": [HumanMessage(content="What is my name?")]}

    with patch(_PATCH, return_value=client):
        result = node(state)

    assert "messages" in result
    assert len(result["messages"]) == 1
    sys_msg = result["messages"][0]
    assert isinstance(sys_msg, SystemMessage)
    assert "Relevant memories:" in sys_msg.content
    assert "Test Content" in sys_msg.content

    client.recall.assert_called_once_with(
        agent_id="test-agent", query="What is my name?"
    )


def test_remember_node():
    client = MagicMock()
    client.activate_agent.return_value = {"session_token": "mock-token"}

    node = create_remember_node(client=client, agent_id="test-agent")

    state = {"messages": [HumanMessage(content="My name is Bob.")]}

    with patch(_PATCH, return_value=client):
        result = node(state)

    assert result == {"messages": []}

    client.remember.assert_called_once_with(
        agent_id="test-agent",
        memory_type=None,
        title="My name is Bob.",
        content="My name is Bob.",
        source="langgraph-node",
        provenance="explicit_statement",
    )


def test_dynamic_agent_id_from_config():
    client = MagicMock()
    client.activate_agent.return_value = {"session_token": "mock-token"}
    client.recall.return_value = {"memories": []}

    recall = create_recall_node(client=client, agent_id_from_config="custom_id")
    remember = create_remember_node(client=client, agent_id_from_config="custom_id")

    config = {"configurable": {"custom_id": "dynamic-user-123"}}

    state = {"messages": [HumanMessage(content="Hello")]}

    with patch(_PATCH, return_value=client):
        recall(state, config=config)
        remember(state, config=config)

    client.recall.assert_called_once_with(agent_id="dynamic-user-123", query="Hello")
    client.remember.assert_called_once_with(
        agent_id="dynamic-user-123",
        memory_type=None,
        title="Hello",
        content="Hello",
        source="langgraph-node",
        provenance="explicit_statement",
    )


def test_recall_no_human_message():
    client = MagicMock()
    node = create_recall_node(client=client, agent_id="test-agent")

    state = {"messages": [SystemMessage(content="You are a helpful assistant")]}
    result = node(state)

    assert result == {"messages": []}
    client.recall.assert_not_called()


def test_recall_no_results():
    client = MagicMock()
    client.recall.return_value = {"memories": []}
    node = create_recall_node(client=client, agent_id="test-agent")

    state = {"messages": [HumanMessage(content="hello")]}
    with patch(_PATCH, return_value=client):
        result = node(state)

    assert result == {"messages": []}


def test_recall_handles_error_gracefully():
    client = MagicMock()
    client.activate_agent.return_value = {"session_token": "mock-token"}
    client.recall.side_effect = Exception("connection refused")
    node = create_recall_node(client=client, agent_id="test-agent")

    state = {"messages": [HumanMessage(content="hello")]}
    with patch(_PATCH, return_value=client):
        result = node(state)

    assert result == {"messages": []}


def test_recall_output_key():
    client = MagicMock()
    client.activate_agent.return_value = {"session_token": "mock-token"}
    client.recall.return_value = {
        "memories": [{"title": "Fact 1", "content": "Python is cool", "type": "fact"}]
    }

    node = create_recall_node(
        client=client, agent_id="test-agent", output_key="my_memory_context"
    )

    state = {"messages": [HumanMessage(content="What do you remember?")]}
    with patch(_PATCH, return_value=client):
        result = node(state)

    assert "messages" not in result
    assert "my_memory_context" in result
    assert "Python is cool" in result["my_memory_context"]


def test_remember_both_human_and_ai():
    client = MagicMock()
    client.activate_agent.return_value = {"session_token": "mock-token"}
    node = create_remember_node(
        client=client, agent_id="test-agent", remember_human=True, remember_ai=True
    )

    state = {
        "messages": [HumanMessage(content="I like pizza"), AIMessage(content="Got it!")]
    }

    with patch(_PATCH, return_value=client):
        result = node(state)
    assert result == {"messages": []}

    assert client.remember.call_count == 1

    call_kwargs = client.remember.call_args[1]
    assert "I like pizza" in call_kwargs["content"]
    assert "Got it!" in call_kwargs["content"]


def test_remember_skips_when_no_messages_match():
    client = MagicMock()
    node = create_remember_node(
        client=client, agent_id="test-agent", remember_human=False, remember_ai=False
    )

    state = {"messages": [HumanMessage(content="hello")]}
    result = node(state)

    assert result == {"messages": []}
    client.remember.assert_not_called()


def test_remember_handles_error_gracefully():
    client = MagicMock()
    client.activate_agent.return_value = {"session_token": "mock-token"}
    client.remember.side_effect = Exception("connection refused")
    node = create_remember_node(client=client, agent_id="test-agent")

    state = {"messages": [HumanMessage(content="hello")]}

    with patch(_PATCH, return_value=client):
        result = node(state)
    assert result == {"messages": []}


def test_skips_when_no_agent_id():
    client = MagicMock()
    recall = create_recall_node(client=client)
    remember = create_remember_node(client=client)

    state = {"messages": [HumanMessage(content="hello")]}

    # Passing empty config so no agent_id can be resolved
    assert recall(state, config={}) == {"messages": []}
    assert remember(state, config={}) == {"messages": []}

    client.recall.assert_not_called()
    client.remember.assert_not_called()


# ── Cross-tenant session leak regression tests ────────────────────────────────
# Bug: _do_setup mutated client.session_token / client.agent_id on the shared
# SdkClient instance. Concurrent runs for different agent_ids raced on these
# fields — the last writer won, causing auth failures or cross-tenant data leaks.
# Fix: each agent_id gets its own SdkClient via _PerAgentClientCache.


def test_per_agent_client_cache_returns_distinct_clients():
    """Each agent_id must get a different SdkClient instance."""
    template = MagicMock(spec=["api_key"])
    template.api_key = "test-key"

    alice_mock = MagicMock()
    bob_mock = MagicMock()
    mocks = iter([alice_mock, bob_mock])

    with patch(_PATCH, side_effect=lambda api_key: next(mocks)):
        cache = _PerAgentClientCache(template)
        alice_client, alice_lock = cache.get("alice")
        bob_client, bob_lock = cache.get("bob")
        alice_client_again, alice_lock_again = cache.get("alice")

    assert alice_client is not bob_client, (
        "Different agent_ids must get different clients"
    )
    assert alice_client is alice_client_again, (
        "Same agent_id must always get the same client"
    )


def test_concurrent_recall_nodes_do_not_share_session_state():
    """Concurrent recall calls for different agent_ids must not interfere.

    Regression test for the cross-tenant session leak: before the fix,
    _do_setup wrote to client.session_token on the shared instance, so the last
    concurrent writer would clobber all other agents' sessions.
    """
    agent_ids = ["alice", "bob", "carol", "dave"]

    # Build one mock per agent — each returns only its own memories.
    per_agent_mocks: dict[str, MagicMock] = {}
    for aid in agent_ids:
        m = MagicMock()
        m.api_key = "test-key"
        m.recall.return_value = {
            "memories": [
                {"title": f"Memory of {aid}", "content": f"data:{aid}", "type": "fact"}
            ]
        }
        per_agent_mocks[aid] = m

    template_client = MagicMock()
    template_client.api_key = "test-key"

    recall_node = create_recall_node(template_client, agent_id_from_config="agent_id")

    # Inject per-agent mocks so each cache.get(agent_id) returns the right mock.
    # Locate _cache by name to stay stable if the closure layout changes.
    freevars = recall_node.__code__.co_freevars
    cache = recall_node.__closure__[freevars.index("_cache")].cell_contents
    cache._clients = {k: (v, threading.Lock()) for k, v in per_agent_mocks.items()}

    barrier = threading.Barrier(len(agent_ids))
    results: list[tuple[str, dict]] = []
    lock = threading.Lock()

    def run_recall(aid: str) -> None:
        barrier.wait()  # all threads start simultaneously
        state = {"messages": [HumanMessage(content=f"Hello I am {aid}")]}
        config = {"configurable": {"agent_id": aid}}
        result = recall_node(state, config=config)
        with lock:
            results.append((aid, result))

    threads = [threading.Thread(target=run_recall, args=(aid,)) for aid in agent_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == len(agent_ids)
    for aid, result in results:
        msgs = result.get("messages", [])
        assert msgs, f"agent '{aid}' got no memories — possible cross-tenant failure"
        memory_text = msgs[0].content
        assert f"data:{aid}" in memory_text, (
            f"agent '{aid}' received wrong memories — cross-tenant leak detected.\n"
            f"Got: {memory_text}"
        )


def test_remember_retries_only_on_session_error():
    """SessionError triggers _do_setup + retry; other exceptions do not retry.

    Regression for the broad-except bug: before the fix, any exception (including
    post-write network errors) would trigger a retry, potentially storing duplicate
    memories. Now only SessionError — which SdkClient always raises before writing —
    triggers the retry path.
    """
    client = MagicMock()
    client.activate_agent.return_value = {"session_token": "mock-token"}

    # First call raises SessionError (pre-write), second call succeeds.
    client.remember.side_effect = [MementoSessionError("no active session"), None]

    node = create_remember_node(client=client, agent_id="test-agent")
    state = {"messages": [HumanMessage(content="hello")]}

    with patch(_PATCH, return_value=client):
        result = node(state)

    assert result == {"messages": []}
    assert client.activate_agent.call_count == 1, "setup must trigger on SessionError"
    assert client.remember.call_count == 2, "remember must be retried after setup"


def test_remember_does_not_retry_on_generic_error():
    """A non-session exception must NOT trigger a retry (avoids duplicate writes)."""
    client = MagicMock()
    client.remember.side_effect = RuntimeError("network timeout")

    node = create_remember_node(client=client, agent_id="test-agent")
    state = {"messages": [HumanMessage(content="hello")]}

    with patch(_PATCH, return_value=client):
        result = node(state)

    assert result == {"messages": []}
    assert client.activate_agent.call_count == 0, (
        "setup must NOT trigger on non-session error"
    )
    assert client.remember.call_count == 1, (
        "remember must NOT be retried on non-session error"
    )
