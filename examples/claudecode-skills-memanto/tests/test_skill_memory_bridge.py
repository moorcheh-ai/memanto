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
from skill_memory_bridge import (  # noqa: E402
    SkillExecution,
    SkillMemoryBridge,
    SkillRun,
)


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

    def test_bridge_wraps_any_skill_executor_with_memory_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = FileMemoryBackend(Path(tmp_dir) / "memory.json")
            memory.remember(
                "Decision: Invoice exports must preserve customer locale settings."
            )
            bridge = SkillMemoryBridge(memory)
            run = SkillRun(
                skill_name="/handoff",
                task="Summarize invoice export implementation",
                file_paths=["apps/billing/invoices/export.ts"],
                metadata={"project": "billing"},
            )
            prompts_seen: list[str] = []

            def fake_executor(prompt: str) -> str:
                prompts_seen.append(prompt)
                return "Learning: Invoice exports need a locale regression test."

            result = bridge.run_with_memory(
                run,
                "Create a handoff note for the invoice export branch.",
                fake_executor,
            )

            self.assertIsInstance(result, SkillExecution)
            self.assertEqual(prompts_seen, [result.prompt])
            self.assertIn("MEMANTO ENGINEERING MEMORY", result.prompt)
            self.assertIn("preserve customer locale", result.prompt)
            self.assertIn("Create a handoff note", result.prompt)
            self.assertEqual(
                result.stored_memories,
                ["Learning: Invoice exports need a locale regression test."],
            )

            records = json.loads((Path(tmp_dir) / "memory.json").read_text())
            self.assertEqual(records[-1]["tags"], "claudecode,skills,handoff")

    def test_metadata_contributes_to_recall_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = FileMemoryBackend(Path(tmp_dir) / "memory.json")
            memory.remember("Decision: Mobile builds use expo-router defaults.")
            bridge = SkillMemoryBridge(memory)
            run = SkillRun(
                skill_name="/tdd",
                task="Add route tests",
                file_paths=[],
                metadata={"framework": "expo-router"},
            )

            context = bridge.before_skill(run)

            self.assertIn("expo-router defaults", context)

    def test_skill_name_is_sanitized_before_tag_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            memory = FileMemoryBackend(Path(tmp_dir) / "memory.json")
            bridge = SkillMemoryBridge(memory)
            run = SkillRun(
                skill_name="/Custom skill,runner/v2!!",
                task="Summarize memory bridge tag handling",
                file_paths=[],
            )

            bridge.after_skill(run, "Learning: Tags should stay comma-safe.")
            bridge.after_skill(
                SkillRun(
                    skill_name=" ///,,, ",
                    task="Summarize empty skill tag handling",
                    file_paths=[],
                ),
                "Decision: Empty skill tags fall back to base tags.",
            )

            records = json.loads((Path(tmp_dir) / "memory.json").read_text())
            self.assertEqual(records[0]["tags"], "claudecode,skills,custom-skill-runner-v2")
            self.assertEqual(records[1]["tags"], "claudecode,skills")

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
