from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mattpocock_adapter import wrapper_script
from productivity_benchmark import run_benchmark
from skill_memory import (
    EngineeringMemory,
    LocalJsonBackend,
    MemantoCliBackend,
    MemantoSdkBackend,
    SkillRun,
    extract_memories,
    render_injected_context,
    split_signal,
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

    def test_extract_memories_honors_max_items(self) -> None:
        memories = extract_memories(
            SkillRun(
                skill="/handoff",
                task="Prepare release notes.",
                output=(
                    "Decision: ship the auth fix first. "
                    "Preference: keep release notes short. "
                    "Must: include rollback instructions. "
                    "Traceback: deploy smoke failed once."
                ),
            ),
            max_items=2,
        )
        self.assertEqual(len(memories), 2)
        self.assertEqual(memories[0].memory_type, "decision")
        self.assertEqual(memories[1].memory_type, "preference")

    def test_split_signal_preserves_bulleted_skill_output(self) -> None:
        signals = split_signal(
            "Decision summary:\n"
            "- Decision: keep auth middleware stateless for tenant isolation.\n"
            "- Must: avoid global mutable caches in parallel tests.\n"
        )
        self.assertEqual(len(signals), 2)
        self.assertIn("Decision: keep auth middleware stateless", signals[0])
        self.assertIn("avoid global mutable caches", signals[1])

    def test_local_backend_ranks_by_query_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backend = LocalJsonBackend(Path(temp) / "memory.json")
            backend.remember(
                EngineeringMemory(
                    text="The auth middleware owns token parsing and tenant lookup.",
                    memory_type="decision",
                    skill="/grill-with-docs",
                    task="Review auth middleware",
                    cwd="services/api",
                    files=["services/api/auth.py"],
                )
            )
            backend.remember(
                EngineeringMemory(
                    text="The dashboard should avoid browser globals.",
                    memory_type="instruction",
                    skill="/tdd",
                    task="Write frontend tests",
                    cwd="apps/web",
                    files=["apps/web/dashboard.tsx"],
                )
            )
            recalled = backend.recall("auth token parsing services/api", limit=2)
            self.assertEqual(recalled[0].files, ["services/api/auth.py"])

    def test_local_backend_returns_empty_when_memory_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backend = LocalJsonBackend(Path(temp) / "missing.json")
            self.assertEqual(backend.recall("anything", limit=5), [])

    def test_skill_run_from_json_defaults_optional_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_file = Path(temp) / "run.json"
            run_file.write_text(
                json.dumps({"skill": "/tdd", "task": "Add tests"}) + "\n",
                encoding="utf-8",
            )
            run = SkillRun.from_json(run_file)
            self.assertEqual(run.output, "")
            self.assertEqual(run.cwd, ".")
            self.assertEqual(run.files, [])

    def test_memanto_text_includes_source_metadata(self) -> None:
        memory = EngineeringMemory(
            text="Prefer SDK recall before CLI fallback.",
            memory_type="preference",
            skill="/handoff",
            task="Document memory backends",
            cwd="examples",
            files=["README.md"],
        )
        text = memory.to_memanto_text()
        self.assertIn("[preference]", text)
        self.assertIn("source_skill=/handoff", text)
        self.assertIn("files=README.md", text)

    def test_rendered_context_handles_empty_recall(self) -> None:
        self.assertEqual(
            render_injected_context([]),
            "No relevant Memanto skill memories found.",
        )

    def test_cli_backend_parses_stdout_lines(self) -> None:
        completed = Mock(stdout="Keep auth stateless\n\nAvoid global caches\n")
        with patch("skill_memory.subprocess.run", return_value=completed) as run:
            memories = MemantoCliBackend().recall("auth", limit=2)
        run.assert_called_once()
        self.assertEqual(
            [memory.text for memory in memories],
            ["Keep auth stateless", "Avoid global caches"],
        )
        self.assertTrue(all(memory.skill == "memanto-recall" for memory in memories))

    def test_sdk_synthesis_returns_prompt_context_memory(self) -> None:
        backend = MemantoSdkBackend.__new__(MemantoSdkBackend)
        backend.agent_id = "agent-123"
        backend.client = Mock()
        backend.client.answer.return_value = {
            "answer": "- Keep auth middleware stateless\n- Avoid global mutable caches"
        }
        memory = backend._synthesize_constraints("implement auth tests", limit=4)
        self.assertIsNotNone(memory)
        assert memory is not None
        self.assertEqual(memory.skill, "memanto-sdk-answer")
        self.assertEqual(memory.memory_type, "context")
        self.assertIn("stateless", memory.text)

    def test_sdk_synthesis_ignores_empty_or_negative_answers(self) -> None:
        backend = MemantoSdkBackend.__new__(MemantoSdkBackend)
        backend.agent_id = "agent-123"
        backend.client = Mock()
        backend.client.answer.return_value = {"answer": "No relevant memories found."}
        self.assertIsNone(backend._synthesize_constraints("new task", limit=4))

    def test_productivity_benchmark_reports_instruction_reduction(self) -> None:
        metrics = run_benchmark()
        self.assertEqual(
            metrics["skill_sequence"],
            ["/grill-with-docs", "/tdd", "/handoff"],
        )
        self.assertEqual(metrics["baseline_repeated_instructions"], 6)
        self.assertEqual(metrics["memanto_injected_constraints"], 6)
        self.assertEqual(metrics["repeated_instruction_reduction_pct"], 100.0)

    def test_generated_wrapper_exports_skill_context_for_child_processes(self) -> None:
        script = wrapper_script("/tdd", "claude")
        self.assertIn("export MEMANTO_SKILL_CONTEXT", script)
        self.assertIn("printf '%s\\n' \"$SKILL_CONTEXT\"", script)
        self.assertIn("pre-skill", script)

    def test_generated_wrapper_passes_file_context_through_hooks(self) -> None:
        script = wrapper_script("/handoff", "claude")
        self.assertIn("SKILL_MEMORY_FILES", script)
        self.assertIn('--files "${SKILL_FILES[@]}"', script)
        self.assertIn('"files": files', script)


if __name__ == "__main__":
    unittest.main()
