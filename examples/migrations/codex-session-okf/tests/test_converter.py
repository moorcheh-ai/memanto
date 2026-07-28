from __future__ import annotations

import json
from pathlib import Path

from codex_session_okf import convert_session
from codex_session_okf.converter import redact_text


def _record(role: str, text: str, timestamp: str = "2026-07-29T00:00:00Z") -> str:
    return json.dumps(
        {
            "timestamp": timestamp,
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": role,
                "content": [{"type": "input_text", "text": text}],
            },
        }
    )


def test_exports_only_user_and_assistant_messages(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    source.write_text(
        "\n".join(
            [
                _record("developer", "private instruction"),
                _record("user", "Remember that I prefer concise answers."),
                _record("assistant", "Preference noted."),
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {"type": "function_call", "arguments": "secret"},
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    output = tmp_path / "okf"
    result = convert_session(source, output)

    assert result.input_records == 4
    assert result.message_records == 2
    assert result.exported_memories == 2
    documents = sorted((output / "memories" / "conversation").glob("*.md"))
    bodies = "\n".join(path.read_text(encoding="utf-8") for path in documents)
    assert "concise answers" in bodies
    assert "Preference noted" in bodies
    assert "private instruction" not in bodies
    assert "secret" not in bodies


def test_extracts_bridge_user_input_and_redacts_identifiers() -> None:
    text = """
<bridge_context>{"senderId":"ou_123456789abcdef"}</bridge_context>
<bridge_instructions>internal transport details</bridge_instructions>
<user_input>{"text":"Contact me at user@example.com or +86 131 5710 1023"}</user_input>
"""
    clean, count = redact_text(text)

    assert clean == "Contact me at [REDACTED_EMAIL] or [REDACTED_PHONE]"
    assert count == 2
    assert "bridge" not in clean.lower()


def test_include_filter_and_limit(tmp_path: Path) -> None:
    source = tmp_path / "session.jsonl"
    source.write_text(
        "\n".join(
            [
                _record("user", "alpha"),
                _record("assistant", "beta match"),
                _record("user", "another match"),
            ]
        ),
        encoding="utf-8",
    )

    result = convert_session(
        source,
        tmp_path / "okf",
        include_pattern="match",
        limit=1,
    )

    assert result.exported_memories == 1
    exported = (
        tmp_path / "okf" / "memories" / "conversation" / "001-assistant.md"
    ).read_text(encoding="utf-8")
    assert "beta match" in exported
    assert "another match" not in exported
