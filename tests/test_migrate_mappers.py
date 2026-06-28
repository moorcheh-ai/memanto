"""Regression coverage for migration export record-shape resilience."""

from memanto.cli.migrate.runner import map_export, run_migration


def test_mem0_mapper_skips_non_object_memory_records():
    """Mem0 migration skips malformed array items and keeps valid memories."""
    rows = map_export(
        "mem0",
        {
            "memories": [
                "truncated record",
                {"id": "m1", "memory": "User prefers concise status updates"},
                42,
            ]
        },
    )

    assert len(rows) == 1
    assert rows[0]["source"] == "mem0"
    assert rows[0]["source_ref"] == "m1"


def test_letta_mapper_skips_non_object_passage_records():
    """Letta migration skips malformed passage entries and maps valid passages."""
    rows = map_export(
        "letta",
        {
            "passages": [
                None,
                {"id": "p1", "text": "The support agent should ask for order id"},
                ["bad", "passage"],
            ]
        },
    )

    assert len(rows) == 1
    assert rows[0]["source"] == "letta"
    assert rows[0]["source_ref"] == "p1"


def test_supermemory_migration_skips_non_object_documents_and_chunks():
    """Supermemory fallback skips malformed documents/chunks without crashing."""
    summary, rows = run_migration(
        provider="supermemory",
        export={
            "memories": [],
            "documents": [
                "truncated document",
                {
                    "id": "doc1",
                    "container_tags": ["team"],
                    "detail": "malformed detail",
                    "chunks": [
                        "truncated chunk",
                        {"id": "c1", "content": "Team uses Python for automation"},
                    ],
                },
            ],
        },
        client=object(),
        agent_id="agent-1",
        dry_run=True,
    )

    assert summary.source_count == 2
    assert summary.mapped_count == 1
    assert summary.skipped == 1
    assert rows[0]["source"] == "supermemory"
    assert rows[0]["source_ref"] == "doc1:c1"


def test_supermemory_migration_falls_back_when_memories_are_malformed():
    """Malformed Supermemory memories still allow document chunk fallback."""
    summary, rows = run_migration(
        provider="supermemory",
        export={
            "memories": ["truncated memory"],
            "documents": [
                {
                    "id": "doc1",
                    "chunks": [
                        {"id": "c1", "content": "First fallback chunk"},
                        {"id": "c2", "text": "Second fallback chunk"},
                    ],
                },
            ],
        },
        client=object(),
        agent_id="agent-1",
        dry_run=True,
    )

    assert summary.source_count == 2
    assert summary.mapped_count == 2
    assert summary.skipped == 0
    assert [row["source_ref"] for row in rows] == ["doc1:c1", "doc1:c2"]


def test_supermemory_migration_uses_doc_timestamp_when_detail_is_malformed():
    """A malformed detail object does not suppress the document timestamp."""
    _, rows = run_migration(
        provider="supermemory",
        export={
            "memories": [],
            "documents": [
                {
                    "id": "doc1",
                    "createdAt": "2026-06-01T12:00:00Z",
                    "detail": "malformed detail",
                    "chunks": [{"id": "c1", "content": "Timestamped chunk"}],
                },
            ],
        },
        client=object(),
        agent_id="agent-1",
        dry_run=True,
    )

    assert rows[0]["created_at"].isoformat() == "2026-06-01T12:00:00+00:00"
