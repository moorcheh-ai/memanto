from __future__ import annotations

import importlib.util
import json
import subprocess
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
run_demo_module = _load("pydanticai_okf_run_demo", "run_demo.py")


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


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_load_rejects_non_finite_numbers(tmp_path: Path, constant: str):
    source = tmp_path / "history.json"
    source.write_text(
        '[{"kind":"request","parts":['
        '{"part_kind":"user-prompt","content":'
        f"{constant}"
        "}]}]",
        "utf-8",
    )

    with pytest.raises(adapter.MigrationError, match="non-finite JSON number"):
        adapter.load_history(source)
    with pytest.raises(ValueError, match="Out of range float values"):
        adapter.canonical_json([float("nan")])


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


@pytest.mark.parametrize(
    "structured_secret",
    [
        {"value": "opaque-secret"},
        ["opaque-secret", {"nested": "value"}],
    ],
)
def test_sensitive_named_fields_redact_structured_values(
    tmp_path: Path,
    structured_secret: object,
):
    messages = _message_history()
    messages[0]["metadata"] = {"api_key": structured_secret}
    source = tmp_path / "history.json"
    _write_source(source, messages)

    findings = adapter.scan_history(adapter.load_history(source).messages)
    assert [finding.category for finding in findings] == ["named_secret_field"]

    bundle = tmp_path / "redacted"
    report = adapter.migrate(source, bundle, redact=True)
    archived = json.loads((bundle / "source" / "history.json").read_text())
    assert archived[0]["metadata"]["api_key"] == "[REDACTED:named_secret_field]"
    assert report["privacy"]["redaction_count"] == 1


def test_secret_scanner_and_redactor_handle_sensitive_dictionary_keys(
    tmp_path: Path,
):
    secret_key = "sk-" + "keyinsideobjectname123456789012345"
    email_key = "migration-owner@example.com"
    messages = _message_history()
    messages[0]["metadata"] = {secret_key: "secret-key-value", email_key: "pii-key"}
    source = tmp_path / "history.json"
    _write_source(source, messages)

    findings = adapter.scan_history(adapter.load_history(source).messages)
    categories = {finding.category for finding in findings}
    serialized_findings = json.dumps([finding.__dict__ for finding in findings])
    assert {"openai_api_key", "email"} <= categories
    assert secret_key not in serialized_findings
    assert email_key not in serialized_findings
    assert all("<redacted-key:" in finding.path for finding in findings)

    bundle = tmp_path / "redacted"
    report = adapter.migrate(source, bundle, redact=True)
    archived = (bundle / "source" / "history.json").read_text()
    assert secret_key not in archived
    assert email_key not in archived
    assert "[REDACTED:openai_api_key_key:" in archived
    assert "[REDACTED:email_key:" in archived
    assert report["privacy"]["redaction_count"] == 2


def test_tool_titles_use_plain_heading_and_keep_rendered_details():
    message = {
        "kind": "response",
        "parts": [
            {
                "part_kind": "tool-call",
                "tool_name": "lookup_bounty",
                "tool_call_id": "lookup-1",
                "args": {"nested": "value" * 30},
            }
        ],
    }

    rendered = adapter.render_message(message, 0)

    assert rendered.title == "Response 001 · Tool call · lookup_bounty"
    assert "`" not in rendered.title
    assert "```json" in rendered.body


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


def test_refuses_embedded_or_symlinked_ownership_markers(tmp_path: Path):
    source = tmp_path / "history.json"
    _write_source(source, _message_history())

    embedded = tmp_path / "embedded-marker"
    embedded.mkdir()
    (embedded / "index.md").write_text(
        f"Project notes\n{adapter.GENERATOR_MARKER}\n", "utf-8"
    )
    (embedded / "owner.txt").write_text("preserve me", "utf-8")
    with pytest.raises(adapter.MigrationError, match="non-adapter directory"):
        adapter.migrate(source, embedded, force=True)
    assert (embedded / "owner.txt").read_text() == "preserve me"

    marker_target = tmp_path / "outside-index.md"
    marker_target.write_text(f"{adapter.GENERATOR_MARKER}\n", "utf-8")
    linked = tmp_path / "linked-marker"
    linked.mkdir()
    (linked / "index.md").symlink_to(marker_target)
    (linked / "owner.txt").write_text("preserve me", "utf-8")
    with pytest.raises(adapter.MigrationError, match="non-adapter directory"):
        adapter.migrate(source, linked, force=True)
    assert (linked / "owner.txt").read_text() == "preserve me"
    assert marker_target.read_text() == f"{adapter.GENERATOR_MARKER}\n"


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


@pytest.mark.parametrize("kind", ["absolute", "traversal", "symlink"])
def test_reconstruct_rejects_manifest_paths_outside_bundle(tmp_path: Path, kind: str):
    source = tmp_path / "history.json"
    bundle = tmp_path / "okf"
    outside = tmp_path / "outside.json"
    outside.write_text("outside", "utf-8")
    _write_source(source, _message_history())
    adapter.migrate(source, bundle)

    if kind == "absolute":
        malicious_path = str(outside.resolve())
        expected_error = "absolute manifest path"
    elif kind == "traversal":
        malicious_path = "../outside.json"
        expected_error = "escapes bundle"
    else:
        link = bundle / "linked-outside.json"
        link.symlink_to(outside)
        malicious_path = "linked-outside.json"
        expected_error = "escapes bundle"

    manifest_path = bundle / "migration-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][malicious_path] = "unused"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), "utf-8")

    with pytest.raises(reconstruct_module.ReconstructionError, match=expected_error):
        reconstruct_module.reconstruct(bundle)


def test_demo_child_timeout_preserves_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def timeout(*_args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["blocked"], timeout=kwargs["timeout"], output=b"partial output\n"
        )

    monkeypatch.setattr(run_demo_module.subprocess, "run", timeout)
    transcript: list[str] = []

    with pytest.raises(SystemExit) as exc:
        run_demo_module.run(
            ["blocked"],
            cwd=tmp_path,
            transcript=transcript,
            timeout_seconds=0.25,
        )

    assert exc.value.code == 124
    assert "partial output" in "".join(transcript)
    assert "timed out after 0.25 seconds" in "".join(transcript)


def test_demo_selects_only_preview_matching_current_bundle(tmp_path: Path):
    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    source = tmp_path / "history.json"
    bundle = tmp_path / "okf"
    run_root = tmp_path / "runs"
    stale = run_root / "old" / "mapped_preview.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("[]", "utf-8")
    _write_source(source, _message_history())
    adapter.migrate(source, bundle)

    before = run_demo_module.preview_snapshot(run_root)
    current = run_root / "current" / "mapped_preview.json"
    current.parent.mkdir()
    expected = map_okf(load_okf_bundle(bundle))
    current.write_text(json.dumps(expected, ensure_ascii=False, default=str), "utf-8")

    selected = run_demo_module.select_invocation_preview(run_root, before, bundle)

    assert selected == current.resolve()


def test_generated_source_is_byte_reproducible(tmp_path: Path):
    pytest.importorskip("pydantic_ai")
    generator = _load("pydanticai_okf_generate_source", "generate_source.py")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    first_report = generator.generate(first, tmp_path / "first-report.json")
    second_report = generator.generate(second, tmp_path / "second-report.json")

    assert first.read_bytes() == second.read_bytes()
    assert first_report["source_sha256"] == second_report["source_sha256"]


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
