from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_memory_bridge import (
    LocalJsonlBackend,
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
                paths=["src/app/billing/actions.ts"],
                summary="Decision: Billing actions must run on the server.",
            )

            second = SkillMemoryBridge(LocalJsonlBackend(memory_file))
            context = second.before_skill(
                skill_name="/tdd",
                paths=["src/app/billing/actions.ts"],
                prompt="Test billing actions.",
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
                prompt="Add invoice tests.",
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
                {"MEMANTO_SKILLS_MEMORY_FILE": str(memory_file)},
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


if __name__ == "__main__":
    unittest.main()
