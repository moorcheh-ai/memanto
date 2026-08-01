from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

EXAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))

import codex_to_okf  # noqa: E402
import run_demo  # noqa: E402
from codex_to_okf import (  # noqa: E402
    _parse_entry_for_validation,
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
                        "text": (
                            "Remember Project Cedar uses port 8042. Bare token "
                            "sk-abcdefghijklmnop must be removed. Email me at a@b.com."
                        ),
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
                        "text": (
                            "innocent prefix <environment_context>hidden"
                            "</environment_context>"
                        ),
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
        "not valid json",
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
    assert manifest["privacy"]["redactions"]["openai_key"] == 1
    assert manifest["privacy"]["redactions"]["secret_assignment"] == 1
    assert manifest["source"]["unparseable_lines_skipped"] == 1
    assert manifest["selection"]["include_filter_applied"] is True
    assert "include_regex" not in manifest["selection"]

    published = "\n".join(
        path.read_text(encoding="utf-8") for path in output.rglob("*.md")
    )
    assert "Project Cedar" not in published
    assert "a@b.com" not in published
    assert "sk-secret" not in published
    assert "Never export me" not in published
    assert "Private reasoning" not in published
    assert "private tool output" not in published
    for path in (output / "memories" / "conversation").glob("*.md"):
        assert not privacy_findings(_parse_entry_for_validation(path)["_content"])


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


def test_validation_compares_content_hash_with_manifest(tmp_path: Path) -> None:
    source = tmp_path / "rollout.jsonl"
    output = tmp_path / "bundle"
    _rollout(source)
    export_bundle(_export_args(source, output))
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["records"][0]["content_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = validate_bundle(
        argparse.Namespace(source=source, bundle=output, report=None)
    )
    assert report["valid"] is False
    assert report["content_hash_parity"] is False
    assert any(
        "manifest content hash mismatch" in failure for failure in report["failures"]
    )


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


def test_privacy_gate_fails_closed_before_creating_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "rollout.jsonl"
    output = tmp_path / "bundle"
    _rollout(source)
    monkeypatch.setattr(codex_to_okf, "privacy_findings", lambda _text: ["forced"])

    with pytest.raises(ValueError, match="privacy gate rejected"):
        export_bundle(_export_args(source, output))
    assert not output.exists()


def test_force_refuses_to_delete_non_bundle_directory(tmp_path: Path) -> None:
    source = tmp_path / "rollout.jsonl"
    output = tmp_path / "not-a-bundle"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    _rollout(source)
    args = _export_args(source, output)
    args.force = True

    with pytest.raises(ValueError, match="refusing --force"):
        export_bundle(args)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_demo_main_reports_schema_and_exit_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "rollout.jsonl"
    output = tmp_path / "demo"
    _rollout(source)
    common = [
        str(source),
        "--include",
        "Cedar",
        "--max-records",
        "10",
    ]

    assert run_demo.main([*common, "--output", str(output)]) == 0
    dry_run = json.loads(
        (output / "memanto_dry_run_report.json").read_text(encoding="utf-8")
    )
    assert set(dry_run) == {
        "command",
        "executed_at",
        "okf_nodes",
        "mapped_memories",
        "skipped",
        "writes_performed",
        "api_key_required",
    }
    assert dry_run["api_key_required"] is False
    assert dry_run["skipped"] == 0

    monkeypatch.setattr(
        run_demo,
        "validate_bundle",
        lambda _args: {
            "valid": False,
            "source_to_okf_coverage": 1.0,
            "content_hash_parity": False,
            "privacy_gate_findings": 0,
            "golden_qa": None,
        },
    )
    assert run_demo.main([*common, "--output", str(tmp_path / "invalid-demo")]) == 1
