"""Tests for the Claude Code conversation memory adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from claude_code_adapter.parser import parse_claude_jsonl, ConversationTurn
from claude_code_adapter.extractor import extract_memories
from claude_code_adapter.okf_writer import write_okf_bundle


def _line(obj: dict) -> str:
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
    archive.write_text("\n".join(_line(l) for l in lines), encoding="utf-8")
    return archive


def test_parse_skips_snapshots_and_last_prompt(tmp_path):
    archive = _sample_turns(tmp_path)
    turns = parse_claude_jsonl(archive)
    assert len(turns) == 3  # 2 user + 1 assistant
    assert all(t.role in {"user", "assistant"} for t in turns)
    assert turns[0].cwd == r"I:\project\payments-api"
    assert turns[0].git_branch == "main"
    assert turns[1].tool_uses == []


def test_parse_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_claude_jsonl(tmp_path / "missing.jsonl")


def test_extract_user_preferences_and_instructions(tmp_path):
    archive = _sample_turns(tmp_path)
    turns = parse_claude_jsonl(archive)
    memories = extract_memories(turns, source_path=str(archive))
    types = {m["type"] for m in memories}
    assert "preference" in types
    assert "instruction" in types
    assert all(m["x_memanto"]["source"] == "claude-code" for m in memories)
    assert all(m["x_memanto"]["provenance"] == "imported" for m in memories)


def test_extract_includes_assistant_decisions_by_default(tmp_path):
    archive = _sample_turns(tmp_path)
    turns = parse_claude_jsonl(archive)
    memories = extract_memories(turns, source_path=str(archive))
    decision = [m for m in memories if m["type"] == "decision"]
    assert decision, "assistant decision should be extracted by default"


def test_user_only_skips_assistant(tmp_path):
    archive = _sample_turns(tmp_path)
    turns = parse_claude_jsonl(archive)
    memories = extract_memories(turns, include_assistant=False)
    assert all(m["x_memanto"]["confidence"] >= 0.9 for m in memories)
    assert all("decided" not in m["body"] for m in memories)


def test_write_okf_bundle_roundtrip(tmp_path):
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
    md_files = [
        p
        for p in (bundle / "memories").rglob("*.md")
        if p.name != "index.md"
    ]
    assert md_files
    sample = md_files[0].read_text(encoding="utf-8")
    assert sample.startswith("---\n")
    assert "x_memanto:" in sample
    assert "source: claude-code" in sample


def test_okf_bundle_loadable_by_memanto_loader(tmp_path):
    """The bundle should be parseable by memanto's own OKF loader."""
    try:
        from memanto.cli.migrate.okf_loader import load_okf_bundle
    except ImportError:
        pytest.skip("memanto package not importable in this environment")

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
    sys.path.insert(0, str(ROOT / "scripts"))
    from generate_demo_session import generate_session

    archive = generate_session(tmp_path / "demo_session.jsonl")
    turns = parse_claude_jsonl(archive)
    assert len(turns) >= 8
    memories = extract_memories(turns)
    assert len(memories) >= 5
    types = {m["type"] for m in memories}
    assert {"preference", "instruction", "decision"}.issubset(types)
