from memanto.app.services.memory_export_service import MemoryExportService


class TestMemoryExportService:
    """Regression coverage for memory export formatting."""

    def test_format_memory_md_skips_malformed_records(self):
        """Malformed export result shapes do not crash Markdown rendering."""
        service = MemoryExportService()

        markdown = service.format_memory_md(
            agent_id="agent-test",
            memories_by_type={
                "fact": [
                    "bad-memory-record",
                    {"title": "Good Fact", "content": "Remember this"},
                ],
                "goal": "not-a-list",
            },
            generated_at="2026-06-28 12:00:00",
        )

        assert "> Total memories: **1**" in markdown
        assert "> Breakdown: fact: 1" in markdown
        assert "### Good Fact" in markdown
        assert "Remember this" in markdown
        assert "bad-memory-record" not in markdown

    def test_normalize_memories_by_type_counts_only_memory_dicts(self):
        """Shared normalization keeps client export counts in sync."""
        service = MemoryExportService()

        normalized = service.normalize_memories_by_type(
            {
                "fact": [
                    {"title": "One"},
                    ["not", "a", "memory"],
                    {"title": "Two"},
                ],
                "error": {"title": "not-a-list"},
            }
        )

        assert normalized == {
            "fact": [{"title": "One"}, {"title": "Two"}],
            "error": [],
        }

    def test_format_memory_md_stringifies_odd_memory_fields(self):
        """Unexpected scalar field values should render instead of crashing."""
        service = MemoryExportService()

        markdown = service.format_memory_md(
            agent_id="agent-test",
            memories_by_type={
                "fact": [
                    {
                        "title": ["List", "Title"],
                        "content": 123,
                        "created_at": 456,
                        "status": ["kept"],
                    }
                ]
            },
            generated_at="2026-06-28 12:00:00",
        )

        assert "### ['List', 'Title']" in markdown
        assert "123" in markdown
        assert "Status: ['kept']" in markdown
        assert "Created: 456" in markdown
