"""Claude Code local-memory → OKF adapter coverage."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "migrations" / "claude-code"
ADAPTER_PATH = EXAMPLE_DIR / "claude_code_to_okf.py"

spec = importlib.util.spec_from_file_location("claude_code_to_okf", ADAPTER_PATH)
assert spec is not None and spec.loader is not None
adapter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = adapter
spec.loader.exec_module(adapter)


def write_jsonl(path: Path, rows: list[dict] | None = None, raw: str = "") -> None:
    """Write a compact JSONL fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row) + "\n" for row in (rows or [])) + raw
    path.write_text(text, encoding="utf-8")


def make_layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a minimal Claude home, project path, and project-state directory."""
    claude_home = tmp_path / "home" / ".claude"
    project = tmp_path / "home" / "Projects" / "demo"
    project.mkdir(parents=True)
    project_dir = claude_home / "projects" / adapter.project_slug(project)
    (project_dir / "memory").mkdir(parents=True)
    return claude_home, project, project_dir


def test_sample_fixture_maps_real_memory_and_history() -> None:
    """The committed privacy-redacted real fixture maps to three useful memories."""
    claude_home = EXAMPLE_DIR / "sample_data" / ".claude"
    project = Path("/Users/demo/Projects/auto-planmaxxer")
    project_dir = claude_home / "projects" / "-Users-demo-Projects-auto-planmaxxer"

    records, stats = adapter.collect_records(
        claude_home,
        project,
        project_dir,
        include_transcripts=True,
        include_todos=True,
    )

    assert len(records) == 3
    assert {record.memory_type for record in records} == {
        "fact",
        "preference",
        "context",
    }
    assert stats.source_by_kind == {
        "auto-memory": 2,
        "history-prompt": 3,
    }
    assert stats.observed_session_ids == {"71933048-a1d1-425a-87dd-40ba20e66b48"}


def test_memory_frontmatter_mapping_and_index_skip(tmp_path: Path) -> None:
    """Claude memory prefixes/frontmatter map to canonical Memanto types."""
    claude_home, project, project_dir = make_layout(tmp_path)
    memory = project_dir / "memory"
    (memory / "MEMORY.md").write_text("- [Index](feedback_rule.md)\n", encoding="utf-8")
    (memory / "feedback_rule.md").write_text(
        "---\n"
        "name: Always verify\n"
        "description: Verification rule\n"
        "type: feedback\n"
        "---\n\n"
        "Run the real boundary before claiming success.\n",
        encoding="utf-8",
    )
    (memory / "reference_api.md").write_text(
        "---\ntype: reference\n---\n\nAPI contract notes.\n",
        encoding="utf-8",
    )

    records, _ = adapter.collect_records(
        claude_home,
        project,
        project_dir,
        include_history=False,
        include_transcripts=False,
        include_todos=False,
    )

    assert [(record.title, record.memory_type) for record in records] == [
        ("Always verify", "instruction"),
        ("reference api", "artifact"),
    ]
    assert "Verification rule" in records[0].content


def test_history_filters_project_and_control_commands(tmp_path: Path) -> None:
    """Only selected-project prompts become context; slash commands stay out."""
    claude_home, project, project_dir = make_layout(tmp_path)
    write_jsonl(
        claude_home / "history.jsonl",
        [
            {
                "project": str(project) + "/",
                "sessionId": "session-a",
                "timestamp": 1_700_000_000_000,
                "display": "/clear",
            },
            {
                "project": str(project),
                "sessionId": "session-a",
                "timestamp": 1_700_000_001_000,
                "display": "Use PostgreSQL 16 for the service.",
            },
            {
                "project": str(tmp_path / "other"),
                "sessionId": "session-b",
                "timestamp": 1_700_000_002_000,
                "display": "Unrelated secret project.",
            },
        ],
    )

    records, stats = adapter.collect_records(
        claude_home,
        project,
        project_dir,
        include_transcripts=False,
        include_todos=False,
    )

    assert len(records) == 1
    assert "PostgreSQL 16" in records[0].content
    assert "/clear" not in records[0].content
    assert "Unrelated" not in records[0].content
    assert stats.observed_session_ids == {"session-a"}


def test_transcript_text_only_and_redacted(tmp_path: Path) -> None:
    """Natural-language turns survive; tool payloads and credentials do not."""
    claude_home, project, project_dir = make_layout(tmp_path)
    transcript = project_dir / "session-a.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "type": "user",
                "sessionId": "session-a",
                "timestamp": "2026-07-01T10:00:00Z",
                "message": {
                    "content": (
                        f"Project is {project}. Contact me@example.com and use "
                        "api_key=supersecretvalue."
                    )
                },
            },
            {
                "type": "assistant",
                "sessionId": "session-a",
                "timestamp": "2026-07-01T10:01:00Z",
                "message": {
                    "content": [
                        {"type": "text", "text": "The database is PostgreSQL 16."},
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "printenv"},
                        },
                    ]
                },
            },
        ],
    )

    records, stats = adapter.collect_records(
        claude_home,
        project,
        project_dir,
        include_history=False,
        include_todos=False,
    )

    assert len(records) == 1
    content = records[0].content
    assert "${PROJECT}" in content
    assert "[REDACTED_EMAIL]" in content
    assert "api_key=[REDACTED]" in content
    assert "PostgreSQL 16" in content
    assert "printenv" not in content
    assert stats.redactions["email"] == 1
    assert stats.redactions["credential-assignment"] == 1


def test_todos_are_scoped_by_observed_session(tmp_path: Path) -> None:
    """Pending/completed todos map only when their session belongs to the project."""
    claude_home, project, project_dir = make_layout(tmp_path)
    write_jsonl(
        claude_home / "history.jsonl",
        [
            {
                "project": str(project),
                "sessionId": "owned-session",
                "timestamp": 1_700_000_000_000,
                "display": "Build the importer.",
            }
        ],
    )
    todo_dir = claude_home / "todos"
    todo_dir.mkdir(parents=True)
    (todo_dir / "owned-session-agent-owned-session.json").write_text(
        json.dumps(
            [
                {
                    "content": "Add round-trip tests",
                    "activeForm": "Adding tests",
                    "status": "pending",
                },
                {
                    "content": "Inspect source schema",
                    "activeForm": "Inspecting",
                    "status": "completed",
                },
            ]
        ),
        encoding="utf-8",
    )
    (todo_dir / "other-session-agent-other-session.json").write_text(
        json.dumps(
            [
                {
                    "content": "Leak unrelated task",
                    "activeForm": "Leaking",
                    "status": "pending",
                }
            ]
        ),
        encoding="utf-8",
    )

    records, _ = adapter.collect_records(
        claude_home,
        project,
        project_dir,
        include_transcripts=False,
    )
    by_title = {record.title: record for record in records}

    assert by_title["Add round-trip tests"].memory_type == "commitment"
    assert by_title["Inspect source schema"].memory_type == "event"
    assert "Leak unrelated task" not in by_title


def test_invalid_json_is_counted_without_aborting(tmp_path: Path) -> None:
    """One damaged JSONL line cannot erase the rest of a migration."""
    claude_home, project, project_dir = make_layout(tmp_path)
    write_jsonl(
        claude_home / "history.jsonl",
        [
            {
                "project": str(project),
                "sessionId": "session-a",
                "timestamp": 1_700_000_000_000,
                "display": "Keep this valid line.",
            }
        ],
        raw="{not-json}\n",
    )

    records, stats = adapter.collect_records(
        claude_home,
        project,
        project_dir,
        include_transcripts=False,
        include_todos=False,
    )

    assert len(records) == 1
    assert stats.invalid_json_lines == 1


def test_end_to_end_okf_round_trip(tmp_path: Path) -> None:
    """Mapped records survive the shipped OKF exporter, loader, and mapper."""
    claude_home, project, project_dir = make_layout(tmp_path)
    (project_dir / "memory" / "project_stack.md").write_text(
        "---\nname: Project stack\ntype: project\n---\n\nUses PostgreSQL 16.\n",
        encoding="utf-8",
    )
    write_jsonl(
        claude_home / "history.jsonl",
        [
            {
                "project": str(project),
                "sessionId": "session-a",
                "timestamp": 1_700_000_000_000,
                "display": "Preserve this decision.",
            }
        ],
    )
    records, stats = adapter.collect_records(
        claude_home,
        project,
        project_dir,
        include_transcripts=False,
        include_todos=False,
    )
    output = tmp_path / "out" / "okf"
    summary = adapter.write_okf_bundle(records, stats, output)
    loaded = load_okf_bundle(output)
    mapped = map_okf(loaded)

    assert summary["okf_output"]["total_memories"] == 2
    assert {row["type"] for row in mapped} == {"fact", "context"}
    assert any("PostgreSQL 16" in row["content"] for row in mapped)
    assert all(row["source"] == "claude-code" for row in mapped)
    assert all(row["provenance"] == "imported" for row in mapped)
    generated_markdown = "\n".join(
        path.read_text(encoding="utf-8") for path in output.rglob("*.md")
    )
    assert not any(
        line.endswith((" ", "\t")) for line in generated_markdown.splitlines()
    )


def test_standalone_recall_validator_runs_on_sample(tmp_path: Path) -> None:
    """The CLI validator can import the dataclass adapter in a fresh process."""
    claude_home = EXAMPLE_DIR / "sample_data" / ".claude"
    project = Path("/Users/demo/Projects/auto-planmaxxer")
    project_dir = claude_home / "projects" / "-Users-demo-Projects-auto-planmaxxer"
    records, stats = adapter.collect_records(
        claude_home,
        project,
        project_dir,
        include_transcripts=True,
        include_todos=True,
    )
    output = tmp_path / "okf"
    adapter.write_okf_bundle(records, stats, output)
    report = tmp_path / "recall_parity.json"

    result = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE_DIR / "validation" / "validate_recall.py"),
            "--source-home",
            str(claude_home),
            "--project",
            str(project),
            "--project-data",
            str(project_dir),
            "--okf",
            str(output),
            "--questions",
            str(EXAMPLE_DIR / "validation" / "golden_qa.json"),
            "--report",
            str(report),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    parity = json.loads(report.read_text(encoding="utf-8"))
    assert parity["source"]["passed"] == parity["source"]["total"] == 5
    assert parity["okf"]["passed"] == parity["okf"]["total"] == 5
    assert parity["parity_delta_points"] == 0.0


def test_existing_output_requires_explicit_force(tmp_path: Path) -> None:
    """Only a bundle previously written by this adapter can be replaced."""
    stats = adapter.MigrationStats(project="demo")
    record = adapter.SourceRecord(
        source_id="id",
        source_kind="auto-memory",
        title="Title",
        content="Body",
        memory_type="fact",
        tags=("claude-code",),
        source_ref="claude-code:memory:id",
    )
    output = tmp_path / "okf"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        adapter.write_okf_bundle([record], stats, output)

    with pytest.raises(FileExistsError, match="unrecognized output"):
        adapter.write_okf_bundle([record], stats, output, force=True)
    assert (output / "keep.txt").exists()

    safe_output = tmp_path / "safe-okf"
    adapter.write_okf_bundle([record], stats, safe_output)
    (safe_output / "stale.txt").write_text("stale", encoding="utf-8")

    adapter.write_okf_bundle([record], stats, safe_output, force=True)
    assert not (safe_output / "stale.txt").exists()
    summary = json.loads(
        (safe_output / "migration_summary.json").read_text(encoding="utf-8")
    )
    assert summary["adapter"] == "claude-code-to-okf"
    assert summary["schema_version"] == 1


def test_source_and_output_paths_cannot_overlap(tmp_path: Path) -> None:
    """The CLI refuses an output that could overwrite Claude Code source data."""
    claude_home, project, project_dir = make_layout(tmp_path)
    (project_dir / "memory" / "project.md").write_text(
        "---\ntype: project\n---\n\nKeep source data safe.\n",
        encoding="utf-8",
    )
    output = project_dir / "generated"

    with pytest.raises(ValueError, match="overlaps Claude Code source data"):
        adapter.main(
            [
                "--claude-home",
                str(claude_home),
                "--project",
                str(project),
                "--project-data",
                str(project_dir),
                "--output",
                str(output),
            ]
        )

    assert not output.exists()


def test_force_does_not_replace_a_file(tmp_path: Path) -> None:
    """A file target is never treated as an adapter-owned bundle."""
    output = tmp_path / "not-a-directory"
    output.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError, match="unrecognized output"):
        adapter.write_okf_bundle(
            [], adapter.MigrationStats(project="demo"), output, force=True
        )

    assert output.read_text(encoding="utf-8") == "keep"


def test_force_replaces_a_recognized_empty_bundle(tmp_path: Path) -> None:
    """Adapter ownership is explicit even when the first bundle has no memories."""
    output = tmp_path / "okf"
    stats = adapter.MigrationStats(project="demo")
    adapter.write_okf_bundle([], stats, output)
    (output / "stale.txt").write_text("stale", encoding="utf-8")

    adapter.write_okf_bundle([], stats, output, force=True)
    assert not (output / "stale.txt").exists()
    assert (output / "migration_summary.json").exists()


def test_project_discovery_accepts_legacy_trailing_dash(tmp_path: Path) -> None:
    """Legacy Claude slugs with a trailing punctuation dash remain discoverable."""
    claude_home = tmp_path / ".claude"
    project = tmp_path / "Projects" / "plan tool"
    legacy = claude_home / "projects" / (adapter.project_slug(project) + "-")
    legacy.mkdir(parents=True)

    assert adapter.discover_project_dir(claude_home, project) == legacy


def test_stable_ids_do_not_expose_raw_session_ids() -> None:
    """Source refs use deterministic fingerprints rather than local UUIDs."""
    value = adapter.stable_id("session", "private-session-uuid")
    assert value == adapter.stable_id("session", "private-session-uuid")
    assert value != adapter.stable_id("session", "other-session-uuid")
    assert "private-session" not in value
    assert len(value) == 20


def test_committed_sample_has_no_local_user_path_or_credentials() -> None:
    """The public fixture contains no developer home path or secret-shaped token."""
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((EXAMPLE_DIR / "sample_data").rglob("*"))
        if path.is_file()
    )
    assert "/Users/zacfarrell" not in text
    assert "sorellonltd@gmail.com" not in text
    assert "ghp_" not in text
    assert "sk-" not in text
