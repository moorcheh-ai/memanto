import threading
import time
from typing import Any
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph_memanto.nodes import create_recall_node, create_remember_node


def test_recall_node():
    client = MagicMock()
    client.activate_agent.return_value = {"session_token": "mock-token"}
    client.recall.return_value = {
        "memories": [{"title": "Test Title", "content": "Test Content", "type": "fact"}]
    }

    node = create_recall_node(client=client, agent_id="test-agent")

    state = {"messages": [HumanMessage(content="What is my name?")]}

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
    result = node(state)

    assert result == {"messages": []}


def test_recall_handles_error_gracefully():
    client = MagicMock()
    client.activate_agent.return_value = {"session_token": "mock-token"}
    client.recall.side_effect = Exception("connection refused")
    node = create_recall_node(client=client, agent_id="test-agent")

    state = {"messages": [HumanMessage(content="hello")]}
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


def test_concurrent_agent_ids_do_not_cross_contaminate():
    """Two recall nodes for different agent_ids sharing one client must not
    clobber session_token / agent_id when called concurrently (issue #884).

    _StrictClient mirrors the SdkClient invariant that the active agent_id must
    match the caller's.  Without the per-client lock, thread-A activates "alice",
    thread-B activates "bob" (clobber), and thread-A's retry-recall raises a
    SessionError which is silently swallowed — returning no memories.
    Runs 10 iterations with simultaneous thread starts so the race window is
    reliably hit even without the fix.
    """

    class _StrictClient:
        def __init__(self) -> None:
            self.agent_id: str | None = None
            self.session_token: str | None = None

        def create_agent(self, agent_id: str, pattern: str | None = None) -> None:
            pass

        def activate_agent(
            self, agent_id: str, duration_hours: int | None = None
        ) -> dict[str, str]:
            self.agent_id = agent_id
            self.session_token = f"tok-{agent_id}"
            # Yield the GIL so the other thread can race in and clobber
            # agent_id before this thread's retry-recall executes.
            time.sleep(0.001)
            return {"session_token": self.session_token}

        def recall(self, agent_id: str, query: str) -> dict[str, Any]:
            if self.agent_id != agent_id:
                raise RuntimeError(
                    f"cross-tenant: client.agent_id={self.agent_id!r}, "
                    f"recall for {agent_id!r}"
                )
            return {
                "memories": [
                    {
                        "title": f"{agent_id}-mem",
                        "content": f"secret-{agent_id}",
                        "type": "fact",
                    }
                ]
            }

    violations: list[str] = []
    worker_errors: list[str] = []

    for _ in range(10):
        client = _StrictClient()
        alice_node = create_recall_node(client=client, agent_id="alice")
        bob_node = create_recall_node(client=client, agent_id="bob")
        barrier = threading.Barrier(2)

        def run(node: Any, name: str) -> None:
            try:
                barrier.wait()  # start both threads at exactly the same instant
                result = node({"messages": [HumanMessage(content="hi")]})
                if f"secret-{name}" not in str(result):
                    violations.append(
                        f"{name} got wrong/empty memories (session clobber?): {result}"
                    )
            except Exception as exc:  # noqa: BLE001
                worker_errors.append(f"{name}: {exc}")

        threads = [
            threading.Thread(target=run, args=(alice_node, "alice"), name="alice"),
            threading.Thread(target=run, args=(bob_node, "bob"), name="bob"),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert all(not t.is_alive() for t in threads), "worker thread did not finish"

    assert not worker_errors, f"Worker thread raised: {worker_errors[0]}"
    assert not violations, (
        f"Cross-tenant session clobber detected in {len(violations)} case(s): "
        + violations[0]
    )


def test_concurrent_remember_nodes_do_not_cross_contaminate():
    """create_remember_node has the same setup/retry block as create_recall_node
    and must also be safe under concurrent calls for different agent_ids.
    """

    class _StrictRememberClient:
        def __init__(self) -> None:
            self.agent_id: str | None = None

        def create_agent(self, agent_id: str, pattern: str | None = None) -> None:
            pass

        def activate_agent(
            self, agent_id: str, duration_hours: int | None = None
        ) -> dict[str, str]:
            self.agent_id = agent_id
            time.sleep(0.001)
            return {"session_token": f"tok-{agent_id}"}

        def remember(self, agent_id: str, **kwargs: Any) -> None:
            if self.agent_id != agent_id:
                raise RuntimeError(
                    f"cross-tenant: client.agent_id={self.agent_id!r}, "
                    f"remember for {agent_id!r}"
                )

    violations: list[str] = []
    worker_errors: list[str] = []

    for _ in range(10):
        client = _StrictRememberClient()
        alice_node = create_remember_node(client=client, agent_id="alice")
        bob_node = create_remember_node(client=client, agent_id="bob")
        barrier = threading.Barrier(2)

        def run_remember(node: Any, name: str) -> None:
            try:
                barrier.wait()
                node({"messages": [HumanMessage(content=f"I am {name}")]})
            except Exception as exc:  # noqa: BLE001
                violations.append(f"{name}: {exc}")

        threads = [
            threading.Thread(
                target=run_remember, args=(alice_node, "alice"), name="alice"
            ),
            threading.Thread(
                target=run_remember, args=(bob_node, "bob"), name="bob"
            ),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert all(not t.is_alive() for t in threads), "worker thread did not finish"

    assert not worker_errors, f"Worker thread raised: {worker_errors[0]}"
    assert not violations, (
        f"Cross-tenant session clobber in remember_node: {violations[0]}"
    )
