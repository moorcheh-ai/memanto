from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))

from codex_to_okf import (  # noqa: E402
    export_bundle,
    iter_message_records,
    privacy_findings,
    redact_text,
    validate_bundle,
)


def _line(timestamp: str, item_type: str, payload: dict) -> str:
    return json.dumps(
        {"timestamp": timestamp, "type": item_type, "payload": payload},
        ensure_ascii=False,
    )


def _rollout(path: Path) -> None:
    lines = [
        _line(
            "2026-08-01T12:00:00Z",
            "session_meta",
            {"session_id": "real-session-1", "cli_version": "1.2.3"},
        ),
        _line(
            "2026-08-01T12:00:01Z",
            "response_item",
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "Never export me"}],
            },
        ),
        _line(
            "2026-08-01T12:00:02Z",
            "response_item",
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Remember Project Cedar uses port 8042. Email me at a@b.com.",
                    },
                    {"type": "input_image", "image_url": "data:private"},
                ],
            },
        ),
        _line(
            "2026-08-01T12:00:03Z",
            "response_item",
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            "Saved the Cedar decision. OPENAI_API_KEY="
                            + "sk-"
                            + "secretsecretsecret"
                        ),
                    }
                ],
            },
        ),
        _line(
            "2026-08-01T12:00:04Z",
            "response_item",
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": '<codex_internal_context source="goal">hidden</codex_internal_context>',
                    }
                ],
            },
        ),
        _line(
            "2026-08-01T12:00:05Z",
            "response_item",
            {"type": "reasoning", "summary": [{"text": "Private reasoning"}]},
        ),
        _line(
            "2026-08-01T12:00:06Z",
            "response_item",
            {"type": "function_call_output", "output": "private tool output"},
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _export_args(source: Path, output: Path) -> argparse.Namespace:
    return argparse.Namespace(
        source=source,
        output=output,
        roles=["user", "assistant"],
        include="Cedar",
        exclude=None,
        max_records=10,
        take="last",
        redact_literal=["Project Cedar"],
        force=False,
    )


def test_exports_only_public_messages_and_redacts(tmp_path: Path) -> None:
    source = tmp_path / "rollout.jsonl"
    output = tmp_path / "bundle"
    _rollout(source)

    records = list(iter_message_records(source))
    assert len(records) == 2
    assert {record.role for record in records} == {"user", "assistant"}

    manifest = export_bundle(_export_args(source, output))
    assert manifest["selection"]["selected"] == 2
    assert manifest["privacy"]["raw_text_published"] is False
    assert manifest["privacy"]["literal_values_persisted"] is False
    assert manifest["privacy"]["redactions"]["literal"] == 1
    assert manifest["privacy"]["redactions"]["email"] == 1
    assert manifest["privacy"]["redactions"]["secret_assignment"] == 1

    published = "\n".join(
        path.read_text(encoding="utf-8") for path in output.rglob("*.md")
    )
    assert "Project Cedar" not in published
    assert "a@b.com" not in published
    assert "sk-secret" not in published
    assert "Never export me" not in published
    assert "Private reasoning" not in published
    assert "private tool output" not in published
    assert not privacy_findings(published)


def test_validation_proves_source_and_content_parity(tmp_path: Path) -> None:
    source = tmp_path / "rollout.jsonl"
    output = tmp_path / "bundle"
    report_path = tmp_path / "report.json"
    _rollout(source)
    manifest = export_bundle(_export_args(source, output))
    user_record = next(row for row in manifest["records"] if row["role"] == "user")
    (output / "golden_questions.json").write_text(
        json.dumps(
            {
                "questions": [
                    {
                        "id": "cedar-port",
                        "question": "What port does Project Cedar use?",
                        "expected_source_record_sha256": user_record[
                            "source_record_sha256"
                        ],
                        "answer_contains": "port 8042",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = validate_bundle(
        argparse.Namespace(source=source, bundle=output, report=report_path)
    )
    assert report["valid"] is True
    assert report["source_to_okf_coverage"] == 1.0
    assert report["content_hash_parity"] is True
    assert report["privacy_gate_findings"] == 0
    assert report["golden_qa"]["questions"] == 1
    assert report["golden_qa"]["fully_correct"] == 1
    assert report["golden_qa"]["recall_parity_score"] == 1.0
    assert json.loads(report_path.read_text(encoding="utf-8"))["valid"] is True


def test_validation_detects_tampering(tmp_path: Path) -> None:
    source = tmp_path / "rollout.jsonl"
    output = tmp_path / "bundle"
    _rollout(source)
    export_bundle(_export_args(source, output))
    entry = next((output / "memories" / "conversation").glob("*.md"))
    entry.write_text(entry.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    report = validate_bundle(
        argparse.Namespace(source=source, bundle=output, report=None)
    )
    assert report["valid"] is False
    assert any("content hash mismatch" in failure for failure in report["failures"])
    assert any("bundle digest" in failure for failure in report["failures"])


def test_redaction_handles_tokens_accounts_and_home_paths() -> None:
    text = (
        "token " + "gho_" + "abcdefghijklmnopqrstuvwxyz123456 and wallet "
        "CDwfgnTvm7HfBDmqSSsjWTxEM48fQwdqtExtYg8Def2z at C:\\Users\\Alice\\repo"
    )
    redacted, counts = redact_text(text)
    assert "gho_" not in redacted
    assert "CDwfgn" not in redacted
    assert "Alice" not in redacted
    assert counts == {"base58_account": 1, "github_token": 1, "user_home": 1}
    assert not privacy_findings(redacted)
