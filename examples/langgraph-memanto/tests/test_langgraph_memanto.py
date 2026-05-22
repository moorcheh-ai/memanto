from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "langgraph_memanto.py"
SPEC = importlib.util.spec_from_file_location("langgraph_memanto", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
if not SPEC or not SPEC.loader:
    raise ImportError(f"Failed to load module spec from {MODULE_PATH}")
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class LangGraphMemantoTests(unittest.TestCase):
    def test_jsonl_backend_remembers_and_recalls_across_instances(self) -> None:
        path = Path(self._testMethodName + ".jsonl")
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        backend = module.JsonlMemoryBackend(path)
        memory_id = backend.remember(
            "Decision: Use PostgreSQL for tenant billing records.",
            memory_type="decision",
            tags=["database", "billing"],
            source="planner",
        )

        reopened = module.JsonlMemoryBackend(path)
        hits = reopened.recall("billing database postgres", limit=1)

        self.assertTrue(memory_id)
        self.assertEqual(len(hits), 1)
        self.assertIn("PostgreSQL", hits[0].content)
        self.assertEqual(hits[0].type, "decision")

    def test_inject_context_adds_recalled_memories_without_mutating_state(self) -> None:
        path = Path(self._testMethodName + ".jsonl")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        backend = module.JsonlMemoryBackend(path)
        backend.remember(
            "Preference: Project Apollo status updates should be concise.",
            memory_type="preference",
            tags=["project-apollo"],
        )
        memory = module.MemantoGraphMemory(backend, recall_limit=2)
        state = {
            "messages": [
                {
                    "role": "user",
                    "content": "How should I write Project Apollo status updates?",
                }
            ]
        }

        hydrated = memory.inject_context(state)

        self.assertNotIn("memanto_context", state)
        self.assertIn("status updates should be concise", hydrated["memanto_context"])
        self.assertEqual(len(hydrated["memanto_hits"]), 1)

    def test_wrap_node_recalls_before_and_stores_marked_node_output(self) -> None:
        path = Path(self._testMethodName + ".jsonl")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        backend = module.JsonlMemoryBackend(path)
        backend.remember(
            "Fact: The existing queue is Celery.",
            memory_type="fact",
            tags=["queue"],
        )
        memory = module.MemantoGraphMemory(backend, recall_limit=2)

        def node(state):
            self.assertIn("Celery", state["memanto_context"])
            return {
                "messages": [
                    {
                        "role": "assistant",
                        "content": "Decision: Migrate queue workers from Celery to Redis Streams.",
                    }
                ]
            }

        wrapped = memory.wrap_node(node, node_name="architect")
        wrapped(
            {
                "messages": [
                    {"role": "user", "content": "What is the queue migration plan?"}
                ]
            }
        )

        hits = backend.recall("redis streams queue migration", limit=1)
        self.assertEqual(len(hits), 1)
        self.assertIn("Redis Streams", hits[0].content)
        self.assertEqual(hits[0].type, "decision")

    def test_remember_node_accepts_structured_memory_payloads(self) -> None:
        path = Path(self._testMethodName + ".jsonl")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        backend = module.JsonlMemoryBackend(path)
        memory = module.MemantoGraphMemory(backend, recall_limit=2)

        update = memory.remember_node(
            {
                "remember": [
                    {
                        "content": "Preference: Use short bullet lists in release notes.",
                        "type": "preference",
                        "tags": ["writing"],
                    }
                ]
            }
        )
        hits = backend.recall("release notes short bullet lists", limit=1)

        self.assertEqual(update["memanto_saved"], 1)
        self.assertIn("short bullet lists", hits[0].content)
        self.assertEqual(hits[0].type, "preference")

    def test_secret_redaction_before_storage(self) -> None:
        path = Path(self._testMethodName + ".jsonl")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        backend = module.JsonlMemoryBackend(path)

        backend.remember(
            "Fact: integration token=sk-test-secret-value should never be exposed.",
            memory_type="fact",
        )
        rows = path.read_text(encoding="utf-8")

        self.assertIn("[REDACTED]", rows)
        self.assertNotIn("sk-test-secret-value", rows)


if __name__ == "__main__":
    unittest.main()
