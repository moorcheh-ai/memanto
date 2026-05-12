from __future__ import annotations
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestSchemas(unittest.TestCase):
    def test_remember_valid(self):
        from memanto_tools import RememberInput
        o = RememberInput(content="Sofia is a ML engineer", memory_type="semantic")
        self.assertEqual(o.memory_type, "semantic")

    def test_remember_empty_fails(self):
        from memanto_tools import RememberInput
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RememberInput(content="")

    def test_recall_defaults(self):
        from memanto_tools import RecallInput
        o = RecallInput(query="test")
        self.assertEqual(o.top_k, 5)

    def test_answer_required(self):
        from memanto_tools import AnswerInput
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            AnswerInput()

class TestGraph(unittest.TestCase):
    def test_build(self):
        from agents import build_graph
        g = build_graph()
        self.assertIsNotNone(g)

    def test_tools_count(self):
        from memanto_tools import MEMORY_TOOLS
        self.assertEqual(len(MEMORY_TOOLS), 3)
        names = {t.name for t in MEMORY_TOOLS}
        self.assertEqual(names, {"memanto_remember", "memanto_recall", "memanto_answer"})

class TestX402(unittest.TestCase):
    def test_config(self):
        from agents import X402_CONFIG
        self.assertIn("payTo", X402_CONFIG)
        self.assertEqual(X402_CONFIG["network"], "solana")
        self.assertGreaterEqual(len(X402_CONFIG["payTo"]), 32)

class TestHealth(unittest.TestCase):
    def test_health(self):
        from agents import health
        h = health()
        self.assertEqual(h["status"], "healthy")
        self.assertIn("subgraphs", h["features"])
        self.assertIn("human-in-the-loop", h["features"])
        self.assertEqual(len(h["tools"]), 3)

class TestState(unittest.TestCase):
    def test_state_keys(self):
        from agents import AgentState
        keys = AgentState.__annotations__
        for k in ["messages", "current_agent", "memory_approved", "summary", "iteration"]:
            self.assertIn(k, keys)

if __name__ == "__main__":
    unittest.main(verbosity=2)
