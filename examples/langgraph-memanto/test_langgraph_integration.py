"""Tests for Memanto + LangGraph integration."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from memory_backend import LocalBackend
from memory_nodes import (
    extract_from_file_references,
    extract_signals,
    format_memory_context,
    recall_memories,
    store_memories,
)
from graph_builder import build_memory_graph, invoke_graph, placeholder_agent
from hooks import pre_execution_hook, post_execution_hook, wrap_execution


# ---------------------------------------------------------------------------
# LocalBackend Tests
# ---------------------------------------------------------------------------

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

    def test_tag_filtering(self):
        self.backend.store({"type": "decision", "content": "Use React", "tags": ["frontend"]})
        self.backend.store({"type": "decision", "content": "Use PostgreSQL", "tags": ["backend"]})
        results = self.backend.recall("Use", limit=5, tags=["frontend"])
        self.assertTrue(any("React" in r["content"] for r in results))


# ---------------------------------------------------------------------------
# Signal Extraction Tests
# ---------------------------------------------------------------------------

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

    def test_stage_name_in_tags(self):
        signals = extract_signals("Must use TDD approach", stage="testing")
        self.assertIn("testing", signals[0].get("tags", []))

    def test_no_signals_from_plain_text(self):
        signals = extract_signals("The weather is nice today.")
        self.assertEqual(len(signals), 0)

    def test_deduplication(self):
        text = "must always use strict mode. must always use strict mode."
        signals = extract_signals(text)
        self.assertEqual(len(signals), 1)


# ---------------------------------------------------------------------------
# File Reference Extraction Tests
# ---------------------------------------------------------------------------

class TestFileReferenceExtraction(unittest.TestCase):
    def test_extract_python_files(self):
        signals = extract_from_file_references("Modified src/auth/login.py and src/models/user.py")
        self.assertTrue(len(signals) >= 1)
        self.assertIn("login.py", signals[0]["content"])

    def test_extract_typescript_files(self):
        signals = extract_from_file_references("Created src/components/Button.tsx")
        self.assertTrue(len(signals) >= 1)

    def test_stage_tag_in_file_refs(self):
        signals = extract_from_file_references("Created src/auth.py", stage="implementation")
        self.assertIn("implementation", signals[0].get("tags", []))


# ---------------------------------------------------------------------------
# Memory Context Formatting Tests
# ---------------------------------------------------------------------------

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

    def test_includes_tags(self):
        memories = [
            {"type": "preference", "content": "Use strict mode", "confidence": 0.9, "tags": ["typescript"]},
        ]
        result = format_memory_context(memories)
        self.assertIn("typescript", result)


# ---------------------------------------------------------------------------
# Memory Nodes Tests
# ---------------------------------------------------------------------------

class TestMemoryNodes(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.backend = LocalBackend(data_dir=self.tmpdir)

    def test_recall_memories_node(self):
        self.backend.store({"type": "decision", "content": "Use PostgreSQL for write model", "tags": ["architecture"]})
        state = {
            "messages": [{"role": "user", "content": "What database should we use?"}],
            "session_id": "test-session",
            "backend": self.backend,
            "stage": None,
            "memory_context": "",
            "recalled_memories": [],
            "stored_memory_ids": [],
        }
        result = recall_memories(state)
        self.assertIn("memory_context", result)
        self.assertIn("recalled_memories", result)
        self.assertTrue(len(result["recalled_memories"]) >= 1)

    def test_recall_memories_with_stage(self):
        self.backend.store({"type": "instruction", "content": "Must write tests first", "tags": ["testing", "validation"]})
        state = {
            "messages": [{"role": "user", "content": "Write the auth module"}],
            "session_id": "test-session",
            "backend": self.backend,
            "stage": "testing",
            "memory_context": "",
            "recalled_memories": [],
            "stored_memory_ids": [],
        }
        result = recall_memories(state)
        self.assertTrue(len(result["recalled_memories"]) >= 1)

    def test_store_memories_node(self):
        state = {
            "messages": [
                {"role": "user", "content": "Design the system"},
                {"role": "assistant", "content": "We decided to use event sourcing for orders"},
            ],
            "session_id": "test-session",
            "backend": self.backend,
            "stage": "planning",
            "memory_context": "",
            "recalled_memories": [],
            "stored_memory_ids": [],
        }
        result = store_memories(state)
        self.assertIn("stored_memory_ids", result)
        self.assertTrue(len(result["stored_memory_ids"]) >= 1)

    def test_store_and_recall_roundtrip(self):
        # Store via node
        state_in = {
            "messages": [
                {"role": "user", "content": "Design the order system"},
                {"role": "assistant", "content": "We decided to use event sourcing for the order module"},
            ],
            "session_id": "session-A",
            "backend": self.backend,
            "stage": "planning",
            "memory_context": "",
            "recalled_memories": [],
            "stored_memory_ids": [],
        }
        store_memories(state_in)

        # Recall via node
        state_out = {
            "messages": [{"role": "user", "content": "What is our order architecture?"}],
            "session_id": "session-B",
            "backend": self.backend,
            "stage": "research",
            "memory_context": "",
            "recalled_memories": [],
            "stored_memory_ids": [],
        }
        result = recall_memories(state_out)
        self.assertTrue(len(result["recalled_memories"]) >= 1)
        self.assertIn("event sourcing", result["memory_context"].lower())

    def test_empty_recall(self):
        state = {
            "messages": [{"role": "user", "content": "Hello"}],
            "session_id": "test-session",
            "backend": self.backend,
            "stage": None,
            "memory_context": "",
            "recalled_memories": [],
            "stored_memory_ids": [],
        }
        result = recall_memories(state)
        self.assertEqual(result["memory_context"], "")
        self.assertEqual(result["recalled_memories"], [])


# ---------------------------------------------------------------------------
# Graph Builder Tests
# ---------------------------------------------------------------------------

class TestGraphBuilder(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.backend = LocalBackend(data_dir=self.tmpdir)

    def test_build_graph(self):
        graph = build_memory_graph(backend=self.backend)
        self.assertIsNotNone(graph)

    def test_invoke_graph(self):
        result = invoke_graph(
            "We decided to use PostgreSQL for the database",
            session_id="test-session",
            backend=self.backend,
        )
        self.assertIn("messages", result)
        self.assertIn("memory_context", result)
        self.assertIn("stored_memory_ids", result)
        self.assertIn("recalled_memories", result)

    def test_invoke_graph_stores_signals(self):
        result = invoke_graph(
            "Design the system. We decided to use microservices architecture.",
            session_id="test-session",
            stage="planning",
            backend=self.backend,
        )
        # Should extract at least one signal
        self.assertTrue(len(result.get("stored_memory_ids", [])) >= 1)

    def test_invoke_graph_with_custom_agent(self):
        def custom_agent(state):
            messages = state.get("messages", [])
            return {
                **state,
                "messages": messages + [{"role": "assistant", "content": "Custom response"}],
            }

        result = invoke_graph(
            "Hello",
            backend=self.backend,
            agent_node=custom_agent,
        )
        self.assertTrue(any(
            m.get("content") == "Custom response"
            for m in result.get("messages", [])
        ))

    def test_cross_session_via_invoke(self):
        # Session 1: store a decision
        invoke_graph(
            "We decided to use event sourcing",
            session_id="session-1",
            backend=self.backend,
        )
        # Session 2: should recall that decision
        result = invoke_graph(
            "What architecture did we choose?",
            session_id="session-2",
            backend=self.backend,
        )
        self.assertTrue(len(result.get("recalled_memories", [])) >= 1)


# ---------------------------------------------------------------------------
# Hooks Tests
# ---------------------------------------------------------------------------

class TestHooks(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.backend = LocalBackend(data_dir=self.tmpdir)

    def test_pre_hook_returns_context(self):
        self.backend.store({"type": "decision", "content": "Use PostgreSQL for write model", "tags": ["architecture"]})
        context = pre_execution_hook("What database should we use?", backend=self.backend)
        self.assertIsInstance(context, str)
        self.assertIn("PostgreSQL", context)

    def test_pre_hook_empty(self):
        context = pre_execution_hook("Hello world", backend=self.backend)
        self.assertIsInstance(context, str)
        self.assertEqual(context, "")

    def test_post_hook_stores_signals(self):
        ids = post_execution_hook(
            "Design the order system",
            "We decided to use event sourcing for orders. Must always use domain events.",
            stage="planning",
            backend=self.backend,
        )
        self.assertTrue(len(ids) >= 1)

    def test_post_hook_no_signals(self):
        ids = post_execution_hook(
            "Hello",
            "The weather is nice today.",
            backend=self.backend,
        )
        self.assertEqual(len(ids), 0)

    def test_full_lifecycle_hooks(self):
        # Pre-hook for first interaction
        context1 = pre_execution_hook("Design the order system", session_id="session-A", backend=self.backend)
        self.assertIsInstance(context1, str)
        # Post-hook after LLM response
        skill_output = "We decided to use event sourcing for the order module. Must always use aggregate roots."
        ids = post_execution_hook("Design the order system", skill_output, session_id="session-A", stage="planning", backend=self.backend)
        self.assertTrue(len(ids) >= 1)
        # Pre-hook for second interaction (should recall stored memories)
        context2 = pre_execution_hook("What is our order module architecture?", session_id="session-B", backend=self.backend)
        self.assertIsInstance(context2, str)
        # Verify recalled context contains stored decisions/signals
        combined = (context2.lower() if context2 else "") + (context1.lower() if context1 else "")
        self.assertIn("event sourcing", combined)

    def test_wrap_execution(self):
        result = wrap_execution(
            "Design the system",
            "We decided to use microservices",
            session_id="test-session",
            stage="planning",
            backend=self.backend,
        )
        self.assertIn("recalled_context", result)
        self.assertIn("stored_memory_ids", result)
        self.assertIn("memories_stored_count", result)

    def test_cross_session_recall_via_hooks(self):
        # Session A: store a memory
        post_execution_hook(
            "Design the system",
            "We decided to use React for the frontend",
            session_id="session-A",
            backend=self.backend,
        )
        # Session B: recall the memory
        context = pre_execution_hook(
            "What frontend framework should we use?",
            session_id="session-B",
            backend=self.backend,
        )
        self.assertIn("React", context)


# ---------------------------------------------------------------------------
# Cross-Session Recall Integration Tests
# ---------------------------------------------------------------------------

class TestCrossSessionRecall(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # All sessions share the same data dir
        self.backend_factory = lambda: LocalBackend(data_dir=self.tmpdir)

    def test_shared_backend_cross_session(self):
        # Session A
        backend_a = self.backend_factory()
        backend_a.store({"type": "decision", "content": "Use Redis for caching", "tags": ["infrastructure"]})

        # Session B
        backend_b = self.backend_factory()
        results = backend_b.recall("Redis caching")
        self.assertTrue(len(results) >= 1)
        self.assertIn("Redis", results[0]["content"])

    def test_graph_cross_session(self):
        # Session 1: store via graph
        invoke_graph(
            "We decided to use Kafka for event streaming",
            session_id="producer-session",
            backend=self.backend_factory(),
        )

        # Session 2: recall via graph
        result = invoke_graph(
            "What event streaming technology do we use?",
            session_id="consumer-session",
            backend=self.backend_factory(),
        )
        recalled = result.get("recalled_memories", [])
        self.assertTrue(len(recalled) >= 1)

    def test_hooks_cross_session(self):
        # Session A
        post_execution_hook(
            "Setup monitoring",
            "We decided to use Prometheus for monitoring. Must always track latency metrics.",
            session_id="devops-A",
            backend=self.backend_factory(),
        )

        # Session B (different session)
        context = pre_execution_hook(
            "What monitoring tool should we set up?",
            session_id="devops-B",
            backend=self.backend_factory(),
        )
        self.assertIn("Prometheus", context)


if __name__ == "__main__":
    unittest.main()
