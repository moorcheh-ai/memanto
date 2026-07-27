from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[2]
for path in (ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from migrate_mcp_memory import MigrationError, load_mcp_graph, migrate  # noqa: E402
from reconstruct_mcp_memory import reconstructed_jsonl  # noqa: E402
from run_live_demo import (  # noqa: E402
    build_commands,
    display_argv,
    staging_export_path,
)

from memanto.cli.migrate.mappers import map_okf  # noqa: E402
from memanto.cli.migrate.okf_loader import load_okf_bundle  # noqa: E402


def _line(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


class McpMemoryMigrationTests(unittest.TestCase):
    def _source(self, directory: Path, records: list[dict]) -> Path:
        source = directory / "memory.jsonl"
        source.write_text(
            "\n".join(_line(record) for record in records), encoding="utf-8"
        )
        return source

    def test_bundle_is_consumable_and_lossless(self) -> None:
        records = [
            {
                "type": "entity",
                "name": "Project Atlas",
                "entityType": "project",
                "observations": ["Uses PostgreSQL 16.", "Ships in Singapore."],
            },
            {
                "type": "entity",
                "name": "PostgreSQL",
                "entityType": "tool",
                "observations": ["Production database."],
            },
            {
                "type": "relation",
                "from": "Project Atlas",
                "to": "PostgreSQL",
                "relationType": "uses",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root, records)
            output = root / "okf"
            report = migrate(source, output)

            self.assertEqual(report["mapped_okf_memories"], 2)
            savings = json.loads(
                (output / "metrics" / "savings-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(savings["applicability"], "not_applicable")
            self.assertIsNone(savings["claims"]["cost_savings"])
            self.assertEqual(
                savings["measured_storage"]["source_jsonl_bytes"],
                len(source.read_bytes()),
            )
            self.assertGreater(
                savings["measured_storage"]["importable_okf_bytes"],
                savings["measured_storage"]["source_jsonl_bytes"],
            )
            rows = map_okf(load_okf_bundle(output))
            self.assertEqual(len(rows), 2)
            atlas = next(row for row in rows if row["title"] == "Project Atlas")
            self.assertIn("Uses PostgreSQL 16.", atlas["content"])
            self.assertIn("uses", atlas["content"])
            self.assertEqual(atlas["type"], "artifact")
            self.assertEqual(atlas["source"], "mcp-memory-server")
            self.assertEqual(
                reconstructed_jsonl(output).decode("utf-8"),
                source.read_text(encoding="utf-8"),
            )

    def test_slug_collisions_remain_unique(self) -> None:
        records = [
            {
                "type": "entity",
                "name": "A/B",
                "entityType": "item",
                "observations": [],
            },
            {
                "type": "entity",
                "name": "A B",
                "entityType": "item",
                "observations": [],
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "okf"
            migrate(self._source(root, records), output)
            docs = list((output / "memories" / "entities").glob("*.md"))
            self.assertEqual(len(docs), 2)
            self.assertEqual(len({doc.name for doc in docs}), 2)

    def test_source_blocks_handle_embedded_markdown_fences(self) -> None:
        records = [
            {
                "type": "entity",
                "name": "Fence-safe",
                "entityType": "learning",
                "observations": [
                    "The source includes ```python and ```` longer fences."
                ],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root, records)
            output = root / "okf"
            migrate(source, output)
            self.assertEqual(
                reconstructed_jsonl(output).decode("utf-8"),
                source.read_text(encoding="utf-8"),
            )

    def test_dangling_relation_fails_closed(self) -> None:
        records = [
            {
                "type": "entity",
                "name": "Known",
                "entityType": "item",
                "observations": [],
            },
            {
                "type": "relation",
                "from": "Known",
                "to": "Missing",
                "relationType": "references",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp), records)
            with self.assertRaisesRegex(MigrationError, "missing entities"):
                load_mcp_graph(source)

    def test_invalid_utf8_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "memory.jsonl"
            source.write_bytes(b"\xff")
            with self.assertRaisesRegex(MigrationError, "UTF-8"):
                load_mcp_graph(source)

    def test_output_is_deterministic(self) -> None:
        records = [
            {
                "type": "entity",
                "name": "Deterministic",
                "entityType": "test",
                "observations": ["Same input, same output."],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root, records)
            first = root / "one"
            second = root / "two"
            migrate(source, first)
            migrate(source, second)
            first_files = {
                file.relative_to(first): file.read_bytes()
                for file in first.rglob("*")
                if file.is_file()
            }
            second_files = {
                file.relative_to(second): file.read_bytes()
                for file in second.rglob("*")
                if file.is_file()
            }
            self.assertEqual(first_files, second_files)

    def test_live_demo_command_plan_covers_full_freedom_loop(self) -> None:
        questions = ["Where is the graph?", "How is it portable?"]
        commands = build_commands(
            Path("/venv/bin/memanto"),
            agent="mcp-demo",
            okf_path=Path("/input/okf"),
            export_path=Path("/evidence/exported-okf"),
            questions=questions,
            reuse_agent=False,
            include_answers=True,
        )
        labels = [command.label for command in commands]
        self.assertEqual(
            labels,
            [
                "create-agent",
                "import-okf",
                "activate-agent",
                "recall-1",
                "answer-1",
                "recall-2",
                "answer-2",
                "export-okf",
            ],
        )
        self.assertIn("--agent", commands[1].argv)
        self.assertIn("--okf", commands[-1].argv)

        reused = build_commands(
            Path("/venv/bin/memanto"),
            agent="mcp-demo",
            okf_path=Path("/input/okf"),
            export_path=Path("/evidence/exported-okf"),
            questions=questions,
            reuse_agent=True,
            include_answers=False,
        )
        self.assertNotIn("create-agent", [command.label for command in reused])
        self.assertNotIn("answer-1", [command.label for command in reused])

    def test_live_export_is_staged_inside_memanto_data_dir(self) -> None:
        data_dir = Path("/home/demo/.memanto")
        first = staging_export_path(
            "mcp-demo", Path("/external/evidence-one"), data_dir
        )
        second = staging_export_path(
            "mcp-demo", Path("/external/evidence-two"), data_dir
        )
        self.assertEqual(first.parent, data_dir / "exports")
        self.assertNotEqual(first, second)
        self.assertTrue(first.name.startswith("mcp-demo_live_"))

    def test_live_command_display_redacts_home_paths(self) -> None:
        executable = Path.home() / "project" / ".venv" / "bin" / "memanto"
        staged = Path.home() / ".memanto" / "exports" / "mcp-demo_okf"
        display = display_argv((str(executable), "--output", str(staged)))
        self.assertEqual(
            display,
            "memanto --output '~/.memanto/exports/mcp-demo_okf'",
        )
        self.assertNotIn(str(Path.home()), display)


if __name__ == "__main__":
    unittest.main()
