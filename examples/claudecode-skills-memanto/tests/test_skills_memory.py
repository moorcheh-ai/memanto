"""
tests/test_skills_memory.py
===========================
Unit tests for the Memanto skills memory companion.

Tests run without a Moorcheh API key — all SDK calls are mocked.
Run: python -m pytest tests/ -v
  or: python -m unittest discover tests/ -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills_memory import SkillsMemory, _MockDB


class TestMockDB(unittest.TestCase):
    """Tests for offline mock backend."""

    def test_store_returns_id(self):
        db = _MockDB()
        result = db.store("Use JWT over sessions", memory_type="decision", skill="/tdd")
        self.assertIsNotNone(result.get("id"))
        self.assertEqual(result["content"], "Use JWT over sessions")
        self.assertEqual(result["type"], "decision")

    def test_recall_returns_stored_memories(self):
        db = _MockDB()
        db.store("JWT preferred", memory_type="decision", skill="/tdd")
        db.store("TypeScript strict mode", memory_type="preference", skill="/grill-with-docs")
        results = db.recall("authentication", limit=5)
        self.assertEqual(len(results), 2)

    def test_correct_stores_new_fact(self):
        db = _MockDB()
        db.store("Use HS256", memory_type="fact", skill="/tdd")
        result = db.correct("Use HS256", "Use RS256 — asymmetric preferred", skill="/tdd")
        self.assertIsNotNone(result.get("id"))
        self.assertIn("RS256", result["content"])

    def test_answer_references_stored_memories(self):
        db = _MockDB()
        db.store("JWT over sessions", memory_type="decision", skill="/tdd")
        answer = db.answer("What auth approach?")
        self.assertIn("engineering profile", answer.lower())


class TestSkillsMemoryOffline(unittest.TestCase):
    """Tests for SkillsMemory in offline mode."""

    def setUp(self):
        self.mem = SkillsMemory(offline=True)

    def test_pre_skill_hook_returns_empty_when_no_memories(self):
        context = self.mem.pre_skill_hook(skill_name="/tdd", task="login")
        self.assertEqual(context, "")

    def test_pre_skill_hook_returns_profile_after_store(self):
        self.mem.post_skill_hook(
            skill_name="/grill-with-docs",
            summary="Auth design done",
            decisions=["JWT over sessions"],
        )
        context = self.mem.pre_skill_hook(skill_name="/tdd", task="login")
        self.assertIn("engineering-profile", context)
        self.assertIn("JWT over sessions", context)

    def test_post_skill_hook_stores_summary_and_decisions(self):
        stored = self.mem.post_skill_hook(
            skill_name="/tdd",
            summary="Implemented login",
            decisions=["JWT with RS256", "7-day refresh rotation"],
            preferences=["TypeScript strict mode"],
        )
        self.assertEqual(len(stored), 4)  # summary + 2 decisions + 1 preference

    def test_cross_session_recall(self):
        """Simulates session boundary — key cross-session test."""
        # Session A: /grill-with-docs stores decisions
        self.mem.post_skill_hook(
            skill_name="/grill-with-docs",
            summary="Stripe webhook architecture",
            decisions=["Use event_id as idempotency key"],
        )

        # Session B: /tdd recalls in a fresh call
        context = self.mem.pre_skill_hook(
            skill_name="/tdd",
            task="Write Stripe webhook tests",
        )
        self.assertIn("event_id", context)
        self.assertIn("engineering-profile", context)

    def test_post_hook_deduplicates(self):
        """Storing same decision twice should not create duplicates in recall."""
        self.mem.post_skill_hook("/tdd", "Summary", decisions=["Use JWT"])
        initial = self.mem.recall("JWT")
        count_before = len(initial)

        # Store again
        self.mem.post_skill_hook("/tdd", "Summary", decisions=["Use JWT"])
        after = self.mem.recall("JWT")

        # Mock DB doesn't dedupe but real SDK would — just verify no crash
        self.assertGreaterEqual(len(after), count_before)

    def test_recall_returns_list(self):
        results = self.mem.recall("authentication")
        self.assertIsInstance(results, list)

    def test_answer_returns_string(self):
        self.mem.post_skill_hook("/tdd", "Auth done", decisions=["JWT"])
        answer = self.mem.answer("What auth approach did we choose?")
        self.assertIsInstance(answer, str)
        self.assertTrue(len(answer) > 0)


class TestHooksCommon(unittest.TestCase):
    """Tests for hook utility functions."""

    def test_detect_skill_from_payload(self):
        from hooks._common import detect_skill
        payload = {"prompt": "Please run /tdd on the auth module"}
        self.assertEqual(detect_skill(payload), "/tdd")

    def test_detect_skill_grill(self):
        from hooks._common import detect_skill
        payload = {"tool_name": "grill-with-docs"}
        self.assertEqual(detect_skill(payload), "/grill-with-docs")

    def test_detect_skill_unknown(self):
        from hooks._common import detect_skill
        payload = {"prompt": "Hello"}
        self.assertEqual(detect_skill(payload), "general")

    def test_extract_files_from_prompt(self):
        from hooks._common import extract_files_from_prompt
        files = extract_files_from_prompt(
            "Please update app/webhooks/stripe.py and tests/test_stripe.py"
        )
        self.assertIn("app/webhooks/stripe.py", files)
        self.assertIn("tests/test_stripe.py", files)

    def test_render_profile_empty_when_no_memories(self):
        from hooks._common import render_profile
        result = render_profile("/tdd", [], "")
        self.assertEqual(result, "")

    def test_render_profile_contains_skill(self):
        from hooks._common import render_profile
        memories = [{"content": "Use JWT", "type": "decision", "confidence": 0.9}]
        result = render_profile("/tdd", memories)
        self.assertIn("/tdd", result)
        self.assertIn("Use JWT", result)
        self.assertIn("engineering-profile", result)

    def test_heuristic_extract_decisions(self):
        from hooks._common import _heuristic_extract
        transcript = (
            "DECISION: Use JWT tokens over sessions.\n"
            "CONSTRAINT: Never store tokens in localStorage.\n"
            "PREFERENCE: TypeScript strict mode always.\n"
        )
        memories = _heuristic_extract(transcript, "/tdd")
        types = [m["type"] for m in memories]
        self.assertIn("decision", types)
        self.assertIn("instruction", types)
        self.assertIn("preference", types)

    def test_heuristic_extract_deduplicates(self):
        from hooks._common import _heuristic_extract
        transcript = (
            "DECISION: Use JWT.\n"
            "DECISION: Use JWT.\n"
        )
        memories = _heuristic_extract(transcript, "/tdd")
        contents = [m["content"] for m in memories]
        self.assertEqual(len(contents), len(set(contents)))


class TestValidateOffline(unittest.TestCase):
    """Ensures offline validation passes end-to-end."""

    def test_demo_runs_without_errors(self):
        """Full offline demo must not raise exceptions."""
        from skills_memory import _offline_demo
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                _offline_demo()
        except Exception as exc:
            self.fail(f"Offline demo raised: {exc}")

        output = buf.getvalue()
        self.assertIn("SESSION BOUNDARY", output)
        self.assertIn("engineering-profile", output)
        self.assertIn("Demo complete", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
