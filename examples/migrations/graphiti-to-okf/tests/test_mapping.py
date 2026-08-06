"""Unit tests for the Graphiti → Memanto mapper.

These run offline against a tiny synthetic export shaped exactly like the
real dump ``scripts/export_graphiti.py`` produces. They are not a substitute
for the live round-trip — they just make sure the mapping table's promises
(types, temporal tags, confidence policy, OKF frontmatter) stay true.
"""

from __future__ import annotations

from datetime import datetime, timezone

from graphiti_okf.mapping import (
    CONFIDENCE_CURRENT_EDGE,
    CONFIDENCE_SUPERSEDED_EDGE,
    classify_edge,
    map_export,
    temporal_status,
)
from graphiti_okf.okf_writer import build_frontmatter, write_bundle
from graphiti_okf.provider_json import build_provider_export


def _sample_export() -> dict:
    return {
        "source": "graphiti",
        "graphiti_version": "0.0-test",
        "exported_at": "2026-08-06T00:00:00+00:00",
        "group_id": "test",
        "episodes": [
            {
                "uuid": "ep-1",
                "name": "s1-kickoff",
                "content": "user: Postgres is our primary datastore.",
                "source": "message",
                "source_description": "kickoff",
                "valid_at": "2026-01-14T09:30:00+00:00",
                "created_at": "2026-01-14T09:30:00+00:00",
                "group_id": "test",
                "entity_edges": [],
            }
        ],
        "entity_nodes": [
            {
                "uuid": "n-daniel",
                "name": "Daniel Okafor",
                "summary": "Staff engineer.",
                "labels": ["Entity", "Person"],
                "attributes": {"role": "staff"},
                "created_at": "2026-01-14T09:30:00+00:00",
                "group_id": "test",
            },
            {
                "uuid": "n-pg",
                "name": "Postgres",
                "summary": "Relational database.",
                "labels": ["Entity"],
                "attributes": {},
                "created_at": "2026-01-14T09:30:00+00:00",
                "group_id": "test",
            },
        ],
        "entity_edges": [
            {
                "uuid": "e-prefers-pg",
                "name": "PREFERS",
                "fact": "Daniel Okafor prefers Postgres as the primary datastore.",
                "source_node_uuid": "n-daniel",
                "target_node_uuid": "n-pg",
                "created_at": "2026-01-14T09:30:00+00:00",
                "valid_at": "2026-01-14T09:30:00+00:00",
                "invalid_at": "2026-03-30T11:00:00+00:00",
                "expired_at": "2026-03-30T11:00:00+00:00",
                "episodes": ["ep-1"],
                "group_id": "test",
                "attributes": {},
            },
            {
                "uuid": "e-works-at",
                "name": "WORKS_AT",
                "fact": "Daniel Okafor works at Halcyon Data.",
                "source_node_uuid": "n-daniel",
                "target_node_uuid": "n-pg",
                "created_at": "2026-06-25T08:45:00+00:00",
                "valid_at": "2026-06-25T08:45:00+00:00",
                "invalid_at": None,
                "expired_at": None,
                "episodes": ["ep-1"],
                "group_id": "test",
                "attributes": {},
            },
        ],
        "communities": [
            {
                "uuid": "c-1",
                "name": "Atlas stack",
                "summary": "Cluster of datastore and infra decisions.",
                "created_at": "2026-07-30T13:00:00+00:00",
                "group_id": "test",
            }
        ],
    }


def test_classify_edge_prefers_preference():
    assert classify_edge("PREFERS", "x") == "preference"


def test_classify_edge_works_at_relationship():
    assert classify_edge("WORKS_AT", "x") == "relationship"


def test_classify_edge_falls_back_to_fact():
    assert classify_edge("RELATED_TO", "something vague") == "fact"


def test_temporal_status():
    assert (
        temporal_status(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 3, 1, tzinfo=timezone.utc),
            None,
        )
        == "superseded"
    )
    assert temporal_status(datetime(2026, 1, 1, tzinfo=timezone.utc), None, None) == "current"


def test_map_export_preserves_temporal_and_types():
    records = map_export(_sample_export())
    by_ref = {r.source_ref: r for r in records}

    superseded = by_ref["graphiti:entity_edge:e-prefers-pg"]
    assert superseded.type == "preference"
    assert superseded.temporal["status"] == "superseded"
    assert superseded.confidence == CONFIDENCE_SUPERSEDED_EDGE
    assert "No longer current" in superseded.content
    assert "superseded" in superseded.tags

    current = by_ref["graphiti:entity_edge:e-works-at"]
    assert current.type == "relationship"
    assert current.temporal["status"] == "current"
    assert current.confidence == CONFIDENCE_CURRENT_EDGE

    entity = by_ref["graphiti:entity_node:n-daniel"]
    assert entity.type == "context"

    episode = by_ref["graphiti:episode:ep-1"]
    assert episode.type == "observation"

    community = by_ref["graphiti:community:c-1"]
    assert community.type == "learning"


def test_okf_frontmatter_carries_temporal_keys(tmp_path):
    records = map_export(_sample_export())
    superseded = next(r for r in records if r.temporal.get("status") == "superseded")
    fm = build_frontmatter(superseded)
    assert fm["type"] == "preference"
    assert fm["x_memanto"]["source"] == "graphiti"
    assert fm["valid_at"]
    assert fm["invalid_at"]
    assert fm["graphiti_status"] == "superseded"

    summary = write_bundle(records, tmp_path / "bundle")
    assert summary["total_memories"] == len(records)
    assert (tmp_path / "bundle" / "memories" / "preference").is_dir()
    assert (tmp_path / "bundle" / "index.md").is_file()


def test_provider_json_puts_type_in_first_category():
    export = _sample_export()
    records = map_export(export)
    document = build_provider_export(records, export)
    assert document["_adapter"]["source_system"] == "graphiti"
    assert document["summary"]["memory_count"] == len(records)
    for mem in document["memories"]:
        assert mem["categories"][0] in {
            "fact",
            "preference",
            "relationship",
            "context",
            "observation",
            "learning",
            "decision",
            "goal",
            "commitment",
            "instruction",
            "event",
            "error",
            "artifact",
        }
