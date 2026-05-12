"""
Unit tests for the LangGraph + Memanto integration.

These tests validate:
  - Tool schemas (Pydantic v2 / Zod v4 compatible)
  - Graph construction and compilation
  - AgentState schema
  - x402 payment config structure
  - Health endpoint
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestSchemas(unittest.TestCase):
    """Validate Pydantic v2 schemas (Zod v4 / x402 structured output compatible)."""

    def test_remember_input_valid(self):
        from memanto_tools import RememberInput
        obj = RememberInput(content="Alice prefers concise answers", memory_type="semantic")
        self.assertEqual(obj.content, "Alice prefers concise answers")
        self.assertEqual(obj.memory_type, "semantic")

    def test_remember_input_defaults(self):
        from memanto_tools import RememberInput
        obj = RememberInput(content="test")
        self.assertEqual(obj.memory_type, "semantic")
        self.assertEqual(obj.tags, "")

    def test_remember_input_validation_empty(self):
        from memanto_tools import RememberInput
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RememberInput(content="")  # min_length=1

    def test_remember_input_validation_whitespace(self):
        from memanto_tools import RememberInput
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RememberInput(content="   ")  # whitespace only

    def test_recall_input_valid(self):
        from memanto_tools import RecallInput
        obj = RecallInput(query="What does Alice prefer?", top_k=3)
        self.assertEqual(obj.query, "What does Alice prefer?")
        self.assertEqual(obj.top_k, 3)

    def test_recall_input_defaults(self):
        from memanto_tools import RecallInput
        obj = RecallInput(query="test")
        self.assertEqual(obj.top_k, 5)  # default

    def test_answer_input_valid(self):
        from memanto_tools import AnswerInput
        obj = AnswerInput(question="Summarise all known preferences")
        self.assertEqual(obj.question, "Summarise all known preferences")

    def test_answer_input_validation(self):
        from memanto_tools import AnswerInput
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            AnswerInput()  # question is required


class TestGraphConstruction(unittest.TestCase):
    """Validate the LangGraph StateGraph builds without errors."""

    def test_build_graph(self):
        """Graph should compile successfully."""
        from agent import build_graph
        graph = build_graph()
        self.assertIsNotNone(graph)

    def test_tools_list(self):
        """TOOLS should contain exactly 3 tools."""
        from agent import TOOLS
        self.assertEqual(len(TOOLS), 3)
        tool_names = {t.name for t in TOOLS}
        self.assertEqual(tool_names, {"memanto_remember", "memanto_recall", "memanto_answer"})


class TestX402Config(unittest.TestCase):
    """Validate x402 payment configuration structure."""

    def test_config_fields(self):
        from agent import X402_CONFIG
        self.assertEqual(X402_CONFIG["payTo"], "66dG5r5TD37ahhrsAMKUroxML9Cqto5jRduifiMgQQ3G")
        self.assertEqual(X402_CONFIG["network"], "solana")
        self.assertIn("amount", X402_CONFIG)

    def test_payto_is_valid_solana_address(self):
        from agent import X402_CONFIG
        payto = X402_CONFIG["payTo"]
        # Solana addresses are base58, 32-44 chars
        self.assertTrue(len(payto) >= 32)
        self.assertTrue(len(payto) <= 44)

    def test_x402_wallet_structure(self):
        from agent import X402_WALLET
        self.assertEqual(X402_WALLET["type"], "x402")
        self.assertEqual(X402_WALLET["version"], 1)
        self.assertIn("config", X402_WALLET)


class TestAgentState(unittest.TestCase):
    """Validate the AgentState TypedDict."""

    def test_state_has_messages(self):
        from agent import AgentState
        annotations = AgentState.__annotations__
        self.assertIn("messages", annotations)
        self.assertIn("summary", annotations)


class TestHealthEndpoint(unittest.TestCase):
    """Validate the health check endpoint."""

    def test_health_returns_dict(self):
        from agent import health
        result = health()
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["agent"], "langgraph-memanto")
        self.assertEqual(len(result["tools"]), 3)
        self.assertIn("x402", result)


if __name__ == "__main__":
    unittest.main()