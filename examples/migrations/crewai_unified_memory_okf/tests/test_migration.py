from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EXAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))

import migrate as migrate_module  # noqa: E402
from generate_source import SOURCE_MEMORIES, generate  # noqa: E402
from migrate import (  # noqa: E402
    CrewAIRecord,
    infer_memanto_type,
    read_lancedb_records,
    record_tags,
    row_to_record,
    write_okf_bundle,
)
from validate import validate  # noqa: E402


def _valid_row(**overrides):
    """Build one current CrewAI LanceDB row for validation tests."""

    row = {
        "id": "one",
        "content": "Content",
        "scope": "/misc",
        "categories_str": "[]",
        "metadata_str": "{}",
        "importance": 0.5,
        "created_at": "2026-08-05T00:00:00Z",
        "last_accessed": "2026-08-05T00:00:00Z",
        "source": "agent",
        "private": False,
    }
    row.update(overrides)
    return row


@pytest.fixture(scope="module")
def real_source(tmp_path_factory: pytest.TempPathFactory):
    """Generate one module-scoped store through CrewAI's public API."""

    root = tmp_path_factory.mktemp("crewai-real-source")
    database = root / "crewai-memory"
    evidence = root / "evidence"
    generate(database, evidence)
    return database, evidence


def test_real_crewai_public_api_run_creates_current_lancedb(real_source):
    """Prove source evidence came from the current public Memory API."""

    database, evidence = real_source
    records = read_lancedb_records(database)
    source_run = json.loads((evidence / "source-run.json").read_text("utf-8"))

    assert len(records) == len(SOURCE_MEMORIES) == source_run["record_count"]
    assert source_run["external_llm_calls"] == 0
    assert source_run["public_api_calls"] == [
        "Memory.remember",
        "Memory.list_records",
        "Memory.recall",
    ]
    assert all(record.content and record.id for record in records)


def test_bundle_round_trip_is_exact_and_memanto_consumable(real_source, tmp_path):
    """Require exact source reconstruction and Memanto mapping parity."""

    database, evidence = real_source
    bundle = tmp_path / "bundle"
    reports = tmp_path / "reports"
    records = read_lancedb_records(database)

    manifest = write_okf_bundle(
        records,
        bundle,
        source_database=database,
    )
    report = validate(
        database,
        bundle,
        evidence / "source-run.json",
        reports,
    )

    assert manifest["migration"]["mapped_records"] == len(records)
    assert report["passed"] is True
    assert report["exact_record_hashes"] == len(records)
    assert report["mapping_checks_passed"] == len(records)
    assert report["exact_bundle_match"] is True

    second_bundle = tmp_path / "bundle-again"
    write_okf_bundle(records, second_bundle, source_database=database)
    assert (bundle / "migration-manifest.json").read_bytes() == (
        second_bundle / "migration-manifest.json"
    ).read_bytes()


@pytest.mark.parametrize(
    ("category", "expected", "basis"),
    [
        ("decision", "decision", "category"),
        ("incident", "error", "category"),
        ("insight", "learning", "category"),
        ("unknown", "observation", "fallback"),
    ],
)
def test_type_mapping_is_explicit_and_deterministic(category, expected, basis):
    """Map aliases deterministically and report the selected mapping basis."""

    record = CrewAIRecord(
        id="one",
        content="Content",
        scope="/misc",
        categories=(category,),
        metadata={},
        importance=0.5,
        created_at="2026-08-05T00:00:00Z",
        last_accessed="2026-08-05T00:00:00Z",
        source="agent",
        private=False,
    )
    assert infer_memanto_type(record) == (expected, basis)


@pytest.mark.parametrize(
    ("metadata", "categories", "scope", "expected"),
    [
        (
            {"memory_type": "decision"},
            ("incident",),
            "/goal",
            ("decision", "metadata.memory_type"),
        ),
        ({}, ("incident",), "/goal", ("error", "category")),
    ],
)
def test_type_mapping_precedence(metadata, categories, scope, expected):
    """Enforce metadata-over-category-over-scope precedence."""

    record = CrewAIRecord(
        id="one",
        content="Content",
        scope=scope,
        categories=categories,
        metadata=metadata,
        importance=0.5,
        created_at="2026-08-05T00:00:00Z",
        last_accessed="2026-08-05T00:00:00Z",
        source="agent",
        private=False,
    )
    assert infer_memanto_type(record) == expected


