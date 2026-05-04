

"""
Tests for CrewAI-Memanto integration.

This module tests the integration between CrewAI agents and Memanto's agentic memory system.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from crewai import Agent, Crew, Task

from src.integrations.crewai import (
    CrewAIMemoryConfig,
    CrewAIMemoryManager,
    CrewAIMemoryTool,
    add_memory_tools_to_agent,
    create_crewai_memory_tool,
    enhance_crew_with_memory
)

class TestCrewAIMemoryConfig(unittest.TestCase):
    """Test the CrewAIMemoryConfig class."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        config = CrewAIMemoryConfig(agent_id="test_agent")

        self.assertEqual(config.agent_id, "test_agent")
        self.assertEqual(config.scope_type, "agent")
        self.assertEqual(config.scope_id, "test_agent")
        self.assertEqual(config.actor_id, "test_agent")
        self.assertEqual(config.source, "agent")

    def test_custom_values(self):
        """Test that custom values are set correctly."""
        config = CrewAIMemoryConfig(
            agent_id="test_agent",
            scope_type="workspace",
            scope_id="workspace_123",
            actor_id="user_456",
            source="system"
        )

        self.assertEqual(config.agent_id, "test_agent")
        self.assertEqual(config.scope_type, "workspace")
        self.assertEqual(config.scope_id, "workspace_123")
        self.assertEqual(config.actor_id, "user_456")
        self.assertEqual(config.source, "system")

