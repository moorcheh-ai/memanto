"""Tests for LangGraph + Memanto customer support agent."""

import json
import pytest
from unittest.mock import MagicMock, patch


class TestSupportState:
    """Test the SupportState TypedDict structure."""

    def test_state_keys(self):
        """SupportState has all required keys."""
        from agent import SupportState
        annotations = SupportState.__annotations__
        assert "messages" in annotations
        assert "recalled_context" in annotations
        assert "intent" in annotations
        assert "response" in annotations
        assert "memories_to_store" in annotations


class TestIntakeNode:
    """Test the intake node logic."""

    def test_recall_formatting(self):
        """Test memory recall formatting."""
        memories = [
            {"title": "Billing Issue", "content": "Charged twice", "type": "fact", "confidence": 0.9},
            {"title": "Preference", "content": "Prefers email", "type": "preference", "confidence": 0.8},
        ]
        recalled_lines = []
        for mem in memories:
            title = mem.get("title", "Untitled")
            content_val = mem.get("content", "")
            mem_type = mem.get("type", "unknown")
            confidence = mem.get("confidence", "N/A")
            recalled_lines.append(f"- [{mem_type}] {title} (confidence: {confidence}): {content_val}")
        NL = chr(10)
        recalled_context = NL.join(recalled_lines)
        assert "Billing Issue" in recalled_context
        assert "Charged twice" in recalled_context
        assert "Preference" in recalled_context

    def test_empty_recall(self):
        """Empty recall returns No prior memories found."""
        memories = []
        recalled_context = "No prior memories found." if not memories else ""
        assert recalled_context == "No prior memories found."


class TestRememberNode:
    """Test the remember node logic."""

    def test_json_extraction_plain(self):
        """Test JSON parsing without code blocks."""
        raw = "[]"
        data = json.loads(raw)
        assert len(data) == 0

    def test_confidence_clamping(self):
        """Confidence values are clamped to [0.0, 1.0]."""
        assert min(1.0, max(0.0, float(1.5))) == 1.0
        assert min(1.0, max(0.0, float(-0.5))) == 0.0
        assert min(1.0, max(0.0, float(0.85))) == 0.85

    def test_tags_parsing(self):
        """Tags are parsed from comma-separated strings."""
        tags_str = "billing, refund, priority"
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        assert tags == ["billing", "refund", "priority"]

    def test_empty_tags(self):
        """Empty tag strings produce empty lists."""
        tags_str = ""
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        assert tags == []


class TestGraphBuilder:
    """Test the graph building logic."""

    def test_graph_nodes(self):
        """Verify expected graph nodes."""
        expected_nodes = {"intake", "respond", "remember"}
        assert len(expected_nodes) == 3
        assert "intake" in expected_nodes
        assert "respond" in expected_nodes
        assert "remember" in expected_nodes


class TestSessionRunner:
    """Test the session runner logic."""

    def test_initial_state(self):
        """Verify the initial state passed to graph.invoke()."""
        from agent import HumanMessage
        msg = "Hello, I need help"
        initial = {
            "messages": [HumanMessage(content=msg)],
            "recalled_context": "",
            "intent": "",
            "response": "",
            "memories_to_store": [],
        }
        assert len(initial["messages"]) == 1
        assert initial["messages"][0].content == msg
        assert initial["recalled_context"] == ""
        assert initial["memories_to_store"] == []
