from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODULE_PATH = ROOT / "skill_memory.py"
spec = importlib.util.spec_from_file_location("skill_memory", MODULE_PATH)
assert spec and spec.loader
skill_memory = importlib.util.module_from_spec(spec)
sys.modules["skill_memory"] = skill_memory
spec.loader.exec_module(skill_memory)


class SkillMemoryTests(unittest.TestCase):
    def test_local_backend_distill_store_and_inject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = skill_memory.LocalJsonlBackend(Path(tmp) / "memories.jsonl")
            completed = skill_memory.SkillRun(
                skill="grill-with-docs",
                task="Review retry policy",
                files=("src/billing/retries.ts",),
                transcript=(
                    "Decision: keep retries deterministic in tests. "
                    "Avoid wall-clock sleeps."
                ),
                cwd="/repo/payments",
            )

            stored = skill_memory.store_completed_run(completed, backend)

            self.assertEqual(stored, 1)
            later = skill_memory.SkillRun(
                skill="tdd",
                task="Add retry tests",
                files=("src/billing/retries.ts",),
                cwd="/repo/payments",
            )
            block = skill_memory.build_injection_block(later, backend, limit=3)
            self.assertIn("<memanto-engineering-memory>", block)
            self.assertIn("deterministic", block)
            self.assertIn("wall-clock", block)

    def test_wrapper_passes_injected_context_to_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = skill_memory.LocalJsonlBackend(Path(tmp) / "memories.jsonl")
            skill_memory.store_completed_run(
                skill_memory.SkillRun(
                    skill="handoff",
                    task="Summarize retry policy",
                    files=("src/billing/retries.ts",),
                    transcript="Decision: preserve idempotency keys across retries.",
                    cwd="/repo/payments",
                ),
                backend,
            )

            run = skill_memory.SkillRun(
                skill="tdd",
                task="Add billing retry tests",
                files=("src/billing/retries.ts",),
                cwd="/repo/payments",
            )
            rc = skill_memory.run_wrapped_command(
                run,
                [
                    sys.executable,
                    "-c",
                    "import os; assert 'idempotency' in os.environ['MEMANTO_SKILL_CONTEXT']",
                ],
                backend,
                limit=3,
            )

            self.assertEqual(rc, 0)

    def test_validate_script_runs_without_credentials(self) -> None:
        env = os.environ.copy()
        env.pop("MOORCHEH_API_KEY", None)
        completed = subprocess.run(
            [sys.executable, str(ROOT / "validate.py")],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

        self.assertIn("credential-free validation passed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
