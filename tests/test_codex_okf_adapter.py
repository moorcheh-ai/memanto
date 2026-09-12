"""Coverage for the Codex memory -> OKF migration example."""

import importlib.util
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

_EXAMPLE_DIR = Path(__file__).parent.parent / "examples" / "migrations" / "codex"
_MODULE_PATH = _EXAMPLE_DIR / "codex_to_okf.py"
_RECALL_VALIDATOR_PATH = _EXAMPLE_DIR / "validation" / "validate_recall.py"


def _load_example_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load example module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load_example_module("codex_to_okf", _MODULE_PATH)
recall_validator = _load_example_module("validate_codex_recall", _RECALL_VALIDATOR_PATH)


RAW_MEMORY = """\
---
description: "Two durable lessons from a real Codex rollout"
task: "Review and repair the authentication workflow"
task_group: "/Users/demo/work/atlas"
task_outcome: success
cwd: "/Users/demo/work/atlas"
keywords: auth, pytest, review-workflow
---

### Task 1: Preserve the user's review-first workflow

task: review workflow
task_group: atlas
task_outcome: success

Preference signals:
- after a test failed, the user asked "show me the failure before editing" -> inspect and explain failures before changing code.

References:
- `uv run pytest tests/test_auth.py`

### Task 2: Repair stale authentication propagation

task: fix auth propagation
task_group: atlas
task_outcome: success

Reusable knowledge:
- `refresh_auth()` must update both the process environment and the child command context.
- The test account used API_KEY=super-secret-value-123456789.

Failures and how to do differently:
- Updating only the process environment left spawned commands stale; update both stores.

References:
- `/Users/demo/work/atlas/tests/test_auth.py`
"""


