from memanto.cli.migrate.runner import map_export, run_migration


def test_mem0_mapper_skips_non_object_memory_records():
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
