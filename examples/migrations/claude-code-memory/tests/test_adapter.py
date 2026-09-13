"""Tests for the Claude Code conversation memory adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from claude_code_adapter.cli import main as cli_main
from claude_code_adapter.extractor import extract_memories
from claude_code_adapter.okf_writer import write_okf_bundle
from claude_code_adapter.parser import parse_claude_jsonl

ROOT = Path(__file__).resolve().parents[1]


def _line(obj: dict) -> str:
    """Serialize one JSONL record."""
    return json.dumps(obj, ensure_ascii=False)


def _sample_turns(tmp_path: Path) -> Path:
    """Write a small but realistic Claude Code JSONL archive."""
    archive = tmp_path / "session.jsonl"
    lines = [
        {
            "type": "file-history-snapshot",
            "messageId": "snap-1",
            "snapshot": {},
            "isSnapshotUpdate": False,
        },
        {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-07-28T09:00:00Z",
            "sessionId": "sess-1",
            "cwd": r"I:\project\payments-api",
            "gitBranch": "main",
            "message": {
                "role": "user",
                "content": (
                    "Build a FastAPI payment service with Stripe. "
                    "I prefer SQLAlchemy over raw SQL."
                ),
            },
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "timestamp": "2026-07-28T09:00:03Z",
            "sessionId": "sess-1",
            "cwd": r"I:\project\payments-api",
            "gitBranch": "main",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "I decided to put the Stripe client behind an "
                            "interface so tests can mock it easily."
                        ),
                    }
                ],
            },
        },
        {
            "type": "user",
            "uuid": "u2",
            "timestamp": "2026-07-28T09:01:00Z",
            "sessionId": "sess-1",
            "cwd": r"I:\project\payments-api",
            "gitBranch": "main",
            "message": {
                "role": "user",
                "content": (
                    "Remember to always use pydantic v2, never log API keys, "
                    "and my team prefers black formatting."
                ),
            },
        },
        {
            "type": "last-prompt",
            "lastPrompt": "Build a FastAPI payment service with Stripe.",
            "sessionId": "sess-1",
        },
    ]
    archive.write_text("\n".join(_line(item) for item in lines), encoding="utf-8")
    return archive


def _bundle_snapshot(bundle: Path) -> dict[str, bytes]:
    """Snapshot every file in a bundle keyed by its relative path."""
    return {
        path.relative_to(bundle): path.read_bytes()
        for path in sorted(bundle.rglob("*"))
        if path.is_file()
    }


def test_parse_skips_snapshots_and_last_prompt(tmp_path):
    """Snapshots and last-prompt sentinels are not conversation turns."""
    archive = _sample_turns(tmp_path)
    turns = parse_claude_jsonl(archive)
    assert len(turns) == 3  # 2 user + 1 assistant
    assert all(t.role in {"user", "assistant"} for t in turns)
    assert turns[0].cwd == r"I:\project\payments-api"
    assert turns[0].git_branch == "main"
    assert turns[1].tool_uses == []


def test_parse_missing_file(tmp_path):
    """A missing archive raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        parse_claude_jsonl(tmp_path / "missing.jsonl")


def test_extract_user_preferences_and_instructions(tmp_path):
    """User preferences and instructions are extracted with Memanto metadata."""
    archive = _sample_turns(tmp_path)
    turns = parse_claude_jsonl(archive)
    memories = extract_memories(turns, source_path=str(archive))
    types = {m["type"] for m in memories}
    assert "preference" in types
    assert "instruction" in types
    assert all(m["x_memanto"]["source"] == "claude-code" for m in memories)
    assert all(m["x_memanto"]["provenance"] == "imported" for m in memories)


def test_extract_includes_assistant_decisions_by_default(tmp_path):
    """Assistant decision summaries are extracted unless --user-only."""
    archive = _sample_turns(tmp_path)
    turns = parse_claude_jsonl(archive)
    memories = extract_memories(turns, source_path=str(archive))
    decision = [m for m in memories if m["type"] == "decision"]
    assert decision, "assistant decision should be extracted by default"


def test_user_only_skips_assistant(tmp_path):
    """--user-only keeps only high-confidence user-statement memories."""
    archive = _sample_turns(tmp_path)
    turns = parse_claude_jsonl(archive)
    memories = extract_memories(turns, include_assistant=False)
    assert all(m["x_memanto"]["confidence"] >= 0.9 for m in memories)
    assert all("decided" not in m["body"] for m in memories)


def test_write_okf_bundle_roundtrip(tmp_path):
    """The bundle writer emits importable markdown with x_memanto blocks."""
    archive = _sample_turns(tmp_path)
    turns = parse_claude_jsonl(archive)
    memories = extract_memories(turns, source_path=str(archive))
    bundle = tmp_path / "bundle"
    result = write_okf_bundle(memories, bundle)

    assert result["total_memories"] == len(memories)
    assert result["per_type_counts"]
    assert (bundle / "index.md").exists()
    assert (bundle / "memories").is_dir()

    # Each memory should be a markdown file with YAML frontmatter.
    # Skip index.md navigation files (they have no x_memanto block).
    md_files = [p for p in (bundle / "memories").rglob("*.md") if p.name != "index.md"]
    assert md_files
    sample = md_files[0].read_text(encoding="utf-8")
    assert sample.startswith("---\n")
    assert "x_memanto:" in sample
    assert "source: claude-code" in sample


