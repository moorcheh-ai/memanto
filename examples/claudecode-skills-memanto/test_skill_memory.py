from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_memory import LocalJsonlBackend, distill_transcript, post_skill, pre_skill
from wrappers import write_wrappers


class SkillMemoryTests(unittest.TestCase):
    def test_distills_decisions_preferences_and_instructions(self) -> None:
        memories = distill_transcript(
            "grill-with-docs",
            "\n".join(
                [
                    "Decision: Put auth refresh in AuthGateway.",
                    "Preference: Use typed Result values.",
                    "Instruction: Never log refresh tokens.",
                    "Looks good.",
                ]
            ),
        )

        self.assertEqual([m.memory_type for m in memories], ["decision", "preference", "instruction"])

    def test_local_backend_recalls_across_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = LocalJsonlBackend(Path(tmp) / "memory.jsonl")
            post_skill(backend, "grill-with-docs", "Decision: Keep retry policy in AuthGateway.")
            injected = pre_skill(backend, "tdd", "AuthGateway retry tests")

        self.assertIn("AuthGateway", injected)

    def test_wrapper_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_wrappers(Path(tmp))
            names = {path.name for path in paths}

        self.assertEqual(names, {"grill-with-docs", "tdd", "handoff"})


if __name__ == "__main__":
    unittest.main()
