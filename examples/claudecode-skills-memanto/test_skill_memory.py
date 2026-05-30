"""Tests for Memanto + mattpocock/skills integration."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from memory_backend import LocalBackend
from skill_memory import (
    extract_signals,
    extract_from_file_references,
    extract_skill_name,
    format_memory_context,
    post_hook,
    pre_hook,
)


class TestLocalBackend(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.backend = LocalBackend(data_dir=self.tmpdir)

    def test_store_returns_id(self):
        mid = self.backend.store({"type": "decision", "content": "Use PostgreSQL for write model"})
        self.assertIsInstance(mid, str)
        self.assertTrue(len(mid) > 0)

    def test_store_and_recall(self):
        self.backend.store({"type": "decision", "content": "Use event sourcing for orders"})
        self.backend.store({"type": "preference", "content": "Prefer composition over inheritance"})
        results = self.backend.recall("event sourcing")
        self.assertTrue(len(results) >= 1)

    def test_recall_by_type(self):
        self.backend.store({"type": "decision", "content": "Decided to use microservices"})
        self.backend.store({"type": "preference", "content": "Prefer tabs over spaces"})
        decisions = self.backend.recall_by_type("decision")
        self.assertTrue(all(d["type"] == "decision" for d in decisions))

    def test_recall_empty(self):
        results = self.backend.recall("nonexistent query xyz123")
        self.assertEqual(results, [])

    def test_superseded_excluded(self):
        self.backend.store({"type": "fact", "content": "Old fact", "status": "superseded"})
        results = self.backend.recall("Old fact")
        self.assertEqual(results, [])

    def test_multiple_stores_persist(self):
        for i in range(5):
            self.backend.store({"type": "fact", "content": f"Fact number {i}"})
        results = self.backend.recall("Fact", limit=10)
        self.assertEqual(len(results), 5)


class TestSignalExtraction(unittest.TestCase):
    def test_extract_instruction(self):
        signals = extract_signals("You must always use TypeScript strict mode")
        self.assertTrue(len(signals) >= 1)
        self.assertEqual(signals[0]["type"], "instruction")

    def test_extract_decision(self):
        signals = extract_signals("We decided to use PostgreSQL for the write model")
        self.assertTrue(len(signals) >= 1)
        self.assertEqual(signals[0]["type"], "decision")

    def test_extract_preference(self):
        signals = extract_signals("I prefer composition over inheritance in this codebase")
        self.assertTrue(len(signals) >= 1)
        self.assertEqual(signals[0]["type"], "preference")

    def test_extract_context(self):
        signals = extract_signals("TODO: Refactor the authentication module")
        self.assertTrue(len(signals) >= 1)
        self.assertEqual(signals[0]["type"], "context")

    def test_skill_name_in_tags(self):
        signals = extract_signals("Must use TDD approach", skill_name="tdd")
        self.assertIn("tdd", signals[0].get("tags", []))

    def test_no_signals_from_plain_text(self):
        signals = extract_signals("The weather is nice today.")
        self.assertEqual(len(signals), 0)

    def test_deduplication(self):
        text = "must always use strict mode. must always use strict mode."
        signals = extract_signals(text)
        self.assertEqual(len(signals), 1)


class TestFileReferenceExtraction(unittest.TestCase):
    def test_extract_python_files(self):
        signals = extract_from_file_references("Modified src/auth/login.py and src/models/user.py")
        self.assertTrue(len(signals) >= 1)
        self.assertIn("login.py", signals[0]["content"])

    def test_extract_typescript_files(self):
        signals = extract_from_file_references("Created src/components/Button.tsx")
        self.assertTrue(len(signals) >= 1)


class TestSkillNameDetection(unittest.TestCase):
    def test_slash_command(self):
        self.assertEqual(extract_skill_name("/grill-with-docs my plan"), "grill-with-docs")

    def test_no_match(self):
        self.assertIsNone(extract_skill_name("just a regular prompt"))

    def test_env_var_override(self):
        os.environ["CLAUDE_SKILL_NAME"] = "tdd"
        try:
            self.assertEqual(extract_skill_name("some prompt"), "tdd")
        finally:
            del os.environ["CLAUDE_SKILL_NAME"]


class TestFormatMemoryContext(unittest.TestCase):
    def test_format_empty(self):
        result = format_memory_context([])
        self.assertEqual(result, "")

    def test_format_with_memories(self):
        memories = [
            {"type": "decision", "content": "Use event sourcing", "confidence": 0.85, "tags": ["architecture"]},
        ]
        result = format_memory_context(memories)
        self.assertIn("DECISION", result)
        self.assertIn("Use event sourcing", result)
        self.assertIn("85%", result)

    def test_truncation(self):
        memories = [
            {"type": "fact", "content": "x" * 300, "confidence": 0.8, "tags": []},
        ]
        result = format_memory_context(memories, max_chars=100)
        self.assertTrue(len(result) <= 100)


class TestPrePostHooks(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Set env var BEFORE creating backend — works because _get_local_dir() is lazy
        os.environ["MEMANTO_SKILLS_DATA"] = self.tmpdir

    def tearDown(self):
        os.environ.pop("MEMANTO_SKILLS_DATA", None)

    def test_pre_hook_returns_context(self):
        backend = LocalBackend(data_dir=self.tmpdir)
        backend.store({"type": "decision", "content": "Use PostgreSQL for write model", "tags": ["architecture"]})
        context = pre_hook("What database should we use?")
        self.assertIsInstance(context, str)

    def test_post_hook_stores_signals(self):
        ids = post_hook(
            "Design the order system",
            "We decided to use event sourcing for orders. Must always use domain events.",
            "grill-with-docs",
        )
        self.assertTrue(len(ids) >= 1)

    def test_full_lifecycle(self):
        context1 = pre_hook("/grill-with-docs Design the order system", "grill-with-docs")
        self.assertIsInstance(context1, str)
        skill_output = "We decided to use event sourcing for the order module. Must always use aggregate roots."
        ids = post_hook("/grill-with-docs Design the order system", skill_output, "grill-with-docs")
        self.assertTrue(len(ids) >= 1)
        context2 = pre_hook("/tdd Implement the Order aggregate", "tdd")
        self.assertIsInstance(context2, str)


if __name__ == "__main__":
    unittest.main()
