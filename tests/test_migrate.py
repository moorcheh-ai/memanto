"""Focused regression tests for migration tools and mappers."""

import pytest

from memanto.cli.migrate.mappers import map_mem0
from memanto.cli.migrate.runner import load_export


class TestMigrateLoadExport:
    """Validate loading migration export files from disk."""

    @pytest.mark.parametrize("payload", ["[]", '"not an export"', "null"])
    def test_load_export_rejects_non_object_json(self, tmp_path, payload):
        """Non-object JSON roots fail before provider-specific mapping starts."""
        export_path = tmp_path / "mem0_export.json"
        export_path.write_text(payload, encoding="utf-8")

        with pytest.raises(ValueError, match="must be a JSON object"):
            load_export(export_path)


def test_map_mem0_accepts_single_category_string():
    rows = map_mem0(
        {
            "memories": [
                {
                    "id": "mem-1",
                    "memory": "The user prefers concise PR summaries.",
                    "categories": "personal_preferences",
                }
            ]
        }
    )

    assert len(rows) == 1
    assert rows[0]["type"] == "preference"
    assert rows[0]["tags"] == ["personal_preferences"]


def test_supermemory_migration_fixes():
    """Test Supermemory migration fixes (pagination, mixed accounts, and tag deduplication)."""
    from unittest.mock import patch

    from memanto.cli.analyze.supermemory_export import (
        collect_memories_deduped,
        paginate_memories_for_tag,
    )
    from memanto.cli.migrate.mappers import map_supermemory
    from memanto.cli.migrate.runner import source_count

    # 1. Pagination uses singular containerTag
    response = {
        "memoryEntries": [{"id": "memory-1", "content": "A fact"}],
        "pagination": {"totalPages": 1},
    }
    with patch(
        "memanto.cli.analyze.supermemory_export.api_request", return_value=response
    ) as request:
        memories = paginate_memories_for_tag("test-key", "project-a")
    assert memories == response["memoryEntries"]
    assert request.call_args.args[3]["containerTag"] == "project-a"
    assert "containerTags" not in request.call_args.args[3]

    # 2. Tag deduplication
    with patch(
        "memanto.cli.analyze.supermemory_export.paginate_memories_for_tag",
        side_effect=lambda k, t: [
            {"id": "shared-memory", "content": "Fact", "metadata": {"queried_via": t}}
        ],
    ):
        memories, memories_by_tag = collect_memories_deduped(
            "test-key", ["project-a", "project-b"]
        )
    assert len(memories) == 1
    assert memories[0]["container_tags"] == ["project-a", "project-b"]
    assert (
        len(memories_by_tag["project-a"]) == 1
        and len(memories_by_tag["project-b"]) == 1
    )

    # 3. Mixed accounts processing
    export = {
        "memories": [
            {"id": "memory-1", "documentId": "processed-doc", "content": "Fact"}
        ],
        "documents": [
            {
                "id": "processed-doc",
                "memory_ids": ["memory-1"],
                "container_tags": ["project-a"],
                "chunks": [{"id": "c1", "content": "Processed"}],
            },
            {
                "id": "fresh-doc",
                "memory_ids": [],
                "container_tags": ["project-b"],
                "chunks": [{"id": "c2", "content": "Fresh"}],
            },
        ],
    }
    migrated = map_supermemory(export)
    assert [r["source_ref"] for r in migrated] == ["memory-1", "fresh-doc:c2"]
    assert source_count("supermemory", export) == 2
