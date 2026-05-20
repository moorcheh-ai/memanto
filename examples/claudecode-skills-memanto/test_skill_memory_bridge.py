"""Tests for the Claude Code skills + Memanto active memory example."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import mattpocock_adapter
import productivity_benchmark
import skill_memory_bridge as bridge


class FakeAnswerBackend:
    def __init__(self, answer: str) -> None:
        self.answer_text = answer
        self.remembered: list[bridge.EngineeringMemory] = []

    def recall(self, query: str, limit: int = 5) -> list[bridge.EngineeringMemory]:
        return []

    def remember(self, memory: bridge.EngineeringMemory) -> None:
        self.remembered.append(memory)

    def answer(
        self,
        question: str,
        header_prompt: str = "",
        footer_prompt: str = "",
        limit: int = 10,
    ) -> dict[str, object]:
        return {"answer": self.answer_text}


class NoAnswerBackend:
    def __init__(self) -> None:
        self.remembered: list[bridge.EngineeringMemory] = []

    def recall(self, query: str, limit: int = 5) -> list[bridge.EngineeringMemory]:
        return []

    def remember(self, memory: bridge.EngineeringMemory) -> None:
        self.remembered.append(memory)


class SkillMemoryBridgeTest(unittest.TestCase):
    def test_active_answer_extraction_is_used_when_backend_supports_it(self) -> None:
        payload = json.dumps(
            {
                "memories": [
                    {
                        "content": "Keep retry scheduling in the service layer.",
                        "memory_type": "decision",
                        "confidence": 0.92,
                        "tags": ["architecture"],
                    },
                    {
                        "content": "Prefer fake clock fixtures for retry tests.",
                        "memory_type": "preference",
                        "confidence": 0.84,
                    },
                ]
            }
        )
        backend = FakeAnswerBackend(payload)
        run = bridge.SkillRun(
            skill="/grill-with-docs",
            task="Review retry architecture",
            files=("billing/retry.py",),
            transcript="A long narrative without deterministic regex markers.",
        )

        stored = bridge.SkillMemoryBridge(backend).after_skill(run)

        self.assertEqual(
            [memory.content for memory in stored],
            [
                "Keep retry scheduling in the service layer.",
                "Prefer fake clock fixtures for retry tests.",
            ],
        )
        self.assertEqual(stored[0].memory_type, "decision")
        self.assertGreaterEqual(stored[0].confidence, 0.9)
        self.assertIn("skill:grill-with-docs", stored[0].tags)
        self.assertIn("file:billing/retry.py", stored[0].tags)
        self.assertEqual(backend.remembered, stored)

    def test_deterministic_fallback_distills_review_transcript(self) -> None:
        run = bridge.SkillRun(
            skill="/tdd",
            task="Implement retry tests",
            files=("tests/test_retry.py",),
            transcript=(
                "Decision: Keep retry scheduling in billing/retry.py.\n"
                "Preference: Use fake clock fixtures for retry tests.\n"
                "Must: Never sleep in retry tests."
            ),
        )

        memories = bridge.EngineeringProfileExtractor().extract(run, NoAnswerBackend())

        self.assertEqual(len(memories), 3)
        self.assertEqual(memories[0].memory_type, "decision")
        self.assertEqual(memories[1].memory_type, "preference")
        self.assertEqual(memories[2].memory_type, "instruction")

    def test_local_backend_recalls_context_across_fresh_skill_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "skills-memory.jsonl"
            first = bridge.SkillMemoryBridge(bridge.LocalJsonlBackend(path))
            first.after_skill(
                bridge.SkillRun(
                    skill="/handoff",
                    task="Capture retry implementation notes",
                    files=("billing/retry.py",),
                    transcript=(
                        "Decision: Keep retry scheduling in billing/retry.py.\n"
                        "Preference: Use fake clock fixtures for retry tests."
                    ),
                )
            )

            second = bridge.SkillMemoryBridge(bridge.LocalJsonlBackend(path))
            context = second.before_skill(
                bridge.SkillRun(
                    skill="/tdd",
                    task="Write retry tests for billing/retry.py",
                    files=("tests/test_retry.py", "billing/retry.py"),
                )
            )

        self.assertIn("<memanto-engineering-memory>", context)
        self.assertIn("billing/retry.py", context)
        self.assertIn("fake clock", context)
        self.assertIn("Treat this memory as guidance", context)

    def test_productivity_benchmark_reports_reprompt_reduction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = productivity_benchmark.run_benchmark(
                Path(tmp) / "benchmark-memory.jsonl"
            )

        self.assertEqual(len(report["sessions"]), 3)
        self.assertGreater(
            report["manual_reprompting"]["instructions_without_memory"],
            report["manual_reprompting"]["instructions_with_memory"],
        )
        self.assertGreaterEqual(report["manual_reprompting"]["reduction_percent"], 60)

    def test_mattpocock_adapter_generates_memory_aware_wrappers(self) -> None:
        specs = mattpocock_adapter.build_specs(backend="local")
        names = {spec.name for spec in specs}

        self.assertEqual(
            names,
            {"grill-with-docs-memory", "tdd-memory", "handoff-memory"},
        )
        for spec in specs:
            self.assertIn("skill_memory_bridge.py recall", spec.body)
            self.assertIn("skill_memory_bridge.py store", spec.body)

        with tempfile.TemporaryDirectory() as tmp:
            written = mattpocock_adapter.write_wrappers(Path(tmp), backend="local")
            self.assertEqual(len(written), 3)
            self.assertTrue((Path(tmp) / "tdd-memory.md").exists())


if __name__ == "__main__":
    unittest.main()
