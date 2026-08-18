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
    from memanto.cli.analyze.supermemory_export import collect_memories_deduped, paginate_memories_for_tag
    from memanto.cli.migrate.mappers import map_supermemory
    from memanto.cli.migrate.runner import source_count