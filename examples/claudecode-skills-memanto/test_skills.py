"""
Tests for MemantoSkillsHook.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from memory_hook import MemantoSkillsHook
from memanto.app.utils.errors import AgentAlreadyExistsError


@pytest.fixture
def mock_sdk_client():
    """Mock the SdkClient to avoid remote API calls during tests."""
    with patch("memory_hook.SdkClient") as mock_cls:
        client_instance = MagicMock()
        mock_cls.return_value = client_instance
        
        # Mock default return values
        client_instance.create_agent.return_value = {"status": "created"}
        client_instance.activate_agent.return_value = {"status": "active"}
        client_instance.deactivate_agent.return_value = {"status": "inactive"}
        client_instance.remember.return_value = {"memory_id": "mocked-mem-id"}
        client_instance.recall.return_value = {
            "memories": [
                {
                    "type": "preference",
                    "title": "Color Theme Preference",
                    "content": "Use HSL harmonious colors",
                }
            ],
            "count": 1,
        }
        
        yield client_instance


def test_hook_initialize(mock_sdk_client):
    """Test that initialize creates the agent and activates the session."""
    hook = MemantoSkillsHook(api_key="test-api-key", agent_id="test-agent")
    hook.initialize()
    
    assert hook.initialized is True
    mock_sdk_client.create_agent.assert_called_once_with(
        agent_id="test-agent",
        pattern="tool",
        description="Global active memory agent for developer skills integration",
    )
    mock_sdk_client.activate_agent.assert_called_once_with("test-agent", duration_hours=6)


def test_hook_initialize_already_exists(mock_sdk_client):
    """Test that initialize handles existing agent gracefully."""
    mock_sdk_client.create_agent.side_effect = AgentAlreadyExistsError("exists")
    
    hook = MemantoSkillsHook(api_key="test-api-key", agent_id="test-agent")
    hook.initialize()  # Should not raise exception
    
    assert hook.initialized is True
    mock_sdk_client.activate_agent.assert_called_once()


def test_pre_skill_execute(mock_sdk_client):
    """Test context injection on pre_skill_execute."""
    hook = MemantoSkillsHook(api_key="test-api-key", agent_id="test-agent")
    
    context = hook.pre_skill_execute(
        skill_name="/tdd",
        file_path="main.py",
        task_description="Implement auth module",
    )
    
    assert context is not None
    assert "[Memanto Persistent Developer Memory Context]" in context
    assert "[PREFERENCE] Color Theme Preference" in context
    
    # Recall should be called with correct search query
    mock_sdk_client.recall.assert_called_once()
    call_args = mock_sdk_client.recall.call_args[1]
    assert call_args["agent_id"] == "test-agent"
    assert "Implement auth module" in call_args["query"]
    assert "file: main.py" in call_args["query"]


def test_post_skill_execute_preference(mock_sdk_client):
    """Test active extraction of developer preferences."""
    hook = MemantoSkillsHook(api_key="test-api-key", agent_id="test-agent")
    
    input_text = "I prefer to use Tailwind v4 styling."
    output_text = "Generated stylesheet configuration."
    
    res = hook.post_skill_execute(
        skill_name="/grill-with-docs",
        file_path="style.css",
        input_text=input_text,
        output_text=output_text,
    )
    
    assert res is not None
    assert res["type"] == "preference"
    assert "Tailwind v4" in res["content"]
    
    # Remember should be called to persist the preference
    mock_sdk_client.remember.assert_called_once()
    call_args = mock_sdk_client.remember.call_args[1]
    assert call_args["agent_id"] == "test-agent"
    assert call_args["memory_type"] == "preference"
    assert call_args["content"] == input_text


def test_post_skill_execute_decision(mock_sdk_client):
    """Test active extraction of architectural decisions."""
    hook = MemantoSkillsHook(api_key="test-api-key", agent_id="test-agent")
    
    input_text = "Should we use PostgreSQL or MongoDB?"
    output_text = "We decided to use PostgreSQL because of strict schema validation constraints."
    
    res = hook.post_skill_execute(
        skill_name="/architecture",
        file_path=None,
        input_text=input_text,
        output_text=output_text,
    )
    
    assert res is not None
    assert res["type"] == "decision"
    assert "PostgreSQL" in res["content"]
    
    mock_sdk_client.remember.assert_called_once()
    call_args = mock_sdk_client.remember.call_args[1]
    assert call_args["memory_type"] == "decision"
