from __future__ import annotations

import base64
import json
import sys
import zlib
from pathlib import Path, PurePosixPath

import pytest

EXAMPLE = Path(__file__).resolve().parents[1]
if str(EXAMPLE) not in sys.path:
    sys.path.insert(0, str(EXAMPLE))

from migrate_antigravity import (  # noqa: E402
    BUNDLE_SENTINEL,
    SOURCE_MARKER_RE,
    Artifact,
    discover_artifacts,
    migrate,
    redact_text,
    render_artifact,
    stable_session_alias,
)
from prepare_public_sample import (  # noqa: E402
    SAMPLE_SENTINEL,
    prepare_sample,
)
from reconstruct_antigravity import (  # noqa: E402
    MAX_DECODED_MARKER_BYTES,
    _decode_record,
    collect_records,
    reconstruct,
)
from run_demo import display_bundle_path  # noqa: E402
from run_live_demo import build_commands, staging_export_path  # noqa: E402

SESSION_ID = "11111111-1111-4111-8111-111111111111"


def make_source(
    root: Path, content: str = "# Real task\n\nRemember mint green.\n"
) -> Path:
    brain = root / "brain" / SESSION_ID
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
    (conversations / f"{SESSION_ID}.pb").write_bytes(bytes(range(256)) * 4)
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
        "Acme Corp Inc\n"
    )
    cleaned, counts = redact_text(
        text, {"Acme": "[company]", "Acme Corp Inc": "[full-company]"}
    )
    assert "person@example.com" not in cleaned
    assert "super-secret" not in cleaned
    assert "![shot]([redacted-path])" in cleaned
    assert "[full-company]" in cleaned
    assert "Corp Inc" not in cleaned
    assert counts["email"] == 1
    assert counts["url"] == 1
    assert counts["windows_path"] == 1
    assert counts["secret_assignment"] == 1
    assert stable_session_alias("abc") == stable_session_alias("abc")


def test_rendered_memory_replaces_nonportable_image_links() -> None:
    artifact = Artifact(
        session_id=SESSION_ID,
        relative_path=PurePosixPath("brain") / SESSION_ID / "walkthrough.md",
        content=b"# Walkthrough\n\n![Private screenshot](/local-image.png)\n",
        metadata_name=None,
        metadata=None,
        artifact_type="ARTIFACT_TYPE_WALKTHROUGH",
        updated_at=None,
    )
    rendered = render_artifact(artifact)
    assert "![Private screenshot]" not in rendered[0].text
    assert "[Image omitted from portable view: Private screenshot]" in rendered[0].text


def test_rendered_memory_budget_includes_frontmatter() -> None:
    artifact = Artifact(
        session_id=SESSION_ID,
        relative_path=PurePosixPath("brain") / SESSION_ID / ("a" * 5_000 + ".md"),
        content=b"small body",
        metadata_name=None,
        metadata=None,
        artifact_type="ARTIFACT_TYPE_UNKNOWN",
        updated_at=None,
    )
    with pytest.raises(ValueError, match="content budget"):
        render_artifact(artifact)


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
    assert rows[0]["source"] == "tool"
    assert "Remember mint green" in rows[0]["content"]

    from memanto.app.core import MemoryRecord

    MemoryRecord(**rows[0], agent_id="test-agent", actor_id="test-actor")

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


def test_reconstruction_ignores_okf_derived_session_views(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source")
    bundle = tmp_path / "bundle"
    migrate(source, bundle)
    memory = next(
        path
        for path in bundle.rglob("*.md")
        if path.name != "index.md" and SOURCE_MARKER_RE.search(path.read_text())
    )
    sessions = bundle / "sessions"
    sessions.mkdir()
    sessions.joinpath("summary.md").write_text(
        "> " + memory.read_text(encoding="utf-8").replace("\n", "\n> "),
        encoding="utf-8",
    )

    records = collect_records(bundle)
    assert len(records) == 1
    reconstruction = reconstruct(bundle, tmp_path / "restored")
    assert reconstruction["byte_exact"] is True


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


def test_oversized_marker_is_rejected_before_json_decode() -> None:
    encoded = base64.b64encode(
        zlib.compress(b"x" * (MAX_DECODED_MARKER_BYTES + 1), 9)
    ).decode()
    with pytest.raises(ValueError, match="Invalid Antigravity source marker"):
        _decode_record(encoded, Path("memory.md"))


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
    with pytest.raises(ValueError, match="Unsafe reconstructed path"):
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


def test_public_sample_force_preserves_previous_output_on_failure(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path / "source")
    output = tmp_path / "public-sample"
    output.mkdir()
    (output / SAMPLE_SENTINEL).write_text("1\n", encoding="utf-8")
    (output / "known-good.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="must not be empty"):
        prepare_sample(
            source,
            output,
            conversation=SESSION_ID,
            custom_redactions={"": "invalid"},
            force=True,
        )

    assert (output / "known-good.txt").read_text(encoding="utf-8") == "keep"


def test_public_sample_pseudonymizes_attachment_filenames(tmp_path: Path) -> None:
    source = make_source(tmp_path / "source")
    attachment = source / "brain" / SESSION_ID / "private-project-1234567890.png"
    attachment.write_bytes(b"private image bytes")
    report = prepare_sample(source, tmp_path / "public-sample", conversation=SESSION_ID)

    row = report["attachment_provenance"][0]
    assert row["filename"].startswith("attachment-")
    assert row["filename"].endswith(".png")
    assert "private-project" not in row["filename"]


def test_display_bundle_path_tracks_custom_output(tmp_path: Path) -> None:
    assert display_bundle_path(EXAMPLE / "custom" / "okf") == "custom/okf"
    external = tmp_path / "okf"
    assert display_bundle_path(external) == external.as_posix()


def test_live_plan_is_guarded_and_uses_staged_export(tmp_path: Path) -> None:
    executable = tmp_path / "memanto"
    cases = [
        {
            "question": "What was chosen?",
            "expected_phrases": ["mint green"],
            "recall_expected_phrases": ["Walkthrough revision 3"],
        }
    ]
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
    assert commands[3].expected_phrases == ("Walkthrough revision 3",)
    assert staged.is_relative_to(tmp_path / "data" / "exports")
    assert all("API_KEY" not in " ".join(command.argv) for command in commands)
