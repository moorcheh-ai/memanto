import json
import os
import tempfile
import unittest
from pathlib import Path

from memanto_skill_memory.backends import LocalJsonlBackend
from memanto_skill_memory.distill import HeuristicSkillDistiller
from memanto_skill_memory.hook import SkillMemoryBridge
from memanto_skill_memory.mattpocock_adapter import build_wrapper_script
from memanto_skill_memory.models import SkillEvent
from memanto_skill_memory.redaction import redact_secrets


class SecretRedactionTests(unittest.TestCase):
    def test_redacts_common_secret_shapes_before_storage(self):
        raw = """
        export MOORCHEH_API_KEY=mc_live_1234567890abcdef
        Authorization: Bearer ghp_1234567890abcdefghijklmnop
        OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz
        password = "correct horse battery staple"
        """

        redacted = redact_secrets(raw)

        self.assertIn("MOORCHEH_API_KEY=<redacted>", redacted)
        self.assertIn("Authorization: Bearer <redacted>", redacted)
        self.assertIn("OPENAI_API_KEY=<redacted>", redacted)
        self.assertIn('password = "<redacted>"', redacted)
        self.assertNotIn("mc_live_1234567890abcdef", redacted)
        self.assertNotIn("ghp_1234567890abcdefghijklmnop", redacted)
        self.assertNotIn("sk-proj-abcdefghijklmnopqrstuvwxyz", redacted)


class DistillerTests(unittest.TestCase):
    def test_extracts_engineering_decisions_preferences_and_instructions(self):
        event = SkillEvent(
            skill_name="tdd",
            prompt="Add pagination to the issue list",
            transcript="""
            Decision: keep pagination state in the URL so reloads preserve filters.
            Preference: use repository helpers instead of calling fetch in components.
            Must not add a second client-side cache for issue data.
            We learned the existing API caps page size at 100.
            """,
            cwd="/repo",
        )

        memories = HeuristicSkillDistiller().distill(event)

        stored = {(memory.memory_type, memory.title) for memory in memories}
        self.assertIn(("decision", "Keep pagination state in the URL"), stored)
        self.assertIn(("preference", "Use repository helpers"), stored)
        self.assertIn(
            ("instruction", "Must not add a second client-side cache"), stored
        )
        self.assertIn(("learning", "Existing API caps page size at 100"), stored)


class LocalBackendTests(unittest.TestCase):
    def test_persists_and_recalls_relevant_memories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "memories.jsonl"
            backend = LocalJsonlBackend(path)
            event = SkillEvent(
                skill_name="handoff",
                prompt="Summarize architecture work",
                transcript="Decision: API clients must live in src/services.",
                cwd="/repo",
            )
            memories = HeuristicSkillDistiller().distill(event)

            backend.remember(memories, event)
            recalled = backend.recall("Where do API clients live?", limit=3)

            self.assertEqual(len(recalled), 1)
            self.assertEqual(recalled[0].memory.memory_type, "decision")
            self.assertIn("src/services", recalled[0].memory.content)

            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(records[0]["event"]["skill_name"], "handoff")
            self.assertEqual(records[0]["memory"]["tags"], ["handoff", "project:/repo"])


class HookLifecycleTests(unittest.TestCase):
    def test_post_then_pre_injects_context_across_separate_skill_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalJsonlBackend(Path(tmpdir) / "memories.jsonl")
            bridge = SkillMemoryBridge(backend=backend)

            first_run = SkillEvent(
                skill_name="grill-with-docs",
                prompt="Review auth architecture",
                transcript="Decision: use signed short-lived session cookies for auth.",
                cwd="/repo",
            )
            bridge.after_skill(first_run)

            second_run = SkillEvent(
                skill_name="tdd",
                prompt="Add tests for auth session renewal",
                transcript="",
                cwd="/repo",
            )
            context = bridge.before_skill(second_run, limit=5)

            self.assertIn("Memanto engineering memory", context)
            self.assertIn("signed short-lived session cookies", context)
            self.assertIn("Source: grill-with-docs", context)
            self.assertEqual(os.environ["MEMANTO_SKILL_CONTEXT"], context)


class MattPocockAdapterTests(unittest.TestCase):
    def test_wrapper_script_runs_command_through_memory_bridge(self):
        script = build_wrapper_script(
            wrapper_name="memanto-tdd",
            skill_name="tdd",
            command=["claude", "/tdd"],
        )

        self.assertIn("memanto-skill-memory wrap", script)
        self.assertIn("--skill tdd", script)
        self.assertIn('exec claude "/tdd" "$@"', script)
        self.assertIn("MEMANTO_SKILL_BACKEND", script)


if __name__ == "__main__":
    unittest.main()
