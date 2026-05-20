import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skill_memanto_bridge import (
    BridgeConfig,
    LiveMemantoBackend,
    LocalJsonlBackend,
    MemoryBridge,
    build_backend,
)
from skill_memanto_bridge.wrappers import generate_wrappers


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


class BridgeTests(unittest.TestCase):
    def test_local_backend_persists_and_recalls_relevant_memories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Path(temp_dir) / "memories.jsonl"
            backend = LocalJsonlBackend(store)

            backend.remember(
                title="Use repository adapters",
                content="For billing work, keep database access behind repository adapters.",
                memory_type="decision",
                tags=["billing", "architecture"],
                source="unit-test",
                metadata={"path": "services/billing"},
            )
            backend.remember(
                title="Prefer Playwright",
                content="For browser flows, prefer Playwright screenshots over manual inspection.",
                memory_type="preference",
                tags=["frontend"],
                source="unit-test",
                metadata={"path": "web"},
            )

            recalled = backend.recall("billing repository architecture", limit=3)

            self.assertEqual(recalled[0]["title"], "Use repository adapters")
            self.assertGreater(recalled[0]["score"], 0)
            self.assertEqual(len(read_jsonl(store)), 2)

    def test_pre_run_injection_is_concise_and_task_specific(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = BridgeConfig(
                store_path=Path(temp_dir) / "memories.jsonl",
                max_injected=2,
            )
            bridge = MemoryBridge(config=config)
            bridge.backend.remember(
                title="Keep auth narrow",
                content="When touching auth, keep changes inside the existing middleware.",
                memory_type="decision",
                tags=["auth", "middleware"],
                source="unit-test",
                metadata={"skill": "grill-with-docs", "path": "server/auth.py"},
            )

            injection = bridge.pre_run(
                skill="tdd",
                task="Add a login middleware regression test",
                path="server/auth.py",
            )

            self.assertIn("Memanto memory context", injection)
            self.assertIn("Keep auth narrow", injection)
            self.assertIn("existing middleware", injection)
            self.assertNotIn("No relevant", injection)

    def test_post_run_extracts_active_engineering_memories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = BridgeConfig(store_path=Path(temp_dir) / "memories.jsonl")
            bridge = MemoryBridge(config=config)

            saved = bridge.post_run(
                skill="grill-with-docs",
                task="Plan payment webhook handling",
                transcript="""
                We decided to keep webhook verification in app/security.py.
                Preference: use stdlib hmac before adding dependencies.
                Avoid storing provider secrets in logs.
                This is just conversational filler and should not become memory.
                """,
                path="payments/webhooks.py",
            )

            contents = [item["content"] for item in saved]
            self.assertTrue(any("webhook verification" in item for item in contents))
            self.assertTrue(any("stdlib hmac" in item for item in contents))
            self.assertTrue(any("provider secrets" in item for item in contents))
            self.assertEqual(len(read_jsonl(config.store_path)), 3)

    def test_build_backend_uses_live_only_when_requested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.dict(
                os.environ,
                {
                    "SKILL_MEMANTO_BACKEND": "local",
                    "SKILL_MEMANTO_STORE": str(Path(temp_dir) / "local.jsonl"),
                },
                clear=False,
            ):
                backend = build_backend()

            self.assertIsInstance(backend, LocalJsonlBackend)

    def test_live_backend_delegates_to_sdk_client_shape(self):
        class FakeClient:
            def __init__(self, api_key: str):
                self.api_key = api_key
                self.remember_calls = []

            def remember(self, **kwargs):
                self.remember_calls.append(kwargs)
                return {"memory_id": "mem-1", "status": "stored"}

            def recall(self, **kwargs):
                return {
                    "memories": [
                        {
                            "title": "Use adapters",
                            "content": "Keep storage behind adapters.",
                            "type": "decision",
                            "tags": ["developer-skill-memory"],
                            "confidence": 0.9,
                        }
                    ]
                }

        backend = LiveMemantoBackend(
            api_key="test-key",
            agent_id="developer-skills",
            client_factory=FakeClient,
        )

        stored = backend.remember(
            title="Use adapters",
            content="Keep storage behind adapters.",
            memory_type="decision",
            tags=["architecture"],
            source="unit-test",
            metadata={"path": "storage.py"},
        )
        recalled = backend.recall("storage adapters", limit=1)

        self.assertEqual(stored["status"], "stored")
        self.assertEqual(recalled[0]["memory_type"], "decision")
        self.assertIn("developer-skill-memory", backend.client.remember_calls[0]["tags"])

    def test_generate_wrappers_writes_shell_and_powershell_launchers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "wrappers"

            generated = generate_wrappers(
                output_dir=output_dir,
                commands=["tdd", "grill-with-docs"],
                runner="python -m skill_memanto_bridge.cli",
            )

            names = {path.name for path in generated}
            self.assertIn("tdd", names)
            self.assertIn("tdd.ps1", names)
            self.assertIn("grill-with-docs", names)
            self.assertIn("grill-with-docs.ps1", names)

            shell_wrapper = output_dir / "tdd"
            ps_wrapper = output_dir / "tdd.ps1"
            self.assertIn("pre-run --skill tdd", shell_wrapper.read_text())
            self.assertIn("post-run --skill tdd", shell_wrapper.read_text())
            self.assertIn("pre-run --skill tdd", ps_wrapper.read_text())
            self.assertTrue(
                os.access(shell_wrapper, os.X_OK)
                or (shell_wrapper.stat().st_mode & stat.S_IXUSR)
            )


if __name__ == "__main__":
    unittest.main()
