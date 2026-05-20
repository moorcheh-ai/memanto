from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_memory import (
    LocalJsonBackend,
    SkillRun,
    extract_memories,
    render_injected_context,
)


class SkillMemoryTests(unittest.TestCase):
    def test_extracts_engineering_decisions(self) -> None:
        run = SkillRun(
            skill="/grill-with-docs",
            task="Review checkout architecture",
            output="Decision: keep checkout state in the order aggregate. Avoid browser globals.",
            cwd="apps/web",
            files=["apps/web/checkout.ts"],
        )
        memories = extract_memories(run)
        self.assertGreaterEqual(len(memories), 1)
        self.assertEqual(memories[0].memory_type, "decision")
        self.assertIn("checkout", memories[0].text.lower())

    def test_local_backend_recalls_relevant_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backend = LocalJsonBackend(Path(temp) / "memory.json")
            memory = extract_memories(
                SkillRun(
                    skill="/handoff",
                    task="Document API auth rules",
                    output="The auth module owns token parsing. Avoid global mutable caches.",
                    cwd="services/api",
                    files=["services/api/auth.py"],
                )
            )[0]
            backend.remember(memory)
            recalled = backend.recall("write auth tests for services/api", limit=3)
            self.assertEqual(len(recalled), 1)
            self.assertEqual(recalled[0].files, ["services/api/auth.py"])

    def test_local_backend_deduplicates_identical_memories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backend = LocalJsonBackend(Path(temp) / "memory.json")
            memory = extract_memories(
                SkillRun(
                    skill="/tdd",
                    task="Test worker retry policy",
                    output="Decision: retry transient queue failures three times.",
                )
            )[0]
            backend.remember(memory)
            backend.remember(memory)
            self.assertEqual(len(backend.recall("queue retry policy", limit=10)), 1)

    def test_rendered_context_is_prompt_ready(self) -> None:
        memory = extract_memories(
            SkillRun(
                skill="/grill-with-docs",
                task="Review frontend data flow",
                output="Prefer TanStack Query for server state in dashboard modules.",
                files=["apps/web/dashboard.tsx"],
            )
        )[0]
        rendered = render_injected_context([memory])
        self.assertIn("Memanto recalled", rendered)
        self.assertIn("dashboard.tsx", rendered)

    def test_error_outputs_are_stored_as_error_memories(self) -> None:
        memory = extract_memories(
            SkillRun(
                skill="/tdd",
                task="Fix queue worker tests",
                output="Traceback: worker retry policy failed with a timeout exception.",
                files=["workers/retry.py"],
            )
        )[0]
        self.assertEqual(memory.memory_type, "error")
        self.assertGreaterEqual(memory.confidence, 0.8)


if __name__ == "__main__":
    unittest.main()