def test_private_records_are_opt_in(tmp_path):
    """Exclude private content from both manifests and written Markdown."""

    public = CrewAIRecord(
        id="public",
        content="Public content",
        scope="/facts",
        categories=("fact",),
        metadata={},
        importance=0.5,
        created_at="2026-08-05T00:00:00Z",
        last_accessed="2026-08-05T00:00:00Z",
        source="agent",
        private=False,
    )
    private = CrewAIRecord(
        id="private",
        content="Private content",
        scope="/facts",
        categories=("fact",),
        metadata={},
        importance=0.5,
        created_at="2026-08-05T00:00:00Z",
        last_accessed="2026-08-05T00:00:00Z",
        source="agent",
        private=True,
    )

    manifest = write_okf_bundle(
        [public, private],
        tmp_path / "public-only",
        source_database=tmp_path / "source",
    )
    assert manifest["migration"]["mapped_records"] == 1
    assert manifest["migration"]["skipped_private"] == 1
    assert [item["crewai_id"] for item in manifest["records"]] == ["public"]
    public_markdown = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "public-only" / "memories").rglob("*.md")
    )
    assert "Private content" not in public_markdown
    assert "visibility-private" not in public_markdown

    manifest_all = write_okf_bundle(
        [public, private],
        tmp_path / "all",
        source_database=tmp_path / "source",
        include_private=True,
    )
    assert manifest_all["migration"]["mapped_records"] == 2
    assert manifest_all["migration"]["skipped_private"] == 0


def test_atomic_publish_restores_previous_bundle_on_failure(tmp_path, monkeypatch):
    """Restore an existing bundle if the final atomic replace fails."""

    output = tmp_path / "bundle"
    output.mkdir()
    sentinel = output / "previous-bundle.txt"
    sentinel.write_text("preserve me", encoding="utf-8")
    record = CrewAIRecord(
        id="public",
        content="Public content",
        scope="/facts",
        categories=("fact",),
        metadata={},
        importance=0.5,
        created_at="2026-08-05T00:00:00Z",
        last_accessed="2026-08-05T00:00:00Z",
        source="agent",
        private=False,
    )
    real_replace = migrate_module.os.replace

    def fail_new_bundle_publish(source, destination):
        """Fail only the new-bundle publish, allowing rollback to proceed."""

        source_path = Path(source)
        destination_path = Path(destination)
        publishing_new_bundle = (
            destination_path == output
            and source_path.name.startswith(f".{output.name}-")
            and "-previous-" not in source_path.name
        )
        if publishing_new_bundle:
            raise OSError("simulated publish failure")
        real_replace(source, destination)

    monkeypatch.setattr(migrate_module.os, "replace", fail_new_bundle_publish)

    with pytest.raises(OSError, match="simulated publish failure"):
        write_okf_bundle(
            [record],
            output,
            source_database=tmp_path / "source",
            force=True,
        )

    assert sentinel.read_text(encoding="utf-8") == "preserve me"


def test_tags_are_bounded_and_deduplicated():
    """Keep generated tags unique and within Memanto bounds."""

    record = CrewAIRecord(
        id="one",
        content="Content",
        scope="/Team With Spaces/" + "x" * 100,
        categories=("Decision", "Decision", "Needs Review"),
        metadata={},
        importance=0.5,
        created_at="2026-08-05T00:00:00Z",
        last_accessed="2026-08-05T00:00:00Z",
        source=None,
        private=False,
    )
    tags = record_tags(record)
    assert len(tags) == len(set(tags))
    assert len(tags) <= 20
    assert all(len(tag) <= 64 and " " not in tag for tag in tags)
    assert not any(tag.endswith("-") for tag in tags)


def test_schema_validation_fails_closed():
    """Reject rows that do not expose the current CrewAI schema."""

    with pytest.raises(ValueError, match="missing columns"):
        row_to_record({"id": "incomplete", "content": "x"})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", ""),
        ("content", ""),
        ("importance", -0.01),
        ("importance", 1.01),
        ("categories_str", "{"),
        ("metadata_str", "["),
        ("created_at", "not-a-date"),
    ],
)
def test_row_validation_rejects_malformed_values(field, value):
    """Cover each independent fail-closed row guard."""

    with pytest.raises(ValueError):
        row_to_record(_valid_row(**{field: value}))


def test_row_normalizes_python_310_iso_variants_and_null_importance():
    """Accept portable ISO variants while defaulting a null importance."""

    record = row_to_record(
        _valid_row(
            importance=None,
            created_at="2026-08-05T01:02:03.123456789+0000",
            last_accessed="2026-08-05T01:02:03.1Z",
        )
    )
    assert record.importance == 0.5
    assert record.created_at == "2026-08-05T01:02:03.123456Z"
    assert record.last_accessed == "2026-08-05T01:02:03.100000Z"
