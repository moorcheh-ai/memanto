from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mattpocock_adapter import write_wrappers
from run_demo import DemoResult, write_benchmark_report
from skill_memory import (
    LocalJsonBackend,
    after_skill,
    before_skill,
    extract_memories,
)


class SkillMemoryTests(unittest.TestCase):
    def test_extracts_typed_memories_from_transcript(self) -> None:
        transcript = "\n".join(
            [
                "Decision: Use shared API client for billing mutations.",
                "Preference: Keep generated wrappers checked into examples only.",
                "Rule: Never store private API keys in memory payloads.",
            ]
        )

        memories = extract_memories(
            "/grill-with-docs",
            "review billing client",
            transcript,
            ["src/billing/client.py"],
        )

        self.assertEqual(["decision", "preference", "instruction"], [m.type for m in memories])
        self.assertIn("billing", memories[0].tags)

    def test_local_backend_recalls_relevant_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalJsonBackend(Path(tmpdir) / "memory.jsonl")
            stored = after_skill(
                backend,
                "/grill-with-docs",
                "review form architecture",
                "Decision: Prefer server-side validation helpers.",
                ["docs/forms.md"],
            )

            self.assertEqual(1, len(stored))
            injected = before_skill(
                backend,
                "/tdd",
                "write tests for server-side form validation",
                ["tests/test_forms.py"],
            )

            self.assertIn("server-side validation helpers", injected)

    def test_before_skill_includes_grounded_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalJsonBackend(Path(tmpdir) / "memory.jsonl")
            after_skill(
                backend,
                "/grill-with-docs",
                "review form architecture",
                "Decision: Prefer server-side validation helpers.",
                ["docs/forms.md"],
            )

            injected = before_skill(
                backend,
                "/tdd",
                "write tests for server-side form validation",
                ["tests/test_forms.py"],
            )

            self.assertIn("[memanto-answer]", injected)
            self.assertIn("Apply remembered context", injected)

    def test_before_skill_reports_empty_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalJsonBackend(Path(tmpdir) / "memory.jsonl")
            injected = before_skill(backend, "/handoff", "summarize unrelated work", [])

            self.assertIn("No relevant prior engineering memories", injected)

    def test_fallback_summary_is_stored_when_no_pattern_matches(self) -> None:
        memories = extract_memories(
            "/handoff",
            "handoff work",
            "Finished the parser repair. Tests pass.",
            ["src/parser.py"],
        )

        self.assertEqual(1, len(memories))
        self.assertEqual("context", memories[0].type)
        self.assertIn("parser", memories[0].tags)

    def test_benchmark_report_quantifies_repeated_instruction_reduction(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report = Path(tmpdir) / "benchmark.md"
            write_benchmark_report(
                DemoResult(
                    stored_memories=3,
                    recalled_expected_rule=True,
                    baseline_repeated_instructions=1,
                    memanto_repeated_instructions=0,
                ),
                report,
            )

            content = report.read_text(encoding="utf-8")
            self.assertIn("Repeated instructions avoided | 1", content)
            self.assertIn("Repeated-instruction reduction | 100%", content)

    def test_generated_wrapper_exports_memanto_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            wrappers = write_wrappers(["/tdd"], Path(tmpdir))
            wrapper = wrappers[0].read_text(encoding="utf-8")

            self.assertIn("MEMANTO_SKILL_CONTEXT=\"$(python", wrapper)
            self.assertIn("export MEMANTO_SKILL_CONTEXT", wrapper)


if __name__ == "__main__":
    unittest.main()
