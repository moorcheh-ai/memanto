from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mattpocock_adapter import install_wrappers, render_wrapper
from skill_memory import LocalJsonlBackend, SkillMemoryBridge, distill_memories


class SkillMemoryTests(unittest.TestCase):
    def test_distill_memories_extracts_explicit_signals(self) -> None:
        memories = distill_memories(
            "\n".join(
                [
                    "decision: keep adapters thin",
                    "preference: prefer pytest fixtures",
                    "debug noise without a durable prefix",
                ]
            ),
            source_skill="/grill-with-docs",
            cwd=Path("/repo"),
        )

        self.assertEqual(
            [item.memory_type for item in memories],
            ["decision", "preference"],
        )
        self.assertEqual(memories[0].text, "keep adapters thin")

    def test_local_backend_deduplicates_and_recalls_by_relevance(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            backend = LocalJsonlBackend(Path(raw_tmp) / "memories.jsonl")
            bridge = SkillMemoryBridge(backend)

            transcript = "decision: use SQLAlchemy repository tests"
            bridge.after_skill("/tdd", transcript, Path("/repo"))
            bridge.after_skill("/tdd", transcript, Path("/repo"))

            recalled = backend.recall("repository tests with SQLAlchemy")

        self.assertEqual(len(recalled), 1)
        self.assertEqual(recalled[0].text, "use SQLAlchemy repository tests")

    def test_before_skill_formats_injected_context(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            backend = LocalJsonlBackend(Path(raw_tmp) / "memories.jsonl")
            bridge = SkillMemoryBridge(backend)
            bridge.after_skill(
                "/handoff",
                "instruction: preserve public API names during refactors",
                Path("/repo"),
            )

            context = bridge.before_skill(
                "/tdd", "refactor public API tests", Path("/repo")
            )

        self.assertIn("Relevant Memanto engineering memory", context)
        self.assertIn("preserve public API names", context)

    def test_adapter_generates_executable_wrappers(self) -> None:
        script = render_wrapper("/tdd", "/usr/local/bin/tdd", Path("/bridge"))
        self.assertIn('skill_name="/tdd"', script)
        self.assertIn('bridge_dir="/bridge"', script)

        with tempfile.TemporaryDirectory() as raw_tmp:
            paths = install_wrappers(Path(raw_tmp), bridge_dir=Path("/bridge"))
            names = sorted(path.name for path in paths)
            modes = [path.stat().st_mode & 0o111 for path in paths]

        self.assertEqual(names, ["grill-with-docs", "handoff", "tdd"])
        self.assertTrue(all(mode for mode in modes))


if __name__ == "__main__":
    unittest.main()
