from unittest.mock import MagicMock

import pytest
from langgraph_memanto.tools import create_memanto_tools
from pydantic import ValidationError

from memanto.app.utils.errors import SessionError


def test_create_memanto_tools_returns_all_tools():
    client = MagicMock()
    tools = create_memanto_tools(client, "test-agent")

    assert len(tools) == 3
    tool_names = [t.name for t in tools]
    assert "memanto_remember" in tool_names
    assert "memanto_recall" in tool_names
    assert "memanto_answer" in tool_names


def test_memanto_remember_tool_success():
    client = MagicMock()
    client.remember.return_value = {"memory_id": "mem-123"}

    tools = create_memanto_tools(client, "test-agent")
    remember_tool = next(t for t in tools if t.name == "memanto_remember")

    result = remember_tool.invoke(
        {
            "memory_type": "fact",
            "title": "Test Fact",
            "content": "This is a test fact.",
            "confidence": 0.9,
            "tags": "test, tag2",
        }
    )

    assert result == "Memory stored: mem-123"
    client.remember.assert_called_once_with(
        agent_id="test-agent",
        memory_type="fact",
        title="Test Fact",
        content="This is a test fact.",
        confidence=0.9,
        tags=["test", "tag2"],
        source="langgraph-agent",
    )


def test_memanto_remember_tool_setup_fallback():
    client = MagicMock()
    # A session failure is known to happen before the write begins, so retrying
    # after setup is safe.
    client.remember.side_effect = [
        SessionError("Not initialized"),
        {"memory_id": "mem-456"},
    ]

    tools = create_memanto_tools(client, "test-agent")
    remember_tool = next(t for t in tools if t.name == "memanto_remember")

    result = remember_tool.invoke(
        {
            "memory_type": "goal",
            "title": "Test Goal",
            "content": "This is a test goal.",
            "confidence": 1.0,
            "tags": "",
        }
    )

    assert result == "Memory stored: mem-456"
    assert client.remember.call_count == 2
    client.create_agent.assert_called_once_with(agent_id="test-agent", pattern="tool")
    client.activate_agent.assert_called_once_with("test-agent", duration_hours=6)


def test_memanto_remember_does_not_retry_ambiguous_write_failure():
    """A non-session error may follow a commit and must not be retried."""
    client = MagicMock()
    client.remember.side_effect = ConnectionError("response lost after remote write")

    tools = create_memanto_tools(client, "test-agent")
    remember_tool = next(t for t in tools if t.name == "memanto_remember")

    with pytest.raises(ConnectionError, match="response lost"):
        remember_tool.invoke(
            {
                "memory_type": "fact",
                "title": "Already committed",
                "content": "Retrying this write would create a duplicate.",
                "confidence": 0.9,
                "tags": "integrity",
            }
        )

    client.remember.assert_called_once()
    client.create_agent.assert_not_called()


def test_memanto_remember_retries_setup_after_activation_failure():
    client = MagicMock()
    activated = False
    activation_attempts = 0

    def activate_agent(*_args, **_kwargs):
        nonlocal activated, activation_attempts
        activation_attempts += 1
        if activation_attempts == 1:
            raise Exception("Activation failed")
        activated = True

    def remember(**_kwargs):
        if not activated:
            raise SessionError("Not initialized")
        return {"memory_id": "mem-789"}

    client.activate_agent.side_effect = activate_agent
    client.remember.side_effect = remember

    tools = create_memanto_tools(client, "test-agent")
    remember_tool = next(t for t in tools if t.name == "memanto_remember")
    payload = {
        "memory_type": "goal",
        "title": "Test Goal",
        "content": "This is a test goal.",
        "confidence": 1.0,
        "tags": "",
    }

    with pytest.raises(Exception, match="Not initialized"):
        remember_tool.invoke(payload)

    result = remember_tool.invoke(payload)

    assert result == "Memory stored: mem-789"
    assert client.create_agent.call_count == 2
    assert client.activate_agent.call_count == 2

    fast_path_result = remember_tool.invoke(payload)

    assert fast_path_result == "Memory stored: mem-789"
    assert client.create_agent.call_count == 2
    assert client.activate_agent.call_count == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", ""),
        ("title", "t" * 101),
        ("content", ""),
        ("content", "c" * 10001),
    ],
)
def test_memanto_remember_tool_enforces_documented_limits(field, value):
    client = MagicMock()
    tools = create_memanto_tools(client, "test-agent")
    remember_tool = next(t for t in tools if t.name == "memanto_remember")
    payload = {
        "memory_type": "fact",
        "title": "Valid title",
        "content": "Valid content",
        "confidence": 0.9,
        "tags": "",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        remember_tool.invoke(payload)

    client.remember.assert_not_called()


def test_memanto_recall_tool_success():
    client = MagicMock()
    client.recall.return_value = {
        "memories": [
            {
                "title": "Test Fact",
                "content": "This is a test fact.",
                "type": "fact",
                "confidence": 0.9,
                "tags": ["test"],
            }
        ]
    }

    tools = create_memanto_tools(client, "test-agent")
    recall_tool = next(t for t in tools if t.name == "memanto_recall")

    result = recall_tool.invoke(
        {"query": "test query", "limit": 5, "memory_types": "fact, observation"}
    )

    assert "Found 1 memories for 'test query'" in result
    assert "Test Fact" in result
    assert "This is a test fact" in result
    client.recall.assert_called_once_with(
        agent_id="test-agent", query="test query", limit=5, type=["fact", "observation"]
    )


def test_memanto_recall_tool_no_results():
    client = MagicMock()
    client.recall.return_value = {"memories": []}

    tools = create_memanto_tools(client, "test-agent")
    recall_tool = next(t for t in tools if t.name == "memanto_recall")

    result = recall_tool.invoke(
        {"query": "test query", "limit": 10, "memory_types": ""}
    )

    assert result == "No memories found for query: 'test query'"


def test_memanto_recall_tool_setup_fallback():
    client = MagicMock()
    client.recall.side_effect = [Exception("Not initialized"), {"memories": []}]

    tools = create_memanto_tools(client, "test-agent")
    recall_tool = next(t for t in tools if t.name == "memanto_recall")

    result = recall_tool.invoke(
        {"query": "test query", "limit": 10, "memory_types": ""}
    )

    assert result == "No memories found for query: 'test query'"
    assert client.recall.call_count == 2
    client.create_agent.assert_called_once_with(agent_id="test-agent", pattern="tool")


def test_memanto_answer_tool_success():
    client = MagicMock()
    client.answer.return_value = {
        "answer": "This is a synthesized answer.",
        "sources": [{"id": "mem-1"}, {"id": "mem-2"}],
    }

    tools = create_memanto_tools(client, "test-agent")
    answer_tool = next(t for t in tools if t.name == "memanto_answer")

    result = answer_tool.invoke({"question": "What is the answer?"})

    assert "Answer: This is a synthesized answer." in result
    assert "Based on 2 memory source(s)." in result
    client.answer.assert_called_once_with(
        agent_id="test-agent", question="What is the answer?"
    )


def test_memanto_answer_tool_setup_fallback():
    client = MagicMock()
    client.answer.side_effect = [
        Exception("Not initialized"),
        {"answer": "Fallback answer.", "sources": []},
    ]

    tools = create_memanto_tools(client, "test-agent")
    answer_tool = next(t for t in tools if t.name == "memanto_answer")

    result = answer_tool.invoke({"question": "What?"})

    assert "Answer: Fallback answer." in result
    assert client.answer.call_count == 2
    client.create_agent.assert_called_once_with(agent_id="test-agent", pattern="tool")