class TestCrewAIMemoryManager(unittest.TestCase):
    """Test the CrewAIMemoryManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = CrewAIMemoryConfig(agent_id="test_agent")
        self.moorcheh_api_key = "test_api_key"

        # Mock the Moorcheh client and services
        self.mock_client = MagicMock()
        self.mock_write_service = MagicMock()
        self.mock_read_service = MagicMock()

        # Patch the services
        with patch('src.integrations.crewai.MoorchehClient', return_value=self.mock_client), \
             patch('src.integrations.crewai.MemoryWriteService', return_value=self.mock_write_service), \
             patch('src.integrations.crewai.MemoryReadService', return_value=self.mock_read_service):

            self.manager = CrewAIMemoryManager(self.config, self.moorcheh_api_key)

    def test_init(self):
        """Test that the manager is initialized correctly."""
        self.assertEqual(self.manager.config, self.config)
        self.assertEqual(self.manager.moorcheh_api_key, self.moorcheh_api_key)
        self.assertEqual(self.manager.namespace, "memanto_agent_test_agent")

    def test_store_memory(self):
        """Test storing a memory."""
        # Set up mock return value
        mock_result = {
            "id": "memory_123",
            "namespace": "memanto_agent_test_agent",
            "status": "success",
            "action": "store",
            "reason": "Stored successfully",
            "confidence": 0.8,
            "memory_status": "active"
        }
        self.mock_write_service.store_memory.return_value = mock_result

        # Call the method
        result = self.manager.store_memory(
            memory_type="fact",
            title="Test Memory",
            content="This is a test memory",
            confidence=0.9,
            tags=["test", "integration"]
        )

        # Verify the result
        self.assertEqual(result, mock_result)
        self.mock_write_service.store_memory.assert_called_once()

    def test_retrieve_memory(self):
        """Test retrieving a memory."""
        # Set up mock return value
        mock_memory = {
            "id": "memory_123",
            "type": "fact",
            "title": "Test Memory",
            "content": "This is a test memory",
            "confidence": 0.9,
            "tags": ["test", "integration"]
        }
        self.mock_read_service.get_memory.return_value = mock_memory

        # Call the method
        result = self.manager.retrieve_memory("memory_123")

        # Verify the result
        self.assertEqual(result, mock_memory)
        self.mock_read_service.get_memory.assert_called_once_with(
            "memory_123", "memanto_agent_test_agent"
        )

    def test_search_memories(self):
        """Test searching for memories."""
        # Set up mock return value
        mock_results = [
            {
                "id": "memory_1",
                "type": "fact",
                "title": "Test Memory 1",
                "content": "This is a test memory 1",
                "confidence": 0.9
            },
            {
                "id": "memory_2",
                "type": "preference",
                "title": "Test Memory 2",
                "content": "This is a test memory 2",
                "confidence": 0.8
            }
        ]
        self.mock_read_service.search_memories.return_value = mock_results

        # Call the method
        result = self.manager.search_memories(
            query="test",
            limit=5,
            memory_types=["fact", "preference"],
            min_confidence=0.7
        )

        # Verify the result
        self.assertEqual(result, mock_results)
        self.mock_read_service.search_memories.assert_called_once_with(
            query="test",
            namespace="memanto_agent_test_agent",
            limit=5,
            filter_query="#memory_type:fact OR #memory_type:preference AND #confidence>=0.7"
        )

    def test_update_memory(self):
        """Test updating a memory."""
        # Set up mock return value
        mock_result = {
            "id": "memory_123",
            "namespace": "memanto_agent_test_agent",
            "status": "success",
            "action": "updated",
            "reason": "Memory updated successfully",
            "validation": "validated",
            "updated_fields": ["title", "content"]
        }
        self.mock_write_service.update_memory.return_value = mock_result

        # Call the method
        result = self.manager.update_memory(
            memory_id="memory_123",
            updates={"title": "Updated Title", "content": "Updated content"}
        )

        # Verify the result
        self.assertEqual(result, mock_result)
        self.mock_write_service.update_memory.assert_called_once_with(
            memory_id="memory_123",
            namespace="memanto_agent_test_agent",
            updates={"title": "Updated Title", "content": "Updated content"}
        )

    def test_delete_memory(self):
        """Test deleting a memory."""
        # Set up mock return value
        self.mock_write_service.delete_memory.return_value = True

        # Call the method
        result = self.manager.delete_memory("memory_123")

        # Verify the result
        self.assertTrue(result)
        self.mock_write_service.delete_memory.assert_called_once_with(
            "memory_123", "memanto_agent_test_agent"
        )

    def test_get_agent_context(self):
        """Test getting agent context."""
        # Set up mock return values
        self.mock_read_service.count_memories.return_value = 10
        mock_memories = [
            {
                "id": "memory_1",
                "title": "Recent Memory 1",
                "type": "fact",
                "updated_at": "2024-01-01T00:00:00"
            },
            {
                "id": "memory_2",
                "title": "Recent Memory 2",
                "type": "preference",
                "updated_at": "2024-01-02T00:00:00"
            }
        ]
        self.mock_read_service.search_memories.return_value = mock_memories

        # Call the method
        result = self.manager.get_agent_context()

        # Verify the result
        self.assertEqual(result["agent_id"], "test_agent")
        self.assertEqual(result["memory_count"], 10)
        self.assertEqual(len(result["recent_memories"]), 2)
        self.assertEqual(result["namespace"], "memanto_agent_test_agent")

class TestCrewAIMemoryTool(unittest.TestCase):
    """Test the CrewAIMemoryTool class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = CrewAIMemoryConfig(agent_id="test_agent")
        self.moorcheh_api_key = "test_api_key"

        # Create a mock memory manager
        self.mock_manager = MagicMock()
        self.tool = CrewAIMemoryTool(self.mock_manager)

    def test_store_memory(self):
        """Test the store_memory method."""
        # Set up mock return value
        mock_result = {"id": "memory_123"}
        self.mock_manager.store_memory.return_value = mock_result

        # Call the method
        result = self.tool.store_memory(
            memory_type="fact",
            title="Test Memory",
            content="This is a test memory",
            confidence=0.9,
            tags=["test"]
        )

        # Verify the result
        self.assertEqual(result, "Memory stored successfully with ID: memory_123")
        self.mock_manager.store_memory.assert_called_once_with(
            memory_type="fact",
            title="Test Memory",
            content="This is a test memory",
            confidence=0.9,
            tags=["test"],
            source_ref=None
        )

    def test_retrieve_memory(self):
        """Test the retrieve_memory method."""
        # Set up mock return value
        mock_memory = {
            "id": "memory_123",
            "title": "Test Memory",
            "content": "This is a test memory"
        }
        self.mock_manager.retrieve_memory.return_value = mock_memory

        # Call the method
        result = self.tool.retrieve_memory("memory_123")

        # Verify the result
        self.assertEqual(
            result,
            "Memory found:\nTitle: Test Memory\nContent: This is a test memory"
        )
        self.mock_manager.retrieve_memory.assert_called_once_with("memory_123")

    def test_retrieve_memory_not_found(self):
        """Test the retrieve_memory method when memory is not found."""
        # Set up mock return value
        self.mock_manager.retrieve_memory.return_value = None

        # Call the method
        result = self.tool.retrieve_memory("memory_123")

        # Verify the result
        self.assertEqual(result, "Memory memory_123 not found")
        self.mock_manager.retrieve_memory.assert_called_once_with("memory_123")

    def test_search_memories(self):
        """Test the search_memories method."""
        # Set up mock return value
        mock_results = [
            {"id": "1", "title": "Result 1", "type": "fact", "confidence": 0.9},
            {"id": "2", "title": "Result 2", "type": "preference", "confidence": 0.8}
        ]
        self.mock_manager.search_memories.return_value = mock_results

        # Call the method
        result = self.tool.search_memories(
            query="test",
            limit=5,
            memory_types=["fact", "preference"]
        )

        # Verify the result
        expected = (
            "Found 2 memories:\n\n"
            "1. Result 1 (fact)\n"
            "   ID: 1\n"
            "   Confidence: 0.9\n"
            "   Content: ...\n\n"
            "2. Result 2 (preference)\n"
            "   ID: 2\n"
            "   Confidence: 0.8\n"
            "   Content: ...\n\n"
        )
        self.assertEqual(result, expected)
        self.mock_manager.search_memories.assert_called_once_with(
            query="test",
            limit=5,
            memory_types=["fact", "preference"],
            tags=None
        )

    def test_search_memories_no_results(self):
        """Test the search_memories method when no results are found."""
        # Set up mock return value
        self.mock_manager.search_memories.return_value = []

        # Call the method
        result = self.tool.search_memories(query="test")

        # Verify the result
        self.assertEqual(result, "No memories found matching your query.")
        self.mock_manager.search_memories.assert_called_once_with(
            query="test",
            limit=10,
            memory_types=None,
            tags=None
        )

    def test_update_memory(self):
        """Test the update_memory method."""
        # Set up mock return value
        mock_result = {"id": "memory_123"}
        self.mock_manager.update_memory.return_value = mock_result

        # Call the method
        result = self.tool.update_memory(
            memory_id="memory_123",
            updates={"title": "Updated Title"}
        )

        # Verify the result
        self.assertEqual(result, "Memory memory_123 updated successfully")
        self.mock_manager.update_memory.assert_called_once_with(
            memory_id="memory_123",
            updates={"title": "Updated Title"}
        )

    def test_delete_memory(self):
        """Test the delete_memory method."""
        # Set up mock return value
        self.mock_manager.delete_memory.return_value = True

        # Call the method
        result = self.tool.delete_memory("memory_123")

        # Verify the result
        self.assertEqual(result, "Memory memory_123 deleted successfully")
        self.mock_manager.delete_memory.assert_called_once_with("memory_123")

    def test_get_agent_context(self):
        """Test the get_agent_context method."""
        # Set up mock return value
        mock_context = {
            "agent_id": "test_agent",
            "memory_count": 10,
            "recent_memories": [
                {"id": "1", "title": "Recent 1", "type": "fact", "updated_at": "2024-01-01"},
                {"id": "2", "title": "Recent 2", "type": "preference", "updated_at": "2024-01-02"}
            ],
            "namespace": "memanto_agent_test_agent"
        }
        self.mock_manager.get_agent_context.return_value = mock_context

        # Call the method
        result = self.tool.get_agent_context()

        # Verify the result
        expected = (
            "Agent Context for test_agent:\n"
            "- Total memories: 10\n"
            "- Namespace: memanto_agent_test_agent\n\n"
            "Recent Memories:\n"
            "1. Recent 1 (fact)\n"
            "   ID: 1\n"
            "   Updated: 2024-01-01\n\n"
            "2. Recent 2 (preference)\n"
            "   ID: 2\n"
            "   Updated: 2024-01-02\n\n"
        )
        self.assertEqual(result, expected)
        self.mock_manager.get_agent_context.assert_called_once()

