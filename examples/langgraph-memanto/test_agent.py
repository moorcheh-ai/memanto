"""
Tests for LangGraph + Memanto integration
"""

import pytest
from agent import CustomerSupportAgent
import os


@pytest.fixture
def agent():
    """Create test agent"""
    return CustomerSupportAgent(user_id="test-user-pytest")


def test_agent_initialization(agent):
    """Test agent initializes correctly"""
    assert agent.user_id == "test-user-pytest"
    assert agent.memanto is not None
    assert agent.graph is not None


def test_cross_session_memory(agent):
    """Test that memories persist across agent instances"""
    # Session 1: Store preference
    response1 = agent.chat("I prefer dark mode")
    assert response1 is not None
    
    # Session 2: New agent instance, same user
    agent2 = CustomerSupportAgent(user_id="test-user-pytest")
    response2 = agent2.chat("What theme do I prefer?")
    
    # Should recall dark mode preference
    assert "dark" in response2.lower() or "dark mode" in response2.lower()


def test_memory_storage():
    """Test that facts are stored in Memanto"""
    agent = CustomerSupportAgent(user_id="test-storage-user")
    
    # Store a clear preference
    agent.chat("I want email notifications disabled")
    
    # Query Memanto directly
    memories = agent.memanto.recall("email notifications", limit=5)
    
    # Should find the stored preference
    assert len(memories) > 0
    assert any("email" in m["content"].lower() for m in memories)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
