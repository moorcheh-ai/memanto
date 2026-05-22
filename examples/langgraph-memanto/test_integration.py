"""
Unit tests for the LangGraph + Memanto integration.

These tests use mocks for the Moorcheh client so they can run
without API keys.
"""

import pytest
import json
from unittest.mock import MagicMock, patch

from memanto_tool import MemantoTool


class TestMemantoToolUnit:
    """Unit tests for MemantoTool without requiring API access."""

    @patch("memanto_tool.MoorchehClient")
    def test_remember_validates_memory_type(self, MockClient):
        """remember() should reject invalid memory types."""
        mock_client = MockClient.return_value
        mock_client.namespaces.get.return_value = True

        tool = MemantoTool(agent_id="test", scope_id="test", moorcheh_api_key="fake")

        with pytest.raises(ValueError, match="Invalid memory_type"):
            tool.remember("test content", memory_type="invalid_type")

    @pytest.mark.parametrize("memory_type", [
        "fact", "preference", "goal", "decision", "artifact",
        "learning", "event", "instruction", "relationship",
        "context", "observation", "commitment", "error",
    ])
    @patch("memanto_tool.MoorchehClient")
    def test_remember_accepts_all_valid_types(self, MockClient, memory_type):
        """remember() should accept all 13 Memanto memory types."""
        mock_client = MockClient.return_value
        mock_client.namespaces.get.return_value = True
        mock_write_service = MagicMock()
        mock_write_service.store_memory.return_value = {"id": "mem-123"}

        tool = MemantoTool(agent_id="test", scope_id="test", moorcheh_api_key="fake")
        tool.write_service = mock_write_service

        result = tool.remember("test content", memory_type=memory_type)
        assert result["action"] == "remembered"
        assert result["type"] == memory_type

    @patch("memanto_tool.MoorchehClient")
    def test_remember_clamps_confidence(self, MockClient):
        """remember() should clamp confidence to [0.0, 1.0]."""
        mock_client = MockClient.return_value
        mock_client.namespaces.get.return_value = True
        mock_write_service = MagicMock()
        mock_write_service.store_memory.return_value = {"id": "mem-123"}

        tool = MemantoTool(agent_id="test", scope_id="test", moorcheh_api_key="fake")
        tool.write_service = mock_write_service

        result = tool.remember("test", confidence=1.5)
        assert result["confidence"] == 1.0

        result = tool.remember("test", confidence=-0.5)
        assert result["confidence"] == 0.0

    @patch("memanto_tool.MoorchehClient")
    def test_remember_auto_generates_title(self, MockClient):
        """remember() should auto-generate title from content if not provided."""
        mock_client = MockClient.return_value
        mock_client.namespaces.get.return_value = True
        mock_write_service = MagicMock()
        mock_write_service.store_memory.return_value = {"id": "mem-123"}

        tool = MemantoTool(agent_id="test", scope_id="test", moorcheh_api_key="fake")
        tool.write_service = mock_write_service

        result = tool.remember("Short content")
        assert result["title"] == "Short content"

        long = "x" * 100
        result = tool.remember(long)
        assert result["title"].endswith("...")

    @patch("memanto_tool.MoorchehClient")
    def test_recall_returns_list(self, MockClient):
        """recall() should return a list of memory dicts."""
        mock_client = MockClient.return_value
        mock_client.namespaces.get.return_value = True
        mock_read_service = MagicMock()
        mock_read_service.search_memories.return_value = {
            "memories": [
                {
                    "id": "mem-1",
                    "memory_type": "fact",
                    "title": "Test fact",
                    "content": "This is a test fact",
                    "confidence": 0.9,
                    "created_at": "2026-05-22T00:00:00",
                },
            ]
        }

        tool = MemantoTool(agent_id="test", scope_id="test", moorcheh_api_key="fake")
        tool.read_service = mock_read_service

        results = tool.recall("test query")
        assert len(results) == 1
        assert results[0]["type"] == "fact"
        assert results[0]["confidence"] == 0.9

    @patch("memanto_tool.MoorchehClient")
    def test_recall_empty(self, MockClient):
        """recall() should return empty list when no memories found."""
        mock_client = MockClient.return_value
        mock_client.namespaces.get.return_value = True
        mock_read_service = MagicMock()
        mock_read_service.search_memories.return_value = {"memories": []}

        tool = MemantoTool(agent_id="test", scope_id="test", moorcheh_api_key="fake")
        tool.read_service = mock_read_service

        results = tool.recall("nonexistent topic")
        assert results == []

    @patch("memanto_tool.MoorchehClient")
    def test_answer_uses_client(self, MockClient):
        """answer() should use the Moorcheh client's answer endpoint."""
        mock_client = MockClient.return_value
        mock_client.namespaces.get.return_value = True
        mock_client.answer.return_value = {
            "answer": "Surface codes are the leading approach to QECC",
            "sources": [{"id": "mem-1"}],
            "confidence": 0.92,
        }

        tool = MemantoTool(agent_id="test", scope_id="test", moorcheh_api_key="fake")
        tool.client = mock_client

        result = tool.answer("What is the best QECC approach?")
        assert "Surface codes" in result["answer"]
        assert result["confidence"] == 0.92

    @patch("memanto_tool.MoorchehClient")
    def test_answer_fallback_on_error(self, MockClient):
        """answer() should fall back to recall when client.answer fails."""
        mock_client = MockClient.return_value
        mock_client.namespaces.get.return_value = True
        mock_client.answer.side_effect = Exception("API error")

        mock_read_service = MagicMock()
        mock_read_service.search_memories.return_value = {
            "memories": [
                {
                    "id": "mem-1",
                    "memory_type": "fact",
                    "content": "Surface codes are best",
                    "confidence": 0.9,
                    "created_at": "2026-05-22",
                },
            ]
        }

        tool = MemantoTool(agent_id="test", scope_id="test", moorcheh_api_key="fake")
        tool.client = mock_client
        tool.read_service = mock_read_service

        result = tool.answer("What is the best QECC approach?")
        assert "Surface codes" in result["answer"]
        assert result["confidence"] == 0.9

    @patch("memanto_tool.MoorchehClient")
    def test_answer_no_memories(self, MockClient):
        """answer() should report no memories when none exist."""
        mock_client = MockClient.return_value
        mock_client.namespaces.get.return_value = True
        mock_client.answer.side_effect = Exception("API error")

        mock_read_service = MagicMock()
        mock_read_service.search_memories.return_value = {"memories": []}

        tool = MemantoTool(agent_id="test", scope_id="test", moorcheh_api_key="fake")
        tool.client = mock_client
        tool.read_service = mock_read_service

        result = tool.answer("unknown topic")
        assert "No relevant memories" in result["answer"]
        assert result["confidence"] == 0.0