class TestIntegrationFunctions(unittest.TestCase):
    """Test the integration functions."""

    def test_create_crewai_memory_tool(self):
        """Test the create_crewai_memory_tool function."""
        # Mock the memory manager
        mock_manager = MagicMock()

        # Call the function
        tool = create_crewai_memory_tool(
            agent_id="test_agent",
            moorcheh_api_key="test_api_key"
        )

        # Verify the tool was created with the mock manager
        self.assertIsInstance(tool, CrewAIMemoryTool)
        self.assertEqual(tool.memory_manager, mock_manager)

    def test_add_memory_tools_to_agent(self):
        """Test the add_memory_tools_to_agent function."""
        # Create a mock agent
        mock_agent = MagicMock()
        mock_agent.role = "test_agent"

        # Call the function
        result = add_memory_tools_to_agent(
            agent=mock_agent,
            moorcheh_api_key="test_api_key"
        )

        # Verify the agent was updated
        self.assertEqual(result, mock_agent)
        self.assertEqual(len(mock_agent.tools), 6)  # 6 memory tools

    def test_enhance_crew_with_memory(self):
        """Test the enhance_crew_with_memory function."""
        # Create a mock crew
        mock_crew = MagicMock()
        mock_crew.agents = [MagicMock(role="agent1"), MagicMock(role="agent2")]

        # Call the function
        result = enhance_crew_with_memory(
            crew=mock_crew,
            moorcheh_api_key="test_api_key"
        )

        # Verify the crew was updated
        self.assertEqual(result, mock_crew)
        self.assertEqual(len(mock_crew.agents), 2)

if __name__ == "__main__":
    unittest.main()
