"""Tests for the Claude Code skills + Memanto bridge example."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))

from memory_backends import FileMemoryBackend  # noqa: E402
from skill_memory_bridge import SkillMemoryBridge, SkillRun  # noqa: E402


class SkillMemoryBridgeTests(unittest.TestCase):
    """Exercise the offline reviewer path used by the bounty PR."""

    def test_bridge_stores_labeled_memories_and_recalls_relevant_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = FileMemoryBackend(Path(tmp_dir) / "memory.json")
            bridge = SkillMemoryBridge(memory)
            review_run = SkillRun(
                skill_name="/grill-with-docs",
                task="Review billing webhook behavior",
                file_paths=["apps/billing/webhooks/stripe.ts"],
            )

            stored = bridge.after_skill(
                review_run,
                """
                Decision: Keep writes idempotent by Stripe event id.
                Preference: Add replay tests before webhook changes.
                Quirk: Billing timestamps are UTC ISO strings.
                Constraint: Do not persist raw Stripe payloads.
                Note: This unlabeled line should not be stored.
                """,
            )

            self.assertEqual(
                stored,
                [
                    "Decision: Keep writes idempotent by Stripe event id.",
                    "Preference: Add replay tests before webhook changes.",
                    "Quirk: Billing timestamps are UTC ISO strings.",
                    "Constraint: Do not persist raw Stripe payloads.",
                ],
            )
            tdd_run = SkillRun(
                skill_name="/tdd",
                task="Add Stripe webhook replay tests",
                file_paths=["apps/billing/webhooks/stripe.test.ts"],
            )

            context = bridge.before_skill(tdd_run)

            self.assertIn("MEMANTO ENGINEERING MEMORY", context)
            self.assertIn("Stripe event id", context)
            self.assertIn("Add replay tests", context)
            self.assertNotIn("unlabeled line", context)

    def test_file_backend_ranks_recall_by_query_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = FileMemoryBackend(Path(tmp_dir) / "memory.json")
            memory.remember("Decision: Stripe webhook replay tests use event ids.")
            memory.remember("Learning: Dashboard filters use URL search params.")
            memory.remember("Constraint: Stripe payloads are discarded after signature checks.")

            recalled = memory.recall("Stripe webhook replay event tests", limit=2)

            self.assertEqual(
                recalled,
                [
                    "Decision: Stripe webhook replay tests use event ids.",
                    "Constraint: Stripe payloads are discarded after signature checks.",
                ],
            )

    def test_malformed_offline_memory_file_recovers_on_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "memory.json"
            path.write_text("{not-json", encoding="utf-8")
            memory = FileMemoryBackend(path)
            bridge = SkillMemoryBridge(memory)
            run = SkillRun(
                skill_name="/handoff",
                task="Summarize webhook constraints",
                file_paths=["apps/billing/webhooks/stripe.ts"],
            )

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                self.assertEqual(memory.recall("webhook"), [])
                bridge.after_skill(run, "Learning: Keep webhook fixtures minimal.")

            self.assertTrue(caught)
            records = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                [record["content"] for record in records],
                ["Learning: Keep webhook fixtures minimal."],
            )

    def test_unexpected_offline_memory_shape_recovers_on_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "memory.json"
            path.write_text('{"content": "not a list"}', encoding="utf-8")
            memory = FileMemoryBackend(path)

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                memory.remember("Decision: Use a same-directory temp file.")

            self.assertTrue(caught)
            records = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(records[0]["content"], "Decision: Use a same-directory temp file.")
            self.assertEqual(records[0]["memory_type"], "learning")


if __name__ == "__main__":
    unittest.main()
