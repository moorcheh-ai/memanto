"""Tests for the Claude export loader (JSONL parsing + turn ordering)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.claude import load_claude  # noqa: E402


def _line(role, text, ts=None):
    line = {
        "type": role,
        "message": {"role": role, "content": [{"type": "text", "text": text}]},
    }
    if ts is not None:
        line["timestamp"] = ts
    return line


def _write_export(tmp_path, uuid="abc123", lines=None, index=True):
    d = tmp_path / "claude"
    d.mkdir(parents=True, exist_ok=True)
    if index:
        (d / "conversations.json").write_text(
            json.dumps([{"uuid": uuid, "name": "Memory test", "created_at": "2026-01-01T00:00:00Z"}]),
            encoding="utf-8")
    with (d / f"{uuid}.jsonl").open("w", encoding="utf-8") as f:
        for line in lines or []:
            f.write(json.dumps(line) + "\n")
    return tmp_path


def test_undated_turns_sort_after_dated_keeping_jsonl_order(tmp_path):
    """Dated turns first (chronological); undated turns after, in original
    JSONL order — a missing timestamp must never sort before real dates."""
    lines = [
        _line("user", "I prefer Postgres over MySQL.", ts=200.0),
        _line("assistant", "Noted.", ts=None),        # undated #1
        _line("user", "We decided to migrate to Postgres 16.", ts=None),  # undated #2
        _line("user", "I prefer offline docs.", ts=100.0),
    ]
    export = _write_export(tmp_path, lines=lines)
    result = load_claude(export)[0]
    texts = [t["text"] for t in result["turns"]]
    assert texts == [
        "I prefer offline docs.",                    # dated, earlier ts first
        "I prefer Postgres over MySQL.",             # dated, later ts second
        "Noted.",                                    # undated after dated
        "We decided to migrate to Postgres 16.",     # undated, JSONL order kept
    ]
    assert [t["ts"] for t in result["turns"][2:]] == [None, None]


def test_parse_without_index_falls_back_to_jsonl(tmp_path):
    """Exports without conversations.json still parse (filename stem as uuid)."""
    lines = [_line("user", "I prefer Postgres.", ts=1.0)]
    export = _write_export(tmp_path, lines=lines, index=False)
    result = load_claude(export)[0]
    assert result["turns"][0]["text"] == "I prefer Postgres."
    assert result["title"].startswith("conversation-")
