from unittest.mock import MagicMock, patch
import pytest
import sys
from pathlib import Path

# Add examples/langgraph-memanto to sys.path to import agent directly
LANGGRAPH_DIR = Path(__file__).parent.parent / "examples" / "langgraph-memanto"
sys.path.insert(0, str(LANGGRAPH_DIR))

from agent import build_agent_graph


def test_langgraph_workflow_compilation():
    """Verify that the LangGraph workflow compiles correctly and contains the expected nodes."""
    graph = build_agent_graph()
    assert graph is not None
    # Verify compiled graph structure by checking its node keys
    assert "recall_context" in graph.nodes
    assert "generate_reply" in graph.nodes
    assert "extract_memory" in graph.nodes


@patch("agent.get_memanto_client")
def test_langgraph_workflow_execution(mock_get_client):
    """Verify end-to-end execution of compiled graph nodes with SdkClient mocking."""
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    # Mock recall payload
    mock_client.recall.return_value = {
        "memories": [
            {
                "type": "preference",
                "title": "User Preference",
                "content": "The user prefers dark mode.",
                "confidence": 0.9,
                "tags": ["profile"]
            }
        ]
    }
    
    # Mock RAG answer payload
    mock_client.answer.return_value = {
        "answer": "Grounded response: Hello Alice, I see you prefer dark mode."
    }

    graph = build_agent_graph()

    # Day 1: Test with name introduction and preference statement
    state = {
        "user_id": "test-user-123",
        "messages": [{"role": "user", "content": "My name is Alice and I prefer dark mode."}],
        "active_memory": "",
        "latest_reply": "",
    }

    output_state = graph.invoke(state)

    # Assert recall was executed with the user message query
    mock_client.recall.assert_called_once_with(
        agent_id="test-user-123",
        query="My name is Alice and I prefer dark mode.",
        limit=3,
        min_similarity=0.35
    )

    # Assert RAG answer was called grounded in the recalled memory
    mock_client.answer.assert_called_once()
    assert "Alice" in mock_client.answer.call_args[1]["question"]

    # Assert remember was called to extract:
    # 1. Identity (Name: Alice)
    # 2. Preference (dark mode)
    assert mock_client.remember.call_count == 2
    
    first_remember_args = mock_client.remember.call_args_list[0][1]
    assert first_remember_args["memory_type"] == "fact"
    assert "Alice" in first_remember_args["content"]

    second_remember_args = mock_client.remember.call_args_list[1][1]
    assert second_remember_args["memory_type"] == "preference"
    assert "dark mode" in second_remember_args["content"]

    # Check output state
    assert output_state["active_memory"] is not None
    assert "dark mode" in output_state["active_memory"]
    assert "Grounded response:" in output_state["latest_reply"]
