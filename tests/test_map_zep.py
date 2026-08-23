"""Zep export → Memanto mapper.

Zep stores extracted facts, graph edges, and session summaries. Raw chat
turns are not memories and must not be imported as first-class rows.
"""

from memanto.cli.migrate.mappers import map_zep
from memanto.cli.migrate.runner import map_export, source_count


SAMPLE = {
    "exported_at": "2026-08-19T20:00:00Z",
    "user_id": "user_42",
    "facts": [
        {
            "uuid": "fact-1",
            "fact": "Shawn prefers EWY for KOSPI beta, not KORU.",
            "created_at": "2026-08-10T12:00:00Z",
            "rating": 0.91,
        },
        {"uuid": "fact-blank", "fact": "   "},
    ],
    "edges": [
        {
            "uuid": "edge-1",
            "fact": "Shawn works with Scrat as his personal AI operator.",
            "created_at": "2026-08-11T09:00:00Z",
            "source_node_uuid": "n-shawn",
            "target_node_uuid": "n-scrat",
            "name": "WORKS_WITH",
        }
    ],
    "nodes": [
        {
            "uuid": "n-shawn",
            "name": "Shawn",
            "summary": "Operator in America/New_York who wants autonomous revenue.",
            "labels": ["User"],
            "created_at": "2026-08-01T00:00:00Z",
        }
    ],
    "sessions": [
        {
            "session_id": "sess-1",
            "summary": "Discussed Kickbacks recovery and bounty farm avoidance.",
            "created_at": "2026-08-19T18:00:00Z",
            "messages": [
                {"uuid": "m1", "role": "user", "content": "figure something out bro"},
                {"uuid": "m2", "role": "assistant", "content": "checking live boards"},
            ],
        }
    ],
}


def test_map_zep_imports_facts_edges_nodes_and_summaries_not_chat():
    rows = map_zep(SAMPLE)
    refs = {row["source_ref"] for row in rows}
    assert refs == {"fact-1", "edge-1", "n-shawn", "sess-1"}
    assert all(row["source"] == "zep" for row in rows)
    assert all(row["provenance"] == "imported" for row in rows)
    bodies = [row["content"] for row in rows]
    assert not any("figure something out bro" in body for body in bodies)


def test_map_zep_types_and_user_tag():
    rows = {row["source_ref"]: row for row in map_zep(SAMPLE)}
    assert rows["fact-1"]["type"] == "fact"
    assert rows["edge-1"]["type"] == "fact"
    assert rows["n-shawn"]["type"] == "relationship"
    assert rows["sess-1"]["type"] == "observation"
    assert "user=user_42" in rows["fact-1"]["tags"]
    assert "KOSPI" in rows["fact-1"]["title"]
    assert "WORKS_WITH" in rows["edge-1"]["content"]


def test_map_zep_relevant_facts_alias():
    rows = map_zep(
        {
            "relevant_facts": [
                {"uuid": "rf-1", "fact": "Account is not blocked."},
            ]
        }
    )
    assert len(rows) == 1
    assert rows[0]["source_ref"] == "rf-1"


def test_map_zep_empty_export():
    assert map_zep({}) == []
    assert map_zep({"facts": [], "sessions": []}) == []


def test_map_export_registry_and_source_count():
    rows = map_export("zep", SAMPLE)
    assert len(rows) == 4
    assert source_count("zep", SAMPLE) == 5