class TestNoteClassification:
    """Test the _classify_note helper function."""

    def test_decision(self):
        from agent import _classify_note
        assert _classify_note("We decided to use Python 3.12") == "decision"

    def test_goal(self):
        from agent import _classify_note
        assert _classify_note("The goal is to achieve 99% uptime") == "goal"

    def test_instruction(self):
        from agent import _classify_note
        assert _classify_note("You must always validate inputs") == "instruction"

    def test_observation(self):
        from agent import _classify_note
        assert _classify_note("We observed that latency decreased by 50%") == "observation"

    def test_plan(self):
        from agent import _classify_note
        assert _classify_note("The plan involves three phases of deployment") == "goal"

    def test_default_fact(self):
        from agent import _classify_note
        assert _classify_note("Python was created in 1991") == "fact"


import os

class TestMemantoToolNoKey:
    """Test that MemantoTool fails gracefully without an API key."""

    def test_no_api_key_raises(self):
        """Should raise ValueError if no API key is provided."""
        with patch.dict("os.environ", {}, clear=True):
            # Ensure MOORCHEH_API_KEY is not set
            os.environ.pop("MOORCHEH_API_KEY", None)
            with pytest.raises(ValueError, match="MOORCHEH_API_KEY"):
                MemantoTool(agent_id="test", scope_id="test", moorcheh_api_key="")
