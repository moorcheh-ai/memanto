from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "migrations"
    / "pydanticai-history-okf"
)


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, EXAMPLE / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = _load("pydanticai_okf_adapter", "adapter.py")
reconstruct_module = _load("pydanticai_okf_reconstruct", "reconstruct.py")


def _message_history(content: str = "Use metric units.") -> list[dict]:
    return [
        {
            "parts": [
                {
                    "content": content,
                    "timestamp": "2026-08-11T10:00:00Z",
                    "part_kind": "user-prompt",
                }
            ],
            "timestamp": "2026-08-11T10:00:00Z",
            "instructions": "Keep context.",
            "kind": "request",
            "run_id": "run-1",
            "conversation_id": "conversation-1",
        },
        {
            "parts": [
                {"content": "Recorded.", "part_kind": "text"},
            ],
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "model_name": "test-model",
            "timestamp": "2026-08-11T10:00:01Z",
            "kind": "response",
            "run_id": "run-1",
            "conversation_id": "conversation-1",
        },
    ]


def _write_source(path: Path, messages: list[dict]) -> None:
    path.write_text(json.dumps(messages, ensure_ascii=False) + "\n", "utf-8")


def test_load_rejects_non_array(tmp_path: Path):
    source = tmp_path / "history.json"
    source.write_text("{}", "utf-8")
    with pytest.raises(adapter.MigrationError, match="JSON array"):
        adapter.load_history(source)


@pytest.mark.parametrize(
    "mutation, error",
    [
        (lambda data: data[0].update(kind="unknown"), "unsupported kind"),
        (lambda data: data[0].update(parts={}), "parts must be an array"),
        (lambda data: data[0]["parts"][0].pop("part_kind"), "part_kind"),
    ],
)
def test_load_rejects_malformed_messages(tmp_path: Path, mutation, error: str):
    messages = _message_history()
    mutation(messages)
    source = tmp_path / "history.json"
    _write_source(source, messages)
    with pytest.raises(adapter.MigrationError, match=error):
        adapter.load_history(source)


def test_migration_is_deterministic_and_source_is_unchanged(tmp_path: Path):
    source = tmp_path / "history.json"
    _write_source(source, _message_history())
    original = source.read_bytes()
    first = tmp_path / "first"
    second = tmp_path / "second"

    report_one = adapter.migrate(source, first)
    report_two = adapter.migrate(source, second)

    assert source.read_bytes() == original
    assert report_one == report_two
    manifest_one = json.loads((first / "migration-manifest.json").read_text())
    manifest_two = json.loads((second / "migration-manifest.json").read_text())
    assert manifest_one["files"] == manifest_two["files"]
    assert report_one["source_messages"] == report_one["mapped_memories"] == 2


def test_bundle_reconstructs_every_message(tmp_path: Path):
    messages = _message_history()
    source = tmp_path / "history.json"
    bundle = tmp_path / "okf"
    _write_source(source, messages)
    adapter.migrate(source, bundle)

    reconstructed, report = reconstruct_module.reconstruct(bundle)

    assert reconstructed == messages
    assert report["messages"] == 2
    assert report["matches_manifest"] is True
    assert report["lossless"] is True


def test_memanto_loader_maps_every_document(tmp_path: Path):
    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    source = tmp_path / "history.json"
    bundle = tmp_path / "okf"
    _write_source(source, _message_history())
    adapter.migrate(source, bundle)

    export = load_okf_bundle(bundle)
    rows = map_okf(export)

    assert len(export["memories"]) == len(rows) == 2
    assert rows[0]["source"] == adapter.SOURCE_LABEL
    assert rows[0]["source_ref"].startswith("pydantic-ai://")


def test_secret_scanner_fails_closed_without_leaking_value(tmp_path: Path):
    secret = "sk-" + "example123456789012345678901234"
    source = tmp_path / "history.json"
    _write_source(source, _message_history(f"Never publish {secret}"))

    findings = adapter.scan_history(adapter.load_history(source).messages)
    assert findings[0].category == "openai_api_key"
    assert secret not in json.dumps([finding.__dict__ for finding in findings])
    with pytest.raises(adapter.MigrationError, match="sensitive values detected"):
        adapter.migrate(source, tmp_path / "okf")
    assert not (tmp_path / "okf").exists()


