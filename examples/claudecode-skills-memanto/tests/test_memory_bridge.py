from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "memanto_skill_memory.py"
)
INSTALL_PATH = Path(__file__).resolve().parents[1] / "install.py"


def load_module(name: str, path: Path):
    """Import a Python file by path so tests work without package installation."""

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bridge = load_module("memanto_skill_memory", MODULE_PATH)
installer = load_module("memanto_install", INSTALL_PATH)


class MemantoSkillsBridgeTest(unittest.TestCase):
    """Integration-style tests for the credential-free bridge workflow."""

    def test_local_backend_stores_and_recalls_relevant_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend = bridge.LocalJsonMemoryBackend(Path(tmp) / "memories.jsonl")
            memory = bridge.MemoryCandidate(
                type="instruction",
                content=(
                    "Always test billing webhooks through the public FastAPI route, "
                    "never by calling private helpers directly."
                ),
                tags=["billing", "tdd"],
            )

            self.assertTrue(backend.remember("agent", memory))
            self.assertFalse(backend.remember("agent", memory))

            hits = backend.recall("agent", "billing webhook public route tests")
            self.assertEqual(1, len(hits))
            self.assertEqual("instruction", hits[0].type)

    def test_prompt_hook_injects_skill_specific_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            state_dir = cwd / ".claude" / "memanto-skills-state"
            backend = bridge.LocalJsonMemoryBackend(state_dir / "memories.jsonl")
            backend.remember(
                bridge._agent_id(cwd),
                bridge.MemoryCandidate(
                    type="decision",
                    content="We decided billing webhook tests use the public FastAPI route.",
                    tags=["billing", "tdd"],
                ),
            )
            event = {
                "session_id": "s1",
                "cwd": str(cwd),
                "hook_event_name": "UserPromptSubmit",
                "prompt": "/tdd implement billing webhook tests",
            }

            result = bridge.handle_user_prompt_submit(event)
            context = result["hookSpecificOutput"]["additionalContext"]

            self.assertIn("/tdd", context)
            self.assertIn("public FastAPI route", context)

    def test_stop_hook_extracts_decision_and_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            state = bridge.HookState(cwd / ".claude" / "memanto-skills-state", "s2")
            state.update(
                prompt=(
                    "/grill-with-docs We will use FastAPI dependency injection "
                    "for signature verification."
                ),
                skill="grill-with-docs",
            )
            state.append(
                "tools",
                {
                    "kind": "file-change",
                    "files": ["CONTEXT.md", "docs/adr/billing.md"],
                    "summary": "Write | files=CONTEXT.md,docs/adr/billing.md",
                },
            )
            event = {
                "session_id": "s2",
                "cwd": str(cwd),
                "hook_event_name": "Stop",
                "last_assistant_message": (
                    "Decided to keep verification behind FastAPI dependency injection."
                ),
            }

            result = bridge.handle_stop(event)
            self.assertTrue(result["suppressOutput"])
            self.assertGreaterEqual(state.read()["stored_memories"], 2)

            backend = bridge.LocalJsonMemoryBackend(
                cwd / ".claude" / "memanto-skills-state" / "memories.jsonl"
            )
            hits = backend.recall(
                bridge._agent_id(cwd),
                "FastAPI signature verification ADR files",
            )
            contents = "\n".join(hit.content for hit in hits)
            self.assertIn("FastAPI", contents)
            self.assertIn("CONTEXT.md", contents)

    def test_installer_merges_hooks_idempotently(self) -> None:
        addition = installer.build_hook_settings()
        once = installer.merge_settings({}, addition)
        twice = installer.merge_settings(once, addition)

        self.assertEqual(once, twice)
        self.assertIn("UserPromptSubmit", twice["hooks"])
        self.assertIn("Stop", twice["hooks"])

        rendered = json.dumps(twice)
        self.assertIn("memanto_skill_memory.py", rendered)

    def test_installer_preserves_distinct_matchers(self) -> None:
        existing = installer.build_hook_settings()
        changed = installer.build_hook_settings()
        changed["hooks"]["PostToolUse"][0]["matcher"] = "Bash"

        merged = installer.merge_settings(existing, changed)

        self.assertEqual(2, len(merged["hooks"]["PostToolUse"]))

    def test_error_text_is_redacted_before_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            event = {
                "session_id": "s3",
                "cwd": tmp,
                "error": "failed with token=abc123 and ghp_abcdefghijklmnopqrstuvwxyz",
            }

            bridge.handle_post_tool_use_failure(event)

            backend = bridge.LocalJsonMemoryBackend(
                Path(tmp) / ".claude" / "memanto-skills-state" / "memories.jsonl"
            )
            hits = backend.recall(bridge._agent_id(Path(tmp)), "tool failure")
            content = "\n".join(hit.content for hit in hits)
            self.assertIn("token=[redacted]", content)
            self.assertIn("gh_[redacted]", content)
            self.assertNotIn("ghp_abcdefghijklmnopqrstuvwxyz", content)


if __name__ == "__main__":
    unittest.main()
