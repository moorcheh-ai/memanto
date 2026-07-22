"""Regression tests for Supermemory export and migration."""

from unittest.mock import patch

from memanto.cli.analyze.supermemory_export import (
    collect_memories_deduped,
    paginate_memories_for_tag,
)
from memanto.cli.migrate.mappers import map_supermemory
from memanto.cli.migrate.runner import source_count


def test_memory_pagination_uses_v4_singular_container_tag():
    """The v4 memories endpoint requires the singular containerTag field."""
    response = {
        "memoryEntries": [{"id": "memory-1", "content": "A fact"}],
        "pagination": {"totalPages": 1},
    }

    with patch(
        "memanto.cli.analyze.supermemory_export.api_request",
        return_value=response,
    ) as request:
        memories = paginate_memories_for_tag("test-key", "project-a")

    assert memories == response["memoryEntries"]
    payload = request.call_args.args[3]
    assert payload["containerTag"] == "project-a"
    assert "containerTags" not in payload


def test_shared_memory_preserves_all_container_tags():
    """A memory returned for multiple containers keeps every association."""

    def memories_for_tag(_api_key: str, tag: str):
        return [
            {
                "id": "shared-memory",
                "content": "The deployment region is eu-west-1",
                "metadata": {"queried_via": tag},
            }
        ]

    with patch(
        "memanto.cli.analyze.supermemory_export.paginate_memories_for_tag",
        side_effect=memories_for_tag,
    ):
        memories, memories_by_tag = collect_memories_deduped(
            "test-key", ["project-a", "project-b"]
        )

    assert len(memories) == 1
    assert memories[0]["container_tag"] == "project-a"
    assert memories[0]["container_tags"] == ["project-a", "project-b"]

    assert [row["id"] for row in memories_by_tag["project-a"]] == ["shared-memory"]
    assert [row["id"] for row in memories_by_tag["project-b"]] == ["shared-memory"]
    assert memories_by_tag["project-a"][0]["container_tag"] == "project-a"
    assert memories_by_tag["project-b"][0]["container_tag"] == "project-b"

    migrated = map_supermemory({"memories": memories})
    assert len(migrated) == 1
    assert migrated[0]["tags"] == ["project-a", "project-b"]


def test_mixed_account_preserves_unrepresented_document_chunks():
    """Extracted memories must not suppress unrelated fresh documents."""
    export = {
        "memories": [
            {
                "id": "memory-1",
                "documentId": "processed-doc",
                "content": "The processed fact",
            }
        ],
        "documents": [
            {
                "id": "processed-doc",
                "memory_ids": ["memory-1"],
                "container_tags": ["project-a"],
                "chunks": [
                    {"id": "processed-chunk", "content": "Processed source text"}
                ],
            },
            {
                "id": "fresh-doc",
                "memory_ids": [],
                "container_tags": ["project-b"],
                "chunks": [{"id": "fresh-chunk", "content": "Fresh document context"}],
            },
        ],
    }

    migrated = map_supermemory(export)

    assert [row["source_ref"] for row in migrated] == [
        "memory-1",
        "fresh-doc:fresh-chunk",
    ]
    assert migrated[1]["content"].startswith("Fresh document context")
    assert migrated[1]["tags"] == ["project-b"]
    assert source_count("supermemory", export) == 2