def test_secret_scanner_distinguishes_providers_and_named_fields(tmp_path: Path):
    anthropic_key = "sk-ant-" + "example123456789012345678901234"
    messages = _message_history(f"Never publish {anthropic_key}")
    messages[0]["metadata"] = {"api_key": "provider-specific-value"}
    source = tmp_path / "history.json"
    _write_source(source, messages)

    findings = adapter.scan_history(adapter.load_history(source).messages)
    categories = [finding.category for finding in findings]
    assert categories.count("anthropic_api_key") == 1
    assert "openai_api_key" not in categories
    assert categories.count("named_secret_field") == 1

    bundle = tmp_path / "redacted"
    report = adapter.migrate(source, bundle, redact=True)
    archived = (bundle / "source" / "history.json").read_text()
    assert anthropic_key not in archived
    assert "provider-specific-value" not in archived
    assert report["privacy"]["redaction_count"] == 2


def test_redaction_is_explicitly_non_lossless(tmp_path: Path):
    source = tmp_path / "history.json"
    _write_source(
        source,
        _message_history("Contact migration-owner@example.com before release."),
    )
    bundle = tmp_path / "okf"

    report = adapter.migrate(source, bundle, redact=True)

    assert report["lossless"] is False
    assert report["privacy"]["redaction_count"] == 1
    assert (
        "migration-owner@example.com"
        not in (bundle / "source" / "history.json").read_text()
    )
    assert "[REDACTED:email]" in (bundle / "source" / "history.json").read_text()


def test_loader_delimiter_is_escaped_only_in_readable_body(tmp_path: Path):
    content = f"Keep this literal marker: {adapter.ENTRY_DELIMITER}"
    messages = _message_history(content)
    source = tmp_path / "history.json"
    bundle = tmp_path / "okf"
    _write_source(source, messages)
    adapter.migrate(source, bundle)

    memory = next((bundle / "memories" / "request").glob("*.md"))
    sidecar = json.loads((bundle / "source" / "messages" / "0000.json").read_text())
    assert adapter.ENTRY_DELIMITER not in memory.read_text()
    assert adapter.ENTRY_DELIMITER in sidecar["parts"][0]["content"]


def test_unknown_parts_are_reported_and_preserved(tmp_path: Path):
    messages = _message_history()
    messages[1]["parts"] = [
        {"part_kind": "future-provider-part", "opaque": {"value": 42}}
    ]
    source = tmp_path / "history.json"
    bundle = tmp_path / "okf"
    _write_source(source, messages)

    report = adapter.migrate(source, bundle)
    reconstructed, _ = reconstruct_module.reconstruct(bundle)

    assert report["omitted_human_readable_part_counts"] == {"future-provider-part": 1}
    assert reconstructed[1]["parts"][0]["opaque"] == {"value": 42}


def test_refuses_to_replace_foreign_output_directory(tmp_path: Path):
    source = tmp_path / "history.json"
    output = tmp_path / "existing"
    output.mkdir()
    (output / "owner.txt").write_text("do not replace", "utf-8")
    _write_source(source, _message_history())

    with pytest.raises(adapter.MigrationError, match="non-adapter directory"):
        adapter.migrate(source, output, force=True)
    assert (output / "owner.txt").read_text() == "do not replace"


def test_refuses_file_and_symlink_output_paths(tmp_path: Path):
    source = tmp_path / "history.json"
    _write_source(source, _message_history())
    output_file = tmp_path / "output"
    output_file.write_text("preserve me", "utf-8")
    with pytest.raises(adapter.MigrationError, match="not a directory"):
        adapter.migrate(source, output_file)
    assert output_file.read_text() == "preserve me"

    real_output = tmp_path / "real-output"
    real_output.mkdir()
    symlink = tmp_path / "linked-output"
    symlink.symlink_to(real_output, target_is_directory=True)
    with pytest.raises(adapter.MigrationError, match="symlink"):
        adapter.migrate(source, symlink)


def test_committed_sample_is_importable_reconstructable_and_private():
    source = EXAMPLE / "sample" / "source" / "history.json"
    bundle = EXAMPLE / "sample" / "okf"
    if not source.exists():
        pytest.skip("sample artifacts have not been generated yet")

    history = adapter.load_history(source)
    reconstructed, report = reconstruct_module.reconstruct(bundle)
    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    rows = map_okf(load_okf_bundle(bundle))
    source_report = json.loads(
        (EXAMPLE / "sample" / "evidence" / "source-run.json").read_text()
    )
    assert len(history.messages) == len(reconstructed) == len(rows) == 20
    assert report["matches_manifest"] is True
    assert adapter.scan_history(history.messages) == []
    assert source_report["official_schema_round_trip"] is True
