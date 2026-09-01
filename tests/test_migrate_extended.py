"""
Unit tests for extended migration mappers and CLI commands (OKF, LangChain, Generic).
"""

import json
from unittest.mock import patch

from typer.testing import CliRunner

from memanto.cli.main import app
from memanto.cli.migrate.mappers import map_generic, map_langchain, map_okf
from memanto.cli.migrate.runner import load_export, run_migration, source_count

runner = CliRunner()


class TestExtendedMappers:
    def test_map_okf_structured_markdown(self):
        sample_okf = """# Memory — agent-007

> Generated: 2026-08-30 10:00:00
> Total memories: **3**

---

## Instructions

*Standing rules and guidelines to always follow.*

### Use TypeScript Strict Mode
Always enable strict mode in tsconfig.json across all backend packages.
*Confidence: 0.95 | Status: active | Created: 2026-08-01 12:00:00 | Tags: `typescript`, `strict`, `coding-standards`*

---

## Facts

*Verified information, project status, and established truths.*

### Production Database Host
The primary database is hosted on AWS RDS PostgreSQL 16 in us-east-1.
*Confidence: 0.9 | Status: active | Created: 2026-08-02 08:30:00 | Tags: `database`, `infra`*

---

## Decisions

*Architectural choices and rationale.*

### Adopted UV Package Manager
We migrated all Python dependency management to uv for 10x faster installations.

---
*End of memory export.*
"""
        rows = map_okf({"content": sample_okf})

        assert len(rows) == 3

        # Instruction row
        r0 = rows[0]
        assert r0["title"] == "Use TypeScript Strict Mode"
        assert "Always enable strict mode" in r0["content"]
        assert r0["type"] == "instruction"
        assert r0["confidence"] == 0.95
        assert "typescript" in r0["tags"]
        assert "strict" in r0["tags"]
        assert r0["source"] == "okf"
        assert r0["provenance"] == "imported"

        # Fact row
        r1 = rows[1]
        assert r1["title"] == "Production Database Host"
        assert "AWS RDS PostgreSQL" in r1["content"]
        assert r1["type"] == "fact"
        assert r1["confidence"] == 0.9
        assert "database" in r1["tags"]

        # Decision row
        r2 = rows[2]
        assert r2["title"] == "Adopted UV Package Manager"
        assert "migrated all Python dependency management to uv" in r2["content"]
        assert r2["type"] == "decision"
        assert r2["confidence"] == 0.9

    def test_map_okf_empty_sections(self):
        sample_okf = """# Memory — empty-agent
## Facts
*No memories of this type.*
---
## Goals
*No memories of this type.*
---
"""
        rows = map_okf({"content": sample_okf})
        assert len(rows) == 0

    def test_map_langchain_full(self):
        export = {
            "summary": "User discussed building an autonomous trading bot using FastAPI.",
            "entities": {
                "FastAPI": "High-performance Python web framework",
                "Binance": "Cryptocurrency exchange API target",
            },
            "messages": [
                {
                    "type": "human",
                    "content": "Always validate API signatures before placing trades.",
                    "created_at": "2026-07-10T14:00:00Z",
                },
                {
                    "type": "ai",
                    "content": "Understood. I will implement HMAC-SHA256 signature verification.",
                    "created_at": "2026-07-10T14:00:05Z",
                },
            ],
        }

        rows = map_langchain(export)
        assert len(rows) == 5

        summary_row = next(r for r in rows if r["type"] == "context" and "summary" in r["tags"])
        assert "FastAPI" in summary_row["content"]

        entity_rows = [r for r in rows if r["type"] == "fact"]
        assert len(entity_rows) == 2
        assert any("FastAPI" in r["title"] for r in entity_rows)

        instruction_row = next(r for r in rows if r["type"] == "instruction")
        assert "API signatures" in instruction_row["content"]

    def test_map_generic_jsonl(self):
        export = {
            "memories": [
                {
                    "id": "gen-1",
                    "title": "Config Setting",
                    "content": "Set MAX_CONCURRENCY=50 for the worker pool.",
                    "type": "instruction",
                    "tags": ["config", "worker"],
                    "confidence": 0.99,
                },
                {
                    "text": "User prefers dark mode UI.",
                    "type": "preference",
                },
            ]
        }

        rows = map_generic(export)
        assert len(rows) == 2
        assert rows[0]["title"] == "Config Setting"
        assert rows[0]["type"] == "instruction"
        assert rows[0]["confidence"] == 0.99
        assert rows[1]["type"] == "preference"


