from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mattpocock_adapter import default_specs, render_wrapper, write_wrappers
from skill_memory import (
    EngineeringMemory,
    LocalJsonlBackend,
    SkillMemoryHook,
    SkillRun,
    distill_memories,
)


class SkillMemoryTests(unittest.TestCase):
    def test_distill_memories_extracts_typed_records(self) -> None:
        run = SkillRun(skill="grill-with-docs", task="Plan importer")
        memories = distill_memories(
            "\n".join(
                [
                    "Decision: Use streaming parser",
                    "Preference: Keep services explicit",
                    "Constraint: Avoid a second queue system",
                ]
            ),
            run,
        )

        self.assertEqual(
            [memory.memory_type for memory in memories],
            ["decision", "preference", "instruction"],
        )
        self.assertTrue(all("skill:grill-with-docs" in m.tags for m in memories))

    def test_local_backend_recalls_across_skill_runs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            backend = LocalJsonlBackend(Path(temp_dir) / "memory.jsonl")
            hook = SkillMemoryHook(backend)
            first_run = SkillRun(
                skill="grill-with-docs",
                task="Plan invoice import architecture",
                workspace="billing",
                files=("src/invoices/parser.ts",),
            )
            hook.after_skill(
                first_run,
                "Decision: Use a streaming parser for invoice imports.",
            )

            second_run = SkillRun(
                skill="tdd",
                task="Write invoice parser tests",
                workspace="billing",
                files=("src/invoices/parser.ts",),
            )
            context = hook.before_skill(second_run)

        self.assertIn("streaming parser", context)
        self.assertIn("Memanto Skill Memory", context)

    def test_local_backend_writes_jsonl(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "memory.jsonl"
            backend = LocalJsonlBackend(path)
            backend.remember(
                EngineeringMemory(
                    memory_type="decision",
                    title="Use local backend",
                    content="Use JSONL for review-safe validation.",
                )
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["memory_type"], "decision")
        self.assertIn("id", payload)

    def test_adapter_generates_executable_wrappers(self) -> None:
        spec = default_specs()[0]
        wrapper = render_wrapper(spec)
        self.assertIn("skill_memory.py before", wrapper)
        self.assertIn("skill_memory.py after", wrapper)

        with TemporaryDirectory() as temp_dir:
            written = write_wrappers(Path(temp_dir), [spec])
            paths = {path.name for path in written}

        self.assertEqual(paths, {spec.skill, "manifest.json"})


if __name__ == "__main__":
    unittest.main()
