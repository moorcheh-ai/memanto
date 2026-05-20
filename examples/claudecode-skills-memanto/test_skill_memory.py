#!/usr/bin/env python3
"""Unit tests for the credential-free Memanto skills bridge preview path."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


skill_memory = load_module("skill_memory", ROOT / "skill_memory.py")
mattpocock_adapter = load_module("mattpocock_adapter", ROOT / "mattpocock_adapter.py")


class SkillMemoryPreviewTests(unittest.TestCase):
    def test_extract_memories_classifies_durable_signals(self) -> None:
        memories = skill_memory.extract_memories(
            "\n".join(
                [
                    "Decision: Keep retries in the transport adapter.",
                    "Preference: Error messages name the upstream service.",
                    "Must: Never retry POST requests unless callers opt in.",
                    "Short note",
                ]
            ),
            skill="grill-with-docs",
            task="Review retry policy",
            paths=["src/api/client.ts"],
            source="session.md",
        )

        self.assertEqual(
            [memory.memory_type for memory in memories],
            ["decision", "preference", "instruction"],
        )
        self.assertTrue(all(memory.skill == "grill-with-docs" for memory in memories))
        self.assertEqual(memories[0].paths, ["src/api/client.ts"])

    def test_preview_after_before_round_trip_writes_relevant_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="memanto-preview-test-") as tmp:
            workdir = Path(tmp)
            transcript = workdir / "session.md"
            transcript.write_text(
                "\n".join(
                    [
                        "Decision: Keep retries in the transport adapter.",
                        "Preference: Error messages name the upstream service.",
                        "Must: Do not retry POST requests unless the caller opts in.",
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.object(skill_memory, "STATE_DIR", workdir / ".memanto-skill-memory"), \
                mock.patch.object(skill_memory, "MEMORY_FILE", workdir / ".memanto-skill-memory" / "memories.jsonl"), \
                mock.patch.object(skill_memory, "INJECTION_FILE", workdir / ".memanto-skill-memory" / "injected-context.md"):
                after_code = skill_memory.command_after(
                    Namespace(
                        skill="grill-with-docs",
                        task="Review API client retry strategy",
                        paths=["src/api/client.ts"],
                        transcript=str(transcript),
                        agent="test-agent",
                    )
                )
                before_code = skill_memory.command_before(
                    Namespace(
                        task="Implement API client retry handling",
                        paths=["src/api/client.ts"],
                        agent="test-agent",
                    )
                )

                context = (workdir / ".memanto-skill-memory" / "injected-context.md").read_text(
                    encoding="utf-8"
                )

        self.assertEqual(after_code, 0)
        self.assertEqual(before_code, 0)
        self.assertIn("mode: preview", context)
        self.assertIn("[decision]", context)
        self.assertIn("[preference]", context)
        self.assertIn("[instruction]", context)
        self.assertIn("transport adapter", context)

    def test_missing_transcript_returns_usage_error(self) -> None:
        with tempfile.TemporaryDirectory(prefix="memanto-preview-test-") as tmp:
            result = skill_memory.command_after(
                Namespace(
                    skill="handoff",
                    task="Summarize constraints",
                    paths=[],
                    transcript=str(Path(tmp) / "missing.md"),
                    agent="test-agent",
                )
            )

        self.assertEqual(result, 2)

    def test_mattpocock_adapter_generates_memory_wrappers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="memanto-adapter-test-") as tmp:
            output = Path(tmp) / "commands"
            written = mattpocock_adapter.write_wrappers(
                output,
                {
                    "tdd": {
                        "source": "/tdd",
                        "purpose": "test-drive one implementation slice",
                        "paths": "src tests",
                    }
                },
            )

            wrapper = written[0].read_text(encoding="utf-8")

        self.assertEqual(len(written), 1)
        self.assertIn("skill_memory.py before", wrapper)
        self.assertIn("skill_memory.py after", wrapper)
        self.assertIn("/tdd", wrapper)


if __name__ == "__main__":
    unittest.main()
