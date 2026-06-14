from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_memory_bridge import (
    LocalJsonlBackend,
    MemantoCliBackend,
    MemoryRecord,
    SkillMemoryBridge,
    extract_memories,
    main,
)


class SkillMemoryBridgeTests(unittest.TestCase):
    def test_local_backend_recalls_tagged_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalJsonlBackend(Path(tmp) / "memories.jsonl")
            backend.remember(
                MemoryRecord(
                    content="Use better-sqlite3 for local database access.",
                    memory_type="decision",
                    tags=["billing", "sqlite"],
                )
            )

            recalled = backend.recall("billing sqlite database", tags=["billing"])

        self.assertEqual(len(recalled), 1)
        self.assertIn("better-sqlite3", recalled[0].content)

    def test_bridge_persists_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_file = Path(tmp) / "memories.jsonl"
            first = SkillMemoryBridge(LocalJsonlBackend(memory_file))
            first.after_skill(
                skill_name="/grill-with-docs",
                paths=["src/app/billing"],
                summary="Decision: Billing actions must run on the server.",
            )

            second = SkillMemoryBridge(LocalJsonlBackend(memory_file))
            context = second.before_skill(
                skill_name="/tdd",
                paths=["src/app/billing/actions.ts"],
                prompt="How should I format a changelog?",
            )

        self.assertIn("Billing actions must run on the server", context)

    def test_bridge_recalls_parent_path_for_child_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_file = Path(tmp) / "memories.jsonl"
            first = SkillMemoryBridge(LocalJsonlBackend(memory_file))
            first.after_skill(
                skill_name="/grill-with-docs",
                paths=["src/features/invoices"],
                summary="Decision: Invoice totals must be stored in cents.",
            )

            second = SkillMemoryBridge(LocalJsonlBackend(memory_file))
            context = second.before_skill(
                skill_name="/tdd",
                paths=["src/features/invoices/create-invoice.test.ts"],
                prompt="How should I format a changelog?",
            )

        self.assertIn("Invoice totals must be stored in cents", context)

    def test_wrap_runs_command_in_requested_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp) / "work"
            workdir.mkdir()
            memory_file = Path(tmp) / "memories.jsonl"
            command = (
                "from pathlib import Path; "
                "Path('cwd-marker.txt').write_text('ok', encoding='utf-8')"
            )

            with patch.dict(
                os.environ,
                {
                    "MEMANTO_SKILLS_BACKEND": "local",
                    "MEMANTO_SKILLS_MEMORY_FILE": str(memory_file),
                },
            ):
                return_code = main(
                    [
                        "wrap",
                        "--skill",
                        "/cwd-test",
                        "--prompt",
                        "Run cwd check.",
                        "--cwd",
                        str(workdir),
                        "--",
                        sys.executable,
                        "-c",
                        command,
                    ]
                )

            self.assertEqual(return_code, 0)
            self.assertTrue((workdir / "cwd-marker.txt").exists())

    def test_extract_memories_classifies_prefixes(self) -> None:
        memories = extract_memories(
            "Decision: Prefer server actions for mutations.\n"
            "Preference: Keep components presentational.\n"
            "Gotcha: Avoid Prisma in this codebase.",
            skill_name="/handoff",
        )
        memory_types = [memory.memory_type for memory in memories]

        self.assertIn("decision", memory_types)
        self.assertIn("preference", memory_types)
        self.assertIn("error", memory_types)

    def test_backend_ignores_malformed_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_file = Path(tmp) / "memories.jsonl"
            memory_file.write_text("{not-json}\n", encoding="utf-8")
            backend = LocalJsonlBackend(memory_file)

            self.assertEqual(backend.recall("anything"), [])

    def test_memory_from_dict_uses_constructor_confidence_default(self) -> None:
        memory = MemoryRecord.from_dict({"content": "Persist deployment decision."})

        self.assertEqual(memory.confidence, 0.82)

    def test_cli_backend_ignores_empty_or_no_result_recall_output(self) -> None:
        no_result_outputs = [
            "",
            " \n",
            "No memories found",
            "No memories found matching your query\nCompleted in 0.01s\n",
            "No relevant memories found.",
        ]

        for output in no_result_outputs:
            completed = subprocess.CompletedProcess(
                args=["memanto", "recall", "query"],
                returncode=0,
                stdout=output,
                stderr="",
            )
            with self.subTest(output=output):
                with patch(
                    "skill_memory_bridge.subprocess.run",
                    return_value=completed,
                ):
                    self.assertEqual(MemantoCliBackend().recall("query"), [])

    def test_cli_backend_parses_structured_recall_items(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["memanto", "recall", "query"],
            returncode=0,
            stdout=(
                '{"memories": ['
                '{"content": "Use local backend in tests.", "type": "decision", '
                '"title": "Test backend", "confidence": 0.91, "tags": ["tests"]},'
                '{"content": "Keep CLI optional.", "memory_type": "instruction"}'
                "]}"
            ),
            stderr="",
        )

        with patch(
            "skill_memory_bridge.subprocess.run",
            return_value=completed,
        ):
            memories = MemantoCliBackend().recall("query", tags=["fallback"])

        self.assertEqual(len(memories), 2)
        self.assertEqual(memories[0].memory_type, "decision")
        self.assertEqual(memories[0].title, "Test backend")
        self.assertEqual(memories[0].confidence, 0.91)
        self.assertEqual(memories[0].tags, ["tests"])
        self.assertEqual(memories[1].memory_type, "instruction")
        self.assertEqual(memories[1].tags, ["fallback"])


if __name__ == "__main__":
    unittest.main()