class TestExtendedMigrationRunner:
    def test_load_export_markdown(self, tmp_path):
        md_file = tmp_path / "test_memory.md"
        md_file.write_text("## Facts\n### Fact 1\nContent 1\n", encoding="utf-8")

        loaded = load_export(md_file)
        assert loaded["format"] == "okf"
        assert "### Fact 1" in loaded["content"]

    def test_load_export_jsonl(self, tmp_path):
        jsonl_file = tmp_path / "memories.jsonl"
        lines = [
            json.dumps({"content": "Memory 1", "type": "fact"}),
            json.dumps({"content": "Memory 2", "type": "goal"}),
        ]
        jsonl_file.write_text("\n".join(lines), encoding="utf-8")

        loaded = load_export(jsonl_file)
        assert loaded["format"] == "jsonl"
        assert len(loaded["memories"]) == 2

    def test_source_count_okf(self):
        export = {"content": "### Mem 1\nText\n### Mem 2\nText 2\n"}
        assert source_count("okf", export) == 2

    def test_run_migration_dry_run_okf(self):
        export = {
            "content": """## Instructions
### Rule 1
Follow clean code standards.
*Confidence: 1.0 | Tags: `clean-code`*
"""
        }
        summary, rows = run_migration(
            provider="okf",
            export=export,
            client=None,
            agent_id="test-agent",
            dry_run=True,
        )
        assert summary.mapped_count == 1
        assert summary.source_count == 1
        assert rows[0]["title"] == "Rule 1"
        assert rows[0]["type"] == "instruction"


class TestExtendedMigrateCLI:
    def test_migrate_okf_cli_dry_run(self, tmp_path):
        okf_file = tmp_path / "memory.md"
        okf_file.write_text(
            """# Memory — test-agent
## Facts
### Server Port
App listens on port 8000.
*Confidence: 0.9 | Tags: `network`*
---
""",
            encoding="utf-8",
        )

        with patch("memanto.cli.commands.migrate.config_manager") as mock_cfg:
            mock_cfg.get_migrate_dir.return_value = tmp_path
            mock_cfg.get_active_session.return_value = ("test-agent", "token-123")

            result = runner.invoke(
                app,
                ["migrate", "okf", "--file", str(okf_file), "--dry-run"],
            )

        assert result.exit_code == 0, result.stdout
        assert "Dry run complete" in result.stdout
        assert "Facts" in result.stdout or "fact: 1" in result.stdout

    def test_migrate_langchain_cli_dry_run(self, tmp_path):
        lc_file = tmp_path / "langchain_export.json"
        lc_file.write_text(
            json.dumps(
                {
                    "summary": "Project is migrating to Memanto.",
                    "messages": [{"type": "human", "content": "Hello bot!"}],
                }
            ),
            encoding="utf-8",
        )

        with patch("memanto.cli.commands.migrate.config_manager") as mock_cfg:
            mock_cfg.get_migrate_dir.return_value = tmp_path
            mock_cfg.get_active_session.return_value = ("test-agent", "token-123")

            result = runner.invoke(
                app,
                ["migrate", "langchain", "--file", str(lc_file), "--dry-run"],
            )

        assert result.exit_code == 0, result.stdout
        assert "Dry run complete" in result.stdout

    def test_migrate_generic_cli_dry_run(self, tmp_path):
        gen_file = tmp_path / "memories.json"
        gen_file.write_text(
            json.dumps({"memories": [{"content": "Custom fact entry", "type": "fact"}]}),
            encoding="utf-8",
        )

        with patch("memanto.cli.commands.migrate.config_manager") as mock_cfg:
            mock_cfg.get_migrate_dir.return_value = tmp_path
            mock_cfg.get_active_session.return_value = ("test-agent", "token-123")

            result = runner.invoke(
                app,
                ["migrate", "generic", "--file", str(gen_file), "--dry-run"],
            )

        assert result.exit_code == 0, result.stdout
        assert "Dry run complete" in result.stdout


    def test_parse_dt_boolean_rejected(self):
        from memanto.cli.migrate.mappers import _parse_dt
        assert _parse_dt(True) is None
        assert _parse_dt(False) is None
        assert _parse_dt(1700000000) is not None

    def test_map_okf_single_field_metadata(self):
        sample_okf = """## Instructions
### Single Field Rule
Always sanitize untrusted user input.
*Confidence: 0.95*
---
"""
        rows = map_okf({"content": sample_okf})
        assert len(rows) == 1
        assert rows[0]["confidence"] == 0.95
        assert "*Confidence:" not in rows[0]["content"]

    def test_map_langchain_content_blocks(self):
        export = {
            "messages": [
                {
                    "type": "human",
                    "content": [{"type": "text", "text": "Deploy to production cluster"}]
                }
            ]
        }
        rows = map_langchain(export)
        assert len(rows) == 1
        assert "Deploy to production cluster" in rows[0]["content"]

    def test_map_generic_coercion(self):
        export = {
            "memories": [
                {
                    "title": 12345,
                    "content": ["Block 1", "Block 2"],
                    "created_at": True
                }
            ]
        }
        rows = map_generic(export)
        assert len(rows) == 1
        assert rows[0]["title"] == "12345"
        assert "Block 1 Block 2" in rows[0]["content"]
        assert rows[0]["created_at"] is None

    def test_load_export_jsonl_unparsed_lines(self, tmp_path):
        jsonl_file = tmp_path / "test.jsonl"
        jsonl_file.write_text('{"text": "valid"}\nBAD_JSON_LINE\n{"text": "valid 2"}\n', encoding="utf-8")
        result = load_export(jsonl_file)
        assert len(result["memories"]) == 2
        assert result["unparsed_lines"] == [2]
