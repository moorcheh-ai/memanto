import tempfile
import unittest
from pathlib import Path

from bridge import (
    LocalJsonBackend,
    distill_transcript,
    render_context,
)
from productivity_check import EXPECTED_CONTEXT, run_productivity_check
from skills_manifest import load_skill_entries, parse_frontmatter, render_markdown


class BridgeTest(unittest.TestCase):
    def test_distill_transcript_extracts_typed_memories(self) -> None:
        transcript = """Decision: Use Postgres for project state.
Constraint: Preserve response fields.
Preference: Avoid new runtime frameworks.
$ pytest tests/test_api.py
"""

        memories = distill_transcript(
            transcript,
            skill="tdd",
            task="add pagination tests",
            paths=["tests/test_api.py"],
        )

        memory_types = {memory.memory_type for memory in memories}
        self.assertIn("decision", memory_types)
        self.assertIn("instruction", memory_types)
        self.assertIn("preference", memory_types)
        self.assertIn("learning", memory_types)
        self.assertTrue(
            any("pytest tests/test_api.py" in memory.content for memory in memories)
        )

    def test_local_backend_recalls_relevant_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = Path(tmpdir) / "memory.json"
            backend = LocalJsonBackend(store)
            memories = distill_transcript(
                "Decision: Use Postgres for project state.",
                skill="grill-with-docs",
                task="review database docs",
                paths=["docs/database.md"],
            )
            for memory in memories:
                backend.remember(memory)

            recalled = backend.recall("database docs postgres", limit=3)

            self.assertTrue(recalled)
            self.assertIn("Postgres", recalled[0].content)

    def test_render_context_is_copy_pasteable(self) -> None:
        memories = distill_transcript(
            "Constraint: Keep handlers backwards compatible.",
            skill="handoff",
            task="prepare route handoff",
            paths=["memanto/app/routes/memory.py"],
        )

        output = render_context(memories, "prepare route handoff")

        self.assertIn("Memanto context for this skill run", output)
        self.assertIn("backwards compatible", output)
        self.assertIn("prepare route handoff", output)

    def test_manifest_reader_matches_matt_pocock_plugin_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plugin_dir = root / ".claude-plugin"
            skill_dir = root / "skills" / "engineering" / "tdd"
            plugin_dir.mkdir()
            skill_dir.mkdir(parents=True)
            (plugin_dir / "plugin.json").write_text(
                '{"name":"demo","skills":["./skills/engineering/tdd"]}',
                encoding="utf-8",
            )
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: tdd\n"
                "description: Test-driven development loop.\n"
                "---\n\n"
                "# TDD\n",
                encoding="utf-8",
            )

            entries = load_skill_entries(root)
            markdown = render_markdown(entries)

            self.assertEqual(entries[0].name, "tdd")
            self.assertIn("Test-driven development loop", entries[0].description)
            self.assertIn("skills/engineering/tdd", markdown)

    def test_parse_frontmatter_without_metadata_is_empty(self) -> None:
        self.assertEqual(parse_frontmatter("# No metadata\n"), {})

    def test_productivity_check_recovers_expected_context(self) -> None:
        exit_code, report = run_productivity_check()

        self.assertEqual(exit_code, 0)
        self.assertIn(
            f"Repeated instructions avoided: {len(EXPECTED_CONTEXT)} / {len(EXPECTED_CONTEXT)}",
            report,
        )
        self.assertIn("Rendered context block", report)


if __name__ == "__main__":
    unittest.main()
