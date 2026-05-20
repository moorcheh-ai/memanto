"""Stdlib tests for the Claude Code skills + Memanto example."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from skill_memory import LocalPreviewMemoryStore, SkillMemoryHook


class SkillMemoryExampleTest(unittest.TestCase):
    def test_local_preview_reuses_cross_skill_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_path = Path(tmpdir) / "skills-memory.jsonl"
            first_hook = SkillMemoryHook(LocalPreviewMemoryStore(memory_path))
            first_hook.after_skill(
                "/grill-with-docs",
                "Review billing retry architecture",
                """
Decision: Keep retry scheduling in billing/retry.py.
Preference: Use fake clock fixtures for retry tests.
""",
                ["billing/retry.py"],
            )

            second_hook = SkillMemoryHook(LocalPreviewMemoryStore(memory_path))
            context = second_hook.before_skill(
                "/tdd",
                "Write retry tests for billing/retry.py",
                ["tests/billing/test_retry.py", "billing/retry.py"],
            )

            self.assertIn("billing/retry.py", context)
            self.assertIn("fake clock", context)

    def test_runner_wraps_command_with_local_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            memory_path = Path(tmpdir) / "memories.jsonl"
            env = os.environ.copy()
            env["MEMANTO_SKILLS_MEMORY"] = str(memory_path)
            env["MEMANTO_SKILLS_BACKEND"] = "local-preview"

            hook = SkillMemoryHook(LocalPreviewMemoryStore(memory_path))
            hook.after_skill(
                "/handoff",
                "Seed notes",
                "Decision: Keep retry logic in billing/retry.py.",
                ["billing/retry.py"],
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "run_skill_with_memory.py",
                    "--skill",
                    "/tdd",
                    "--task",
                    "Write retry tests",
                    "--file",
                    "billing/retry.py",
                    "--",
                    sys.executable,
                    "-c",
                    "print('wrapped command ran')",
                ],
                cwd=Path(__file__).parent,
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Relevant prior engineering memory from Memanto", result.stdout)
            self.assertIn("billing/retry.py", result.stdout)
            self.assertIn("wrapped command ran", result.stdout)


if __name__ == "__main__":
    unittest.main()
