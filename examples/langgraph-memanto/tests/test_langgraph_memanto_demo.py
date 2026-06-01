from __future__ import annotations

import sys
import unittest
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory

EXAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))

from customer_support_graph import build_customer_support_graph  # noqa: E402
from memory_backends import FileMemoryBackend  # noqa: E402


class LangGraphMemantoDemoTests(unittest.TestCase):
    def test_file_backend_ranks_relevant_memories(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backend = FileMemoryBackend(Path(temp_dir) / "memory.json")
            backend.remember("Customer Alex is on the enterprise plan.")
            backend.remember("Invoices for Alex should stay in GBP.")
            backend.remember("Customer Sam prefers phone follow-ups.")

            recalled = backend.recall("Alex invoices GBP", limit=2)

        self.assertEqual(
            recalled,
            [
                "Invoices for Alex should stay in GBP.",
                "Customer Alex is on the enterprise plan.",
            ],
        )

    def test_file_backend_recovers_from_unexpected_json_shape(self) -> None:
        with TemporaryDirectory() as temp_dir:
            memory_file = Path(temp_dir) / "memory.json"
            memory_file.write_text('{"content": "not a list"}', encoding="utf-8")
            backend = FileMemoryBackend(memory_file)

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                self.assertEqual(backend.recall("anything"), [])
                backend.remember("Customer Alex prefers email follow-ups.")

            self.assertTrue(
                any(
                    "unexpected demo memory shape" in str(warning.message)
                    for warning in caught
                )
            )
            self.assertEqual(
                backend.recall("Alex email"),
                ["Customer Alex prefers email follow-ups."],
            )

    def test_graph_requires_question_before_recall(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backend = FileMemoryBackend(Path(temp_dir) / "memory.json")
            graph = build_customer_support_graph(backend)

            with self.assertRaises(ValueError):
                graph.invoke({})

    def test_graph_recalls_cross_session_memory_and_stores_new_learning(self) -> None:
        with TemporaryDirectory() as temp_dir:
            memory_file = Path(temp_dir) / "memory.json"
            yesterday_memory = FileMemoryBackend(memory_file)
            yesterday_memory.remember(
                "Customer Alex prefers email follow-ups before demos."
            )
            yesterday_memory.remember("Invoices for Alex should stay in GBP.")

            today_memory = FileMemoryBackend(memory_file)
            graph = build_customer_support_graph(today_memory)
            result = graph.invoke(
                {
                    "question": (
                        "Alex prefers a quick email before the demo and asks "
                        "which invoice currency we will use."
                    )
                }
            )

        self.assertIn(
            "Customer Alex prefers email follow-ups before demos.",
            result["recalled_memories"],
        )
        self.assertIn(
            "Invoices for Alex should stay in GBP.", result["recalled_memories"]
        )
        self.assertIn("email follow-up", result["response"])
        self.assertIn("New support preference", result["stored_learning"])


if __name__ == "__main__":
    unittest.main()
