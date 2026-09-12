"""Tests for the Hindsight → OKF migration adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_sample_archive import build_archive_bytes  # noqa: E402
from hindsight_mapper import (  # noqa: E402
    export_hindsight_to_okf,
    hindsight_to_memories_by_type,
    parse_hindsight_archive,
)
from memanto.cli.migrate.mappers import map_okf  # noqa: E402
from memanto.cli.migrate.okf_loader import load_okf_bundle  # noqa: E402


def test_parse_sample_archive():
    archive = parse_hindsight_archive(build_archive_bytes())
    assert archive.manifest["schema_version"] == 1
    assert archive.manifest["source_bank_id"] == "project-atlas-agent"
    assert len(archive.documents) == 2
    assert len(archive.observations) == 1


def test_maps_facts_and_observations():
    archive = parse_hindsight_archive(build_archive_bytes())
    buckets = hindsight_to_memories_by_type(archive)
    total = sum(len(v) for v in buckets.values())
    assert total == 6  # 5 facts + 1 observation
    assert "preference" in buckets
    assert "observation" in buckets


def test_okf_round_trip(tmp_path):
    okf_dir = tmp_path / "okf"
    result = export_hindsight_to_okf(build_archive_bytes(), okf_dir, agent_id="test-agent")
    assert result["total_memories"] == 6
    assert (okf_dir / "index.md").exists()

    rows = map_okf(load_okf_bundle(okf_dir))
    assert len(rows) == 6
    jwt_rows = [r for r in rows if "jwt" in r["content"].lower()]
    assert jwt_rows, "expected JWT decision to survive OKF import mapping"


def test_migration_summary_fields():
    archive = parse_hindsight_archive(build_archive_bytes())
    buckets = hindsight_to_memories_by_type(archive)
    from hindsight_mapper import migration_summary

    summary = migration_summary(archive, buckets)
    assert summary["source_facts"] == 5
    assert summary["mapped_memories"] == 6
    assert summary["per_type"]["preference"] == 1


def test_rejects_invalid_zip():
    with pytest.raises(ValueError, match="not a valid ZIP"):
        parse_hindsight_archive(b"not-a-zip")
