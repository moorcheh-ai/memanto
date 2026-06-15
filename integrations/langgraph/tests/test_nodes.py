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
