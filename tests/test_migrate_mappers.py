from memanto.cli.migrate.mappers import map_supermemory


def test_supermemory_fallback_preserves_same_text_from_different_documents():
    export = {
        "memories": [],
        "documents": [
            {
                "id": "doc-eng",
                "container_tags": ["engineering"],
                "chunks": [
                    {
                        "id": "chunk-1",
                        "content": "Shared rollout checklist applies this week.",
                    }
                ],
            },
            {
                "id": "doc-ops",
                "container_tags": ["operations"],
                "chunks": [
                    {
                        "id": "chunk-1",
                        "content": "Shared rollout checklist applies this week.",
                    }
                ],
            },
        ],
    }

    rows = map_supermemory(export)

    assert len(rows) == 2
    assert {row["source_ref"] for row in rows} == {
        "doc-eng:chunk-1",
        "doc-ops:chunk-1",
    }
    assert {tuple(row["tags"]) for row in rows} == {
        ("engineering",),
        ("operations",),
    }


def test_supermemory_fallback_still_skips_exact_same_source_chunk():
    export = {
        "memories": [],
        "documents": [
            {
                "id": "doc-eng",
                "container_tags": ["engineering"],
                "chunks": [
                    {"id": "chunk-1", "content": "Duplicate source chunk."},
                    {"id": "chunk-1", "content": "Duplicate source chunk."},
                ],
            }
        ],
    }

    rows = map_supermemory(export)

    assert len(rows) == 1
    assert rows[0]["source_ref"] == "doc-eng:chunk-1"
