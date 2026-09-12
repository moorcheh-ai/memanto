"""Offline tests for the LangMem -> OKF migration path.

No network, no API keys needed. Covers the two things that matter most:

1. The pipeline produces a bundle that Memanto's own loader + mapper accept,
   with no memory lost and correct provenance/source stamping.
2. The before/after recall check reports full parity on the sample data.

Run:  pytest examples/migrations/langmem/tests -q
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langmem_migration import validate as V
from langmem_migration.adapter import write_okf_bundle
from langmem_migration.export import export_store
from langmem_migration.mapping import VALID_MEMORY_TYPES, classify, map_record
from langmem_migration.populate import build_store_replay


@pytest.fixture(scope="module")
def store():
    return build_store_replay()


@pytest.fixture(scope="module")
def export(store):
    return export_store(store)


def test_langmem_store_has_expected_live_memories(export):
    # 12 create ops, 1 delete (the fulfilled ADR to-do) => 10 survive.
    assert export["count"] == 10
    contents = " ".join(m["value"]["content"] for m in export["memories"]).lower()
    # Correction applied in place, not duplicated:
    assert "vitest" in contents
    # Deleted commitment is gone:
    assert "write an adr" not in contents
    # Superseded plan revised:
    assert "single-currency" in contents or "single currency" in contents


def test_adapter_types_are_all_valid_memanto_types():
    # The local mirror of VALID_MEMORY_TYPES must match memanto's source of truth.
    from memanto.app.constants import VALID_MEMORY_TYPES as CANON

    assert VALID_MEMORY_TYPES == CANON
    for record_content in ["Alex prefers dark mode", "some unclassifiable text xyz"]:
        assert classify(record_content) in CANON


def test_bundle_loads_back_through_memanto_loader(export, tmp_path: Path):
    from memanto.cli.migrate.mappers import map_okf, type_breakdown
    from memanto.cli.migrate.okf_loader import load_okf_bundle

    bundle = tmp_path / "okf-bundle"
    summary = write_okf_bundle(export, bundle, agent_id="test-agent")

    assert summary["mapped_count"] == export["count"]

    reloaded = load_okf_bundle(bundle)
    rows = map_okf(reloaded)

    # No memory lost in the LangMem -> OKF -> Memanto round trip.
    assert len(rows) == export["count"]
    # Type breakdown from the bundle matches what the adapter reported.
    assert type_breakdown(rows) == summary["type_counts"]
    # Provenance + source survive for every migrated memory.
    assert all(r["source"] == "langmem" for r in rows)
    assert all(r["provenance"] == "imported" for r in rows)
    # Temporal fidelity: timestamps are carried through.
    assert all(r["created_at"] is not None for r in rows)


def test_mapping_is_lossless_for_custom_schema_fields():
    # A LangMem memory with extra (custom-schema) fields keeps them in a footer.
    record = {
        "namespace": ["memories", "alex"],
        "key": "k1",
        "value": {"content": "Alex likes espresso", "importance": "high"},
        "created_at": "2026-06-01T00:00:00+00:00",
    }
    row = map_record(record)
    assert "espresso" in row["content"]
    assert "importance" in row["content"]  # preserved in [Supporting data]
    assert row["source_ref"] == "langmem:k1"


def test_recall_parity_is_full_on_sample(store, export):
    report = V.validate(store, export, after="bundle")
    assert report["before_pass"] == report["n"]
    assert report["after_pass"] == report["n"]
    assert report["parity_pct"] == 100.0