def test_repeated_write_removes_stale_memories(tmp_path):
    """Re-running into an existing bundle dir must not leave old memories."""
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    first = _sample_turns(tmp_path)
    bundle = tmp_path / "bundle"
    write_okf_bundle(
        extract_memories(parse_claude_jsonl(first), source_path=str(first)),
        bundle,
    )
    first_loaded = load_okf_bundle(bundle)
    assert any("pydantic" in (m.get("body") or "") for m in first_loaded["memories"])

    second = tmp_path / "second.jsonl"
    second.write_text(
        _line(
            {
                "type": "user",
                "uuid": "u-second",
                "timestamp": "2026-07-29T10:00:00Z",
                "sessionId": "sess-2",
                "cwd": r"D:\work\mobile-app",
                "gitBranch": "feat/onboarding",
                "message": {
                    "role": "user",
                    "content": (
                        "I decided to use SwiftUI for the mobile app "
                        "and prefer dark mode by default."
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    second_memories = extract_memories(
        parse_claude_jsonl(second), source_path=str(second)
    )
    write_okf_bundle(second_memories, bundle)

    second_loaded = load_okf_bundle(bundle)
    assert len(second_loaded["memories"]) == len(second_memories)
    assert not any(
        "pydantic" in (m.get("body") or "") for m in second_loaded["memories"]
    )


def test_write_failure_keeps_previous_bundle(tmp_path, monkeypatch):
    """A failed rewrite must leave the previous bundle readable."""
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    first = _sample_turns(tmp_path)
    bundle = tmp_path / "bundle"
    first_memories = extract_memories(parse_claude_jsonl(first), source_path=str(first))
    write_okf_bundle(first_memories, bundle)
    before = _bundle_snapshot(bundle)

    def _fail_write(self, *args, **kwargs):
        """Fail every Path.write_text call to simulate a write error."""
        raise OSError("injected write failure")

    monkeypatch.setattr(Path, "write_text", _fail_write)
    with pytest.raises(OSError, match="injected write failure"):
        write_okf_bundle(first_memories, bundle)

    assert _bundle_snapshot(bundle) == before
    after = load_okf_bundle(bundle)
    assert len(after["memories"]) == len(first_memories)
    assert not list(bundle.parent.glob(f".{bundle.name}.bak-*"))
    assert not list(bundle.parent.glob(f".{bundle.name}.tmp-*"))


def test_publish_failure_rolls_back_previous_bundle(tmp_path, monkeypatch):
    """A failed publish step must restore the previous bundle."""
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    first = _sample_turns(tmp_path)
    bundle = tmp_path / "bundle"
    first_memories = extract_memories(parse_claude_jsonl(first), source_path=str(first))
    write_okf_bundle(first_memories, bundle)
    before = _bundle_snapshot(bundle)

    original_rename = Path.rename

    def _fail_staging_rename(self, target):
        """Fail only the publish move (staging -> output)."""
        if self.name.startswith(f".{bundle.name}.tmp-"):
            raise OSError("injected publish failure")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", _fail_staging_rename)
    with pytest.raises(OSError, match="injected publish failure"):
        write_okf_bundle(first_memories, bundle)

    # Rollback restored the previous bundle byte-for-byte; no debris remains.
    assert _bundle_snapshot(bundle) == before
    after = load_okf_bundle(bundle)
    assert len(after["memories"]) == len(first_memories)
    assert not list(bundle.parent.glob(f".{bundle.name}.bak-*"))
    assert not list(bundle.parent.glob(f".{bundle.name}.tmp-*"))


def test_okf_bundle_loadable_by_memanto_loader(tmp_path):
    """The bundle must be parseable by memanto's own OKF loader.

    This is a hard requirement rather than a soft check: the whole point of
    the adapter is producing bundles ``memanto migrate okf`` can consume, so
    the test fails when the memanto package is not importable. Run pytest
    from the memanto repository root (see README).
    """
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    archive = _sample_turns(tmp_path)
    turns = parse_claude_jsonl(archive)
    memories = extract_memories(turns, source_path=str(archive))
    bundle = tmp_path / "bundle"
    write_okf_bundle(memories, bundle)

    loaded = load_okf_bundle(bundle)
    assert "memories" in loaded
    assert len(loaded["memories"]) == len(memories)
    assert all("body" in m and m["body"] for m in loaded["memories"])


def test_demo_generator_produces_parseable_archive(tmp_path):
    """The generated demo archive parses and extracts at least 5 memories."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from generate_demo_session import generate_session

    archive = generate_session(tmp_path / "demo_session.jsonl")
    turns = parse_claude_jsonl(archive)
    assert len(turns) >= 8
    memories = extract_memories(turns)
    assert len(memories) >= 5
    types = {m["type"] for m in memories}
    assert {"preference", "instruction", "decision"}.issubset(types)


def test_demo_generator_is_byte_stable(tmp_path):
    """Two runs of the demo generator produce byte-identical archives."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from generate_demo_session import generate_session

    first = generate_session(tmp_path / "a.jsonl")
    second = generate_session(tmp_path / "b.jsonl")
    assert first.read_bytes() == second.read_bytes()


def test_two_archives_keep_individual_sources(tmp_path):
    """Memories from two archives keep the exact archive they came from."""
    _sample_turns(tmp_path)  # writes session.jsonl
    second = tmp_path / "second.jsonl"
    second.write_text(
        "\n".join(
            [
                _line(
                    {
                        "type": "user",
                        "uuid": "u-second",
                        "timestamp": "2026-07-29T10:00:00Z",
                        "sessionId": "sess-2",
                        "cwd": r"D:\work\mobile-app",
                        "gitBranch": "feat/onboarding",
                        "message": {
                            "role": "user",
                            "content": (
                                "I decided to use SwiftUI for the mobile app "
                                "and prefer dark mode by default."
                            ),
                        },
                    }
                ),
                _line(
                    {
                        "type": "last-prompt",
                        "lastPrompt": "Build the mobile app.",
                        "sessionId": "sess-2",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    out = tmp_path / "bundle"
    assert cli_main(["--projects", str(tmp_path), "--output", str(out)]) == 0

    resources: set[str] = set()
    for md in (out / "memories").rglob("*.md"):
        if md.name == "index.md":
            continue
        for line in md.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("resource:"):
                resources.add(line)
    assert any("session.jsonl" in r for r in resources)
    assert any("second.jsonl" in r for r in resources)


def test_real_shape_fixture_parses_and_extracts():
    """A real-format (sanitized) Claude Code excerpt parses and extracts."""
    fixture = ROOT / "fixtures" / "real_session_excerpt.jsonl"
    turns = parse_claude_jsonl(fixture)
    assert any(t.role == "user" for t in turns)
    assert not any(t.is_meta for t in turns)

    # The assistant turn carrying the Bash tool_use is preserved as tool
    # metadata, never as memory text.
    tool_turn = next(t for t in turns if t.role == "assistant" and t.tool_uses)
    assert any(u.get("name") == "Bash" for u in tool_turn.tool_uses)

    # Per the Claude message contract, the tool_result arrives in a user
    # message immediately after the tool_use, and is excluded from memory.
    result_turn = next(
        t
        for t in turns
        if t.role == "user"
        and any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in (t.raw.get("message") or {}).get("content") or []
        )
    )
    assert turns.index(result_turn) == turns.index(tool_turn) + 1
    blocks = (result_turn.raw.get("message") or {}).get("content") or []
    assert any(
        isinstance(b, dict)
        and b.get("type") == "tool_result"
        and b.get("tool_use_id") == "toolu_01JX7K9Q2ABC"
        for b in blocks
    )

    memories = extract_memories(turns, source_path=str(fixture))
    assert memories
    assert all("uvicorn" not in (m.get("body") or "") for m in memories)


def test_golden_questions_content_retention_parity(tmp_path):
    """Migrating the demo session must retain every golden-set answer."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from evaluate_recall import evaluate_content_retention

    archive = ROOT / "demo_source" / "demo_session.jsonl"
    report = evaluate_content_retention(archive, tmp_path / "bundle")
    assert report["before_retention"] == 1.0
    assert report["after_retention"] == 1.0
    assert report["parity"] == 1.0
    assert report["complete_retention"] is True


def test_partial_retention_is_not_reported_as_complete(tmp_path, monkeypatch, capsys):
    """Partial retention must not produce the complete-preservation result."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import evaluate_recall as recall_module

    partial = ["I prefer SQLAlchemy over raw SQL."]
    monkeypatch.setattr(recall_module, "_before_candidates", lambda archive: partial)
    monkeypatch.setattr(
        recall_module, "_after_candidates", lambda archive, bundle: partial
    )

    archive = ROOT / "demo_source" / "demo_session.jsonl"
    exit_code = recall_module.main(
        ["--archive", str(archive), "--bundle", str(tmp_path / "bundle")]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "complete_retention" in captured.out
    assert "CONTENT PRESERVED" not in captured.out
    assert "RETENTION LOST" in captured.out


def test_cli_reports_unreadable_archive(tmp_path, capsys):
    """A missing archive produces a clear error instead of a traceback."""
    missing = tmp_path / "missing.jsonl"
    exit_code = cli_main(["--archive", str(missing), "--output", str(tmp_path / "out")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Failed to read archive" in captured.err
    assert str(missing) in captured.err
