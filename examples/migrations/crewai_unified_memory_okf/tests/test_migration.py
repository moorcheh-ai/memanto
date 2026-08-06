from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EXAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))

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


@pytest.fixture(scope="module")
def real_source(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("crewai-real-source")
    database = root / "crewai-memory"
    evidence = root / "evidence"
    generate(database, evidence)
    return database, evidence


def test_real_crewai_public_api_run_creates_current_lancedb(real_source):
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


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("decision", "decision"),
        ("incident", "error"),
        ("insight", "learning"),
        ("unknown", "observation"),
    ],
)
def test_type_mapping_is_explicit_and_deterministic(category, expected):
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
    assert infer_memanto_type(record)[0] == expected


def test_private_records_are_opt_in(tmp_path):
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

    manifest_all = write_okf_bundle(
        [public, private],
        tmp_path / "all",
        source_database=tmp_path / "source",
        include_private=True,
    )
    assert manifest_all["migration"]["mapped_records"] == 2
    assert manifest_all["migration"]["skipped_private"] == 0


def test_tags_are_bounded_and_deduplicated():
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


def test_schema_validation_fails_closed():
    with pytest.raises(ValueError, match="missing columns"):
        row_to_record({"id": "incomplete", "content": "x"})
