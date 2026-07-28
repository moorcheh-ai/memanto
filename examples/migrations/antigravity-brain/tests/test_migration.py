from __future__ import annotations

import base64
import json
import sys
import zlib
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[1]
if str(EXAMPLE) not in sys.path:
    sys.path.insert(0, str(EXAMPLE))

from migrate_antigravity import (  # noqa: E402
    BUNDLE_SENTINEL,
    SOURCE_MARKER_RE,
    discover_artifacts,
    migrate,
    redact_text,
    stable_session_alias,
)
from reconstruct_antigravity import collect_records, reconstruct  # noqa: E402
from run_live_demo import build_commands, staging_export_path  # noqa: E402


def make_source(
    root: Path, content: str = "# Real task\n\nRemember mint green.\n"
) -> Path:
    session = "11111111-1111-4111-8111-111111111111"
    brain = root / "brain" / session
    brain.mkdir(parents=True)
    (brain / "task.md").write_text(content, encoding="utf-8")
    (brain / "task.md.metadata.json").write_text(
        json.dumps(
            {
                "artifactType": "ARTIFACT_TYPE_TASK",
                "summary": "A real task",
                "updatedAt": "2026-07-28T10:00:00Z",
                "version": "1",
            }
        ),
        encoding="utf-8",
    )
    (brain / "task.md.resolved").write_text("old draft", encoding="utf-8")
    conversations = root / "conversations"
    conversations.mkdir()
    (conversations / f"{session}.pb").write_bytes(bytes(range(256)) * 4)
    return root


def test_discovery_reads_only_canonical_markdown(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source")
    artifacts = discover_artifacts(source)
    assert len(artifacts) == 1
    assert artifacts[0].relative_path.name == "task.md"
    assert artifacts[0].artifact_type == "ARTIFACT_TYPE_TASK"


def test_numbered_revisions_become_ordered_events(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source")
    session = next((source / "brain").iterdir())
    (session / "task.md.resolved.0").write_text("# Earlier task\n", encoding="utf-8")
    artifacts = discover_artifacts(source)
    assert {artifact.relative_path.name for artifact in artifacts} == {
        "task.md",
        "task.md.resolved.0",
    }
    bundle = tmp_path / "bundle"
    report = migrate(source, bundle)
    assert report["type_breakdown"] == {"commitment": 1, "event": 1}


def test_public_redaction_is_deterministic_and_preserves_markdown() -> None:
    text = (
        "Email person@example.com at https://example.com/x.\n"
        "![shot](/C:/Users/alice/private/shot.png)\n"
        "API_KEY=super-secret\n"
    )
    cleaned, counts = redact_text(text)
    assert "person@example.com" not in cleaned
    assert "super-secret" not in cleaned
    assert "![shot]([redacted-path])" in cleaned
    assert counts["email"] == 1
    assert counts["url"] == 1
    assert counts["windows_path"] == 1
    assert counts["secret_assignment"] == 1
    assert stable_session_alias("abc") == stable_session_alias("abc")


def test_okf_maps_and_reconstructs_exact_bytes(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source")
    bundle = tmp_path / "bundle"
    report = migrate(source, bundle)
    assert report["mapped_memories"] == 1
    assert report["type_breakdown"] == {"commitment": 1}

    from memanto.cli.migrate.mappers import map_okf
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    rows = map_okf(load_okf_bundle(bundle))
    assert len(rows) == 1
    assert rows[0]["type"] == "commitment"
    assert "Remember mint green" in rows[0]["content"]

    restored = tmp_path / "restored"
    reconstruction = reconstruct(bundle, restored)
    assert reconstruction["byte_exact"] is True
    source_brain = next((source / "brain").iterdir())
    restored_brain = restored / "brain" / source_brain.name
    assert (restored_brain / "task.md").read_bytes() == (
        source_brain / "task.md"
    ).read_bytes()
    assert (restored_brain / "task.md.metadata.json").read_bytes() == (
        source_brain / "task.md.metadata.json"
    ).read_bytes()


def test_large_artifact_is_chunked_and_reassembled(tmp_path: Path) -> None:
    content = "# Long artifact\n\n" + "abcdef " * 1_400
    source = make_source(tmp_path / "source", content)
    bundle = tmp_path / "bundle"
    report = migrate(source, bundle)
    assert report["mapped_memories"] > 1
    restored = tmp_path / "restored"
    reconstruct(bundle, restored)
    session = next((source / "brain").iterdir()).name
    assert (restored / "brain" / session / "task.md").read_text(
        encoding="utf-8"
    ) == content


def test_tampered_payload_fails_closed(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source")
    bundle = tmp_path / "bundle"
    migrate(source, bundle)
    memory = next(
        path
        for path in bundle.rglob("*.md")
        if path.name != "index.md" and SOURCE_MARKER_RE.search(path.read_text())
    )
    text = memory.read_text(encoding="utf-8")
    match = SOURCE_MARKER_RE.search(text)
    assert match is not None
    record = json.loads(zlib.decompress(base64.b64decode(match.group(1))))
    record["content_sha256"] = "0" * 64
    replacement = base64.b64encode(
        zlib.compress(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode(), 9
        )
    ).decode()
    memory.write_text(
        text[: match.start(1)] + replacement + text[match.end(1) :],
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hash check"):
        reconstruct(bundle, tmp_path / "restored")


def test_path_traversal_payload_is_rejected(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source")
    bundle = tmp_path / "bundle"
    migrate(source, bundle)
    memory = next(
        path
        for path in bundle.rglob("*.md")
        if path.name != "index.md" and SOURCE_MARKER_RE.search(path.read_text())
    )
    text = memory.read_text(encoding="utf-8")
    match = SOURCE_MARKER_RE.search(text)
    assert match is not None
    record = json.loads(zlib.decompress(base64.b64decode(match.group(1))))
    record["relative_path"] = "../escape.md"
    replacement = base64.b64encode(
        zlib.compress(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode(), 9
        )
    ).decode()
    memory.write_text(
        text[: match.start(1)] + replacement + text[match.end(1) :],
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unsafe reconstructed path"):
        collect_records(bundle)
        reconstruct(bundle, tmp_path / "restored")


def test_force_only_replaces_owned_output(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source")
    output = tmp_path / "existing"
    output.mkdir()
    (output / "user-file.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="not created by this tool"):
        migrate(source, output, force=True)
    assert (output / "user-file.txt").read_text(encoding="utf-8") == "keep"

    owned = tmp_path / "owned"
    owned.mkdir()
    (owned / BUNDLE_SENTINEL).write_text("1\n", encoding="utf-8")
    (owned / "stale.txt").write_text("stale", encoding="utf-8")
    migrate(source, owned, force=True)
    assert not (owned / "stale.txt").exists()


def test_live_plan_is_guarded_and_uses_staged_export(tmp_path: Path) -> None:
    executable = tmp_path / "memanto"
    cases = [{"question": "What was chosen?", "expected_phrases": ["mint green"]}]
    staged = staging_export_path("demo-agent", tmp_path / "evidence", tmp_path / "data")
    commands = build_commands(
        executable,
        agent="demo-agent",
        okf_path=tmp_path / "okf",
        export_path=staged,
        cases=cases,
        reuse_agent=False,
        include_answers=True,
    )
    assert [command.label for command in commands] == [
        "create-agent",
        "import-okf",
        "activate-agent",
        "recall-1",
        "answer-1",
        "export-okf",
    ]
    assert commands[3].expected_phrases == ("mint green",)
    assert staged.is_relative_to(tmp_path / "data" / "exports")
    assert all("API_KEY" not in " ".join(command.argv) for command in commands)