def _create_memory_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE stage1_outputs (
            thread_id TEXT PRIMARY KEY,
            source_updated_at INTEGER NOT NULL,
            raw_memory TEXT NOT NULL,
            rollout_summary TEXT NOT NULL,
            rollout_slug TEXT,
            generated_at INTEGER NOT NULL,
            usage_count INTEGER,
            last_usage INTEGER,
            selected_for_phase2 INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    connection.execute(
        """
        INSERT INTO stage1_outputs (
            thread_id, source_updated_at, raw_memory, rollout_summary,
            rollout_slug, generated_at, usage_count, last_usage,
            selected_for_phase2
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "thread-demo-001",
            1785000000,
            RAW_MEMORY,
            "The user workflow and authentication propagation fix were captured.",
            "atlas-auth-fix",
            1785000060,
            3,
            1785001000,
            1,
        ),
    )
    connection.commit()
    connection.close()


def _create_state_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            cwd TEXT NOT NULL,
            rollout_path TEXT NOT NULL,
            git_branch TEXT,
            cli_version TEXT,
            title TEXT
        );
        """
    )
    connection.execute(
        """
        INSERT INTO threads (
            id, cwd, rollout_path, git_branch, cli_version, title
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "thread-demo-001",
            "/Users/demo/work/atlas",
            "/private/tmp/codex-demo/sessions/rollout-demo.jsonl",
            "fix/auth-propagation",
            "0.145.0",
            "Repair authentication",
        ),
    )
    connection.commit()
    connection.close()


class TestDatabaseSource:
    def test_loads_stage1_rows_and_enriches_thread_metadata(self, tmp_path):
        memory_db = tmp_path / "memories_1.sqlite"
        state_db = tmp_path / "state_5.sqlite"
        _create_memory_db(memory_db)
        _create_state_db(state_db)

        rows = adapter.load_memory_database(memory_db, state_db)

        assert len(rows) == 1
        assert rows[0].thread_id == "thread-demo-001"
        assert rows[0].cwd == "/Users/demo/work/atlas"
        assert rows[0].git_branch == "fix/auth-propagation"
        assert rows[0].cli_version == "0.145.0"
        assert rows[0].selected_for_phase2 is True

    def test_discovers_memory_and_state_databases(self, tmp_path):
        memory_db = tmp_path / "memories_1.sqlite"
        state_db = tmp_path / "state_5.sqlite"
        _create_memory_db(memory_db)
        _create_state_db(state_db)

        assert adapter.discover_memory_db(tmp_path) == memory_db
        assert adapter.discover_state_db(memory_db) == state_db

    def test_rejects_unrelated_sqlite_database(self, tmp_path):
        database = tmp_path / "other.sqlite"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE unrelated (id INTEGER)")
        connection.close()

        with pytest.raises(ValueError, match="stage1_outputs"):
            adapter.load_memory_database(database)

    def test_reads_checkpointed_wal_database_without_sidecars(self, tmp_path):
        memory_db = tmp_path / "memories_1.sqlite"
        _create_memory_db(memory_db)
        connection = sqlite3.connect(memory_db)
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        connection.close()

        assert not Path(f"{memory_db}-wal").exists()
        assert len(adapter.load_memory_database(memory_db)) == 1
        assert not Path(f"{memory_db}-wal").exists()

    def test_database_rows_have_a_stable_source_order(self, tmp_path):
        memory_db = tmp_path / "memories_1.sqlite"
        _create_memory_db(memory_db)
        connection = sqlite3.connect(memory_db)
        connection.execute(
            """
            INSERT INTO stage1_outputs (
                thread_id, source_updated_at, raw_memory, rollout_summary,
                rollout_slug, generated_at, usage_count, last_usage,
                selected_for_phase2
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "thread-early",
                1784000000,
                RAW_MEMORY,
                "Earlier memory.",
                "earlier-memory",
                1784000060,
                0,
                None,
                0,
            ),
        )
        connection.commit()
        connection.close()

        records = adapter.load_memory_database(memory_db)

        assert [record.thread_id for record in records] == [
            "thread-early",
            "thread-demo-001",
        ]


class TestTaskMapping:
    @pytest.fixture()
    def mapped(self):
        source = adapter.SourceMemory(
            thread_id="thread-demo-001",
            raw_memory=RAW_MEMORY,
            rollout_summary="Authentication workflow was repaired.",
            rollout_slug="atlas-auth-fix",
            source_updated_at=1785000000,
            generated_at=1785000060,
            usage_count=3,
            selected_for_phase2=True,
            cwd="/Users/demo/work/atlas",
            rollout_path="/private/tmp/codex-demo/sessions/rollout-demo.jsonl",
            git_branch="fix/auth-propagation",
            cli_version="0.145.0",
        )
        stats = adapter.MigrationStats(source_format="memory-db")
        redactor = adapter.Redactor()
        memories = adapter.map_source_memories([source], redactor=redactor, stats=stats)
        return memories, stats

    def test_splits_one_rollout_into_task_sized_memories(self, mapped):
        memories, stats = mapped

        assert len(memories) == 2
        assert stats.source_records == 1
        assert stats.source_tasks == 2
        assert stats.mapped_memories == 2
        assert [memory.title for memory in memories] == [
            "Preserve the user's review-first workflow",
            "Repair stale authentication propagation",
        ]

    def test_maps_preference_and_failure_semantics(self, mapped):
        memories, stats = mapped

        assert memories[0].memory_type == "preference"
        assert memories[1].memory_type == "learning"
        assert stats.type_counts == {"preference": 1, "learning": 1}

    def test_redacts_secrets_email_and_home_paths(self, mapped):
        memories, stats = mapped
        rendered = "\n".join(memory.body for memory in memories)
        metadata = json.dumps(
            [memory.metadata for memory in memories], ensure_ascii=False
        )

        assert "super-secret-value" not in rendered
        assert "API_KEY=[REDACTED_SECRET]" in rendered
        assert "/Users/demo" not in rendered + metadata
        assert "~/work/atlas" in rendered + metadata
        assert "/private/tmp/codex-demo" not in metadata
        assert "$TMPDIR/sessions/rollout-demo.jsonl" in metadata
        assert stats.redactions["secret_assignment"] == 1
        assert stats.redactions["home_path"] >= 1
        assert stats.redactions["temporary_path"] >= 1

    def test_redaction_is_idempotent(self):
        redactor = adapter.Redactor()
        once = redactor.redact("API_KEY=super-secret-value-123456789")
        twice = redactor.redact(once)

        assert once == "API_KEY=[REDACTED_SECRET]"
        assert twice == once
        assert redactor.counts["secret_assignment"] == 1

    def test_provenance_is_deterministic(self, mapped):
        memories, _ = mapped

        assert memories[0].resource == "codex://thread/thread-demo-001#task-1"
        assert memories[1].resource == "codex://thread/thread-demo-001#task-2"
        assert memories[0].metadata["codex_thread_id"] == "thread-demo-001"
        assert memories[0].metadata["codex_cli_version"] == "0.145.0"
        assert memories[0].timestamp == "2026-07-25T17:20:00+00:00"

    def test_no_failure_marker_does_not_override_decision(self):
        body = """\
Preference signals:
- Keep status updates concise.

Reusable knowledge:
- The team adopted PostgreSQL 16 for shared workers.

Failures and how to do differently:
- No failure; this was a read-only review.
"""

        memory_type = adapter.infer_memory_type(
            title="Reconcile adopted project decisions",
            body=body,
            outcome="success",
        )

        assert memory_type == "decision"

    def test_uses_rollout_summary_when_raw_memory_has_no_body(self):
        source = adapter.SourceMemory(
            thread_id="thread-summary-only",
            raw_memory="",
            rollout_summary="The project decided to keep UTC timestamps.",
            thread_title="Keep timestamps stable",
        )
        stats = adapter.MigrationStats(source_format="memory-db")

        memories = adapter.map_source_memories(
            [source], redactor=adapter.Redactor(), stats=stats
        )

        assert len(memories) == 1
        assert memories[0].title == "Keep timestamps stable"
        assert "keep UTC timestamps" in memories[0].body


class TestOkfRoundTrip:
    def test_shipped_loader_and_mapper_consume_the_bundle(self, tmp_path):
        source = adapter.SourceMemory(
            thread_id="thread-demo-001",
            raw_memory=RAW_MEMORY,
            rollout_summary="Authentication workflow was repaired.",
            source_updated_at=1785000000,
        )
        stats = adapter.MigrationStats(source_format="memory-db")
        memories = adapter.map_source_memories(
            [source], redactor=adapter.Redactor(), stats=stats
        )
        bundle = tmp_path / "bundle"
        adapter.write_okf_bundle(
            memories,
            bundle,
            split="file",
            overwrite=False,
            summary=stats.as_dict(),
        )

        export = load_okf_bundle(bundle)
        rows = map_okf(export)

        assert len(rows) == 2
        assert {row["type"] for row in rows} == {"preference", "learning"}
        assert all(row["source"] == "codex" for row in rows)
        assert all(row["provenance"] == "imported" for row in rows)
        assert all(row["source_ref"].startswith("codex://thread/") for row in rows)
        assert "codex_thread_id" in rows[0]["content"]
        assert (bundle / "migration_summary.json").exists()
        assert "# Codex memory migration\n\n- " in (bundle / "index.md").read_text(
            encoding="utf-8"
        )

    def test_stacked_type_layout_round_trips(self, tmp_path):
        source = adapter.SourceMemory(
            thread_id="thread-demo-001",
            raw_memory=RAW_MEMORY,
            rollout_summary="Authentication workflow was repaired.",
        )
        stats = adapter.MigrationStats(source_format="memory-db")
        memories = adapter.map_source_memories(
            [source], redactor=adapter.Redactor(), stats=stats
        )
        bundle = tmp_path / "stacked"
        adapter.write_okf_bundle(
            memories,
            bundle,
            split="type",
            overwrite=False,
            summary=stats.as_dict(),
        )

        assert len(map_okf(load_okf_bundle(bundle))) == 2

    def test_recall_validation_ignores_export_only_context(self, tmp_path):
        bundle = tmp_path / "bundle"
        memory_dir = bundle / "memories" / "decision"
        context_dir = bundle / "daily-summaries"
        memory_dir.mkdir(parents=True)
        context_dir.mkdir()
        (memory_dir / "project-rules.md").write_text(
            "The project stores every timestamp in UTC.", encoding="utf-8"
        )
        (context_dir / "2026-07-26.md").write_text(
            "This export-only summary must not affect recall.", encoding="utf-8"
        )

        documents = recall_validator.load_okf_documents(bundle)

        assert documents == ["The project stores every timestamp in UTC."]

    def test_existing_output_requires_explicit_overwrite(self, tmp_path):
        output = tmp_path / "bundle"
        output.mkdir()

        with pytest.raises(FileExistsError, match="--overwrite"):
            adapter.write_okf_bundle(
                [],
                output,
                split="file",
                overwrite=False,
                summary={},
            )

    def test_overwrite_refuses_unrecognized_directory(self, tmp_path):
        output = tmp_path / "user-data"
        output.mkdir()
        sentinel = output / "keep.txt"
        sentinel.write_text("important", encoding="utf-8")

        with pytest.raises(FileExistsError, match="refusing to overwrite"):
            adapter.write_okf_bundle(
                [],
                output,
                split="file",
                overwrite=True,
                summary={"adapter": "codex-to-okf"},
            )

        assert sentinel.read_text(encoding="utf-8") == "important"

    def test_overwrite_replaces_adapter_generated_bundle(self, tmp_path):
        output = tmp_path / "bundle"
        summary = {"adapter": "codex-to-okf"}
        adapter.write_okf_bundle(
            [],
            output,
            split="file",
            overwrite=False,
            summary=summary,
        )
        stale = output / "stale.txt"
        stale.write_text("stale", encoding="utf-8")

        adapter.write_okf_bundle(
            [],
            output,
            split="file",
            overwrite=True,
            summary=summary,
        )

        assert not stale.exists()
        assert (
            json.loads((output / "migration_summary.json").read_text(encoding="utf-8"))
            == summary
        )


class TestPortableSourceExport:
    def test_json_snapshot_round_trips_source_records(self, tmp_path):
        source = [
            adapter.SourceMemory(
                thread_id="thread-demo-001",
                raw_memory=RAW_MEMORY,
                rollout_summary="Authentication workflow was repaired.",
                cli_version="0.145.0",
            )
        ]
        destination = tmp_path / "source.json"

        adapter.write_source_export(
            source,
            destination,
            source_fingerprint="sha256:demo",
            codex_version="0.145.0",
        )
        loaded = adapter.load_source_export(destination)

        assert loaded == source
        payload = json.loads(destination.read_text(encoding="utf-8"))
        assert payload["schema"] == adapter.EXPORT_SCHEMA
        assert payload["source_fingerprint"] == "sha256:demo"

    def test_rejects_export_record_missing_required_fields(self, tmp_path):
        source = tmp_path / "invalid.json"
        source.write_text(
            json.dumps(
                {
                    "schema": adapter.EXPORT_SCHEMA,
                    "records": [{"thread_id": "thread-demo-001"}],
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="missing required fields"):
            adapter.load_source_export(source)

    def test_source_fingerprint_is_independent_of_record_order(self):
        records = [
            adapter.SourceMemory(
                thread_id="thread-b",
                raw_memory=RAW_MEMORY,
                rollout_summary="Memory B.",
            ),
            adapter.SourceMemory(
                thread_id="thread-a",
                raw_memory=RAW_MEMORY,
                rollout_summary="Memory A.",
            ),
        ]

        assert adapter._source_fingerprint(records) == adapter._source_fingerprint(
            reversed(records)
        )


class TestSessionFallback:
    def _write_rollout(self, path: Path, *, malformed: bool = False) -> None:
        records = [
            {
                "type": "session_meta",
                "timestamp": "2026-07-25T08:00:00Z",
                "payload": {
                    "id": "session-001",
                    "cwd": "/Users/demo/work/atlas",
                    "cli_version": "0.145.0",
                    "git": {"branch": "main"},
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "private policy"}],
                },
            },
            {
                "type": "event_msg",
                "timestamp": "2026-07-25T08:01:00Z",
                "payload": {"type": "task_started", "turn_id": "turn-001"},
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": "Keep UTC timestamps in the Atlas service.",
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "phase": "commentary",
                    "message": "Hidden progress with ghp_abcdefghijklmnopqrstuvwxyz1234",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "output": "private tool output",
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "phase": "final_answer",
                    "message": "Atlas now stores all timestamps in UTC.",
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": "turn-001",
                    "last_agent_message": "Atlas now stores all timestamps in UTC.",
                },
            },
        ]
        lines = [json.dumps(record) for record in records]
        if malformed:
            lines.insert(3, "{not-json")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_uses_only_user_and_final_messages(self, tmp_path):
        rollout = tmp_path / "rollout-demo.jsonl"
        self._write_rollout(rollout)
        stats = adapter.MigrationStats(source_format="sessions")

        records = adapter.load_session_rollouts(rollout, strict=False, stats=stats)

        assert len(records) == 1
        raw = records[0].raw_memory
        assert "Keep UTC timestamps" in raw
        assert "Atlas now stores" in raw
        assert "Hidden progress" not in raw
        assert "private policy" not in raw
        assert "private tool output" not in raw
        assert records[0].source_kind == "session_rollout"
        assert records[0].turn_id == "turn-001"

    def test_turn_ids_keep_multi_turn_resources_unique(self):
        raw_memory = adapter._session_turn_memory(
            title="Keep UTC timestamps",
            user_message="Keep UTC timestamps.",
            final_answer="All timestamps are UTC.",
            cwd="/workspace/atlas",
        )
        sources = [
            adapter.SourceMemory(
                thread_id="session-001",
                turn_id=turn_id,
                raw_memory=raw_memory,
                rollout_summary="All timestamps are UTC.",
                source_kind="session_rollout",
            )
            for turn_id in ("turn-001", "turn-002")
        ]
        stats = adapter.MigrationStats(source_format="sessions")

        memories = adapter.map_source_memories(
            sources,
            redactor=adapter.Redactor(),
            stats=stats,
        )

        assert [memory.resource for memory in memories] == [
            "codex://thread/session-001/turn/turn-001#task-1",
            "codex://thread/session-001/turn/turn-002#task-1",
        ]
        assert [memory.metadata["codex_turn_id"] for memory in memories] == [
            "turn-001",
            "turn-002",
        ]

    def test_skips_malformed_lines_by_default(self, tmp_path):
        rollout = tmp_path / "rollout-demo.jsonl"
        self._write_rollout(rollout, malformed=True)
        stats = adapter.MigrationStats(source_format="sessions")

        records = adapter.load_session_rollouts(rollout, strict=False, stats=stats)

        assert len(records) == 1
        assert stats.malformed_lines == 1

    def test_strict_mode_reports_file_and_line(self, tmp_path):
        rollout = tmp_path / "rollout-demo.jsonl"
        self._write_rollout(rollout, malformed=True)
        stats = adapter.MigrationStats(source_format="sessions")

        with pytest.raises(ValueError, match=r"rollout-demo\.jsonl:4"):
            adapter.load_session_rollouts(rollout, strict=True, stats=stats)

    def test_strict_mode_ignores_blank_lines(self, tmp_path):
        rollout = tmp_path / "rollout-demo.jsonl"
        self._write_rollout(rollout)
        lines = rollout.read_text(encoding="utf-8").splitlines()
        rollout.write_text("\n\n".join(lines) + "\n\n", encoding="utf-8")
        stats = adapter.MigrationStats(source_format="sessions")

        records = adapter.load_session_rollouts(rollout, strict=True, stats=stats)

        assert len(records) == 1
        assert stats.malformed_lines == 0

    def test_main_counts_each_source_redaction_once(self, tmp_path):
        export = tmp_path / "source.json"
        export.write_text(
            json.dumps(
                {
                    "schema": adapter.EXPORT_SCHEMA,
                    "records": [
                        {
                            "thread_id": "thread-secret",
                            "raw_memory": (
                                "### Task 1: Keep the credential private\n\n"
                                "Reusable knowledge:\n"
                                "- API_KEY=super-secret-value-123456789"
                            ),
                            "rollout_summary": "Credential handling was documented.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        output = tmp_path / "bundle"

        exit_code = adapter.main(
            [
                str(export),
                "--source-format",
                "export-json",
                "--output",
                str(output),
            ]
        )

        summary = json.loads(
            (output / "migration_summary.json").read_text(encoding="utf-8")
        )
        assert exit_code == 0
        assert summary["redactions"]["secret_assignment"] == 1

    def test_auto_source_falls_back_when_memory_database_is_empty(self, tmp_path):
        memory_db = tmp_path / "memories_1.sqlite"
        connection = sqlite3.connect(memory_db)
        connection.executescript(
            """
            CREATE TABLE stage1_outputs (
                thread_id TEXT PRIMARY KEY,
                source_updated_at INTEGER NOT NULL,
                raw_memory TEXT NOT NULL,
                rollout_summary TEXT NOT NULL,
                generated_at INTEGER NOT NULL
            );
            """
        )
        connection.close()
        rollout = tmp_path / "sessions" / "2026" / "rollout-demo.jsonl"
        rollout.parent.mkdir(parents=True)
        self._write_rollout(rollout)
        stats = adapter.MigrationStats(source_format="auto")

        records, resolved_format = adapter._load_source(
            tmp_path,
            source_format="auto",
            state_db=None,
            strict=False,
            stats=stats,
        )

        assert len(records) == 1
        assert resolved_format == "sessions"


class TestCommittedSample:
    def test_real_codex_sample_round_trips_through_memanto(self):
        source_path = _EXAMPLE_DIR / "sample_data" / "codex-memory-export.json"
        bundle = _EXAMPLE_DIR / "sample_output" / "okf-bundle"

        source_records = adapter.load_source_export(source_path)
        mapped_rows = map_okf(load_okf_bundle(bundle))

        assert len(source_records) == 1
        assert source_records[0].source_kind == "stage1_memory"
        assert source_records[0].cli_version == "0.145.0-alpha.30"
        assert len(mapped_rows) == 1
        assert mapped_rows[0]["type"] == "decision"
        assert mapped_rows[0]["source"] == "codex"
        assert mapped_rows[0]["provenance"] == "imported"
        assert mapped_rows[0]["source_ref"].startswith("codex://thread/")

        payload = json.loads(source_path.read_text(encoding="utf-8"))
        assert payload["source_fingerprint"] == adapter._source_fingerprint(
            source_records
        )

    def test_committed_artifacts_contain_no_personal_paths_or_common_secrets(self):
        artifact_paths = [
            _EXAMPLE_DIR / "sample_data" / "codex-memory-export.json",
            *(_EXAMPLE_DIR / "sample_output").rglob("*"),
        ]
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in artifact_paths
            if path.is_file()
        )

        assert "/Users/" not in text
        assert "/private/tmp/" not in text
        assert "/tmp/memanto-" not in text
        assert "nijianwei" not in text.lower()
        assert not re.search(r"\bsk-[A-Za-z0-9_-]{16,}\b", text)
        assert not re.search(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b", text)

        recall_report = json.loads(
            (_EXAMPLE_DIR / "sample_output" / "recall_report.json").read_text(
                encoding="utf-8"
            )
        )
        assert recall_report["source_score"] == 100.0
        assert recall_report["okf_score"] == 100.0
        assert recall_report["parity_delta"] == 0.0
