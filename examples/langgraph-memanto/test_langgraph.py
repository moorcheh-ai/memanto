"""
Tests for LangGraph + Memanto Integration.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from agent import AgentState, MemantoMemoryManager, build_agent_graph
from langchain_core.messages import AIMessage, HumanMessage
from memanto.app.utils.errors import AgentAlreadyExistsError


@pytest.fixture
def mock_sdk_client():
    """Mock the SdkClient to avoid remote API calls during tests."""
    with patch("agent.SdkClient") as mock_cls:
        client_instance = MagicMock()
        mock_cls.return_value = client_instance

        # Mock default return values
        client_instance.create_agent.return_value = {"status": "created"}
        client_instance.activate_agent.return_value = {"status": "active"}
        client_instance.deactivate_agent.return_value = {"status": "inactive"}
        client_instance.remember.return_value = {"memory_id": "mock-mem-123"}
        client_instance.recall.return_value = {
            "memories": [
                {
                    "type": "preference",
                    "title": "Programming Language Preference",
                    "content": "The user prefers coding in Python.",
                }
            ],
            "count": 1,
        }

        yield client_instance


def test_memory_manager_initialize(mock_sdk_client):
    """Test that initialize creates the agent and activates the session."""
    mgr = MemantoMemoryManager(api_key="test-api-key", agent_id="test-agent")
    mgr.initialize()

    assert mgr.initialized is True
    mock_sdk_client.create_agent.assert_called_once_with(
        agent_id="test-agent",
        pattern="tool",
        description="Long term memory layer for LangGraph agents",
    )
    mock_sdk_client.activate_agent.assert_called_once_with("test-agent", duration_hours=12)


def test_memory_manager_recall(mock_sdk_client):
    """Test that recall delegates to SDK client correctly."""
    mgr = MemantoMemoryManager(api_key="test-api-key", agent_id="test-agent")
    memories = mgr.recall_memories("What is my favorite language?")

    assert len(memories) == 1
    assert memories[0]["content"] == "The user prefers coding in Python."
    mock_sdk_client.recall.assert_called_once_with(
        agent_id="test-agent",
        query="What is my favorite language?",
        limit=3,
        min_similarity=0.45,
    )


def test_agent_graph_execution_recall_and_llm(mock_sdk_client):
    """Test full LangGraph execution for memory recall node."""
    mgr = MemantoMemoryManager(api_key="test-api-key", agent_id="test-agent")
    workflow = build_agent_graph(mgr)
    app = workflow.compile()

    state = {
        "messages": [HumanMessage(content="What programming language do I prefer?")],
        "user_id": "user-123",
        "recalled_memories": [],
        "new_memories_extracted": [],
    }

    outputs = app.invoke(state)

    # Verify memory recall node functioned
    assert len(outputs["recalled_memories"]) == 1
    assert outputs["recalled_memories"][0]["content"] == "The user prefers coding in Python."

    # Verify LLM node referenced the recalled memory
    final_message = outputs["messages"][-1]
    assert isinstance(final_message, AIMessage)
    assert "coding in Python" in final_message.content


def test_agent_graph_execution_extraction(mock_sdk_client):
    """Test full LangGraph execution for active memory extraction node."""
    mgr = MemantoMemoryManager(api_key="test-api-key", agent_id="test-agent")
    workflow = build_agent_graph(mgr)
    app = workflow.compile()

    state = {
        "messages": [HumanMessage(content="My name is Alex.")],
        "user_id": "user-123",
        "recalled_memories": [],
        "new_memories_extracted": [],
    }

    # Execute graph
    outputs = app.invoke(state)

    # Verify active extraction saved the memory
    assert len(outputs["new_memories_extracted"]) == 1
    assert "Alex" in outputs["new_memories_extracted"][0]["content"]

    mock_sdk_client.remember.assert_called_once()
    call_args = mock_sdk_client.remember.call_args[1]
    assert call_args["agent_id"] == "test-agent"
    assert call_args["memory_type"] == "fact"
    assert "Alex" in call_args["content"]
