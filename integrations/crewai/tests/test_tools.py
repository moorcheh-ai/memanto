from unittest.mock import MagicMock

from crewai_memanto.tools import (
    MemantoAnswerTool,
    MemantoRecallTool,
    MemantoRememberTool,
    MemantoSetup,
)

from memanto.app.utils.errors import AgentAlreadyExistsError


def test_memanto_setup_create_new_agent():
    setup = MemantoSetup(api_key="test_key")
    setup.client = MagicMock()

    client = setup.setup(agent_id="test-agent", pattern="tool", duration_hours=4)

    assert client == setup.client
    setup.client.create_agent.assert_called_once_with(
        agent_id="test-agent", pattern="tool", description=None
    )
    setup.client.activate_agent.assert_called_once_with("test-agent", duration_hours=4)


def test_memanto_setup_agent_exists():
    setup = MemantoSetup(api_key="test_key")
    setup.client = MagicMock()
    setup.client.create_agent.side_effect = AgentAlreadyExistsError("test-agent")

    # Should catch the error and still activate
    client = setup.setup(agent_id="test-agent")

    assert client == setup.client
    setup.client.create_agent.assert_called_once()
    setup.client.activate_agent.assert_called_once_with("test-agent", duration_hours=6)


def test_memanto_setup_teardown():
    setup = MemantoSetup(api_key="test_key")
    setup.client = MagicMock()

    setup.teardown("test-agent")
    setup.client.deactivate_agent.assert_called_once_with("test-agent")


def test_memanto_remember_tool():
    client = MagicMock()
    client.remember.return_value = {"memory_id": "mem-123"}

    tool = MemantoRememberTool(client=client, agent_id="test-agent")

    # Simulate crewai calling the tool
    result = tool._run(
        memory_type="fact",
        title="Test Fact",
        content="The content",
        confidence=0.9,
        tags="tag1, tag2 ",
    )

    assert "Memory stored successfully" in result
    assert "mem-123" in result
    assert "fact" in result

    client.remember.assert_called_once_with(
        agent_id="test-agent",
        memory_type="fact",
        title="Test Fact",
        content="The content",
        confidence=0.9,
        tags=["tag1", "tag2"],
        source="crewai-agent",
        provenance="explicit_statement",
    )


def test_memanto_recall_tool_success():
    client = MagicMock()
    client.recall.return_value = {
        "memories": [
            {
                "id": "mem-123",
                "type": "fact",
                "title": "Fact 1",
                "content": "Content 1",
                "confidence": 0.8,
                "tags": ["test"],
            }
        ]
    }

    tool = MemantoRecallTool(client=client, agent_id="test-agent")
    result = tool._run(
        query="test query", limit=5, memory_types="fact", min_similarity=0.7
    )

    assert "Found 1 memories for 'test query'" in result
    assert "Fact 1" in result
    assert "Content 1" in result

    client.recall.assert_called_once_with(
        agent_id="test-agent",
        query="test query",
        limit=5,
        type=["fact"],
        min_similarity=0.7,
    )


def test_memanto_recall_tool_empty():
    client = MagicMock()
    client.recall.return_value = {"memories": []}

    tool = MemantoRecallTool(client=client, agent_id="test-agent")
    result = tool._run(query="test query")

    assert result == "No memories found for query: 'test query'"


def test_memanto_answer_tool_success():
    client = MagicMock()
    client.answer.return_value = {
        "answer": "This is the answer.",
        "sources": [{"id": "mem-1"}],
    }

    tool = MemantoAnswerTool(client=client, agent_id="test-agent")
    result = tool._run(question="What is this?")

    assert "Answer: This is the answer." in result
    assert "Based on 1 memory source(s)." in result

    client.answer.assert_called_once_with(
        agent_id="test-agent", question="What is this?"
    )


def test_memanto_answer_tool_no_answer():
    client = MagicMock()
    client.answer.return_value = {}

    tool = MemantoAnswerTool(client=client, agent_id="test-agent")
    result = tool._run(question="What is this?")

    assert "Answer: No answer could be generated." in result
