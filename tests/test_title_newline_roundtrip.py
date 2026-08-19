"""
Regression tests for multi-line memory titles.

A title containing a newline breaks the ``[TYPE] title\\n\\ncontent`` document
format round-trip:

- ``MemoryReadService._format_memory_item`` fails to strip the ``[TYPE]``
  prefix (its regex cannot cross the embedded newline), so recall returns the
  internal storage prefix leaked into the user-visible title.
- ``update_memory`` rebuilds the record from that corrupted read, so every
  update prepends another ``[TYPE]`` prefix; once the title outgrows the
  100-char limit the memory can never be updated again.
- Titles with newlines are reachable from every entry point: no API/MCP/CLI
  validator rejects them, and the derived-title fallback (``content[:50]``)
  produces them automatically for any multi-line content stored without an
  explicit title.

See https://github.com/moorcheh-ai/memanto/issues/770
"""

from unittest.mock import MagicMock

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_read_service import MemoryReadService


def _record(title: str, content: str = "Body of the memory.") -> MemoryRecord:
    return MemoryRecord(
        type="fact",
        title=title,
        content=content,
        agent_id="test-agent",
        actor_id="test-agent",
        source="user",
    )


def _read_back(record: MemoryRecord) -> dict:
    """Serialize a record and re-parse it the way recall/get_memory does."""
    document = record.to_moorcheh_document()
    service = MemoryReadService(MagicMock())
    return service._format_memory_item(
        {"id": record.id, "text": document["text"], "metadata": {}}
    )


class TestTitleNewlineNormalization:
    """Titles are single-line labels: embedded newlines must be normalized."""

    def test_title_with_newline_is_normalized_at_construction(self):
        record = _record("Deploy checklist\n(staging first)")
        assert "\n" not in record.title
        assert record.title == "Deploy checklist (staging first)"

    def test_title_with_crlf_and_surrounding_spaces_is_normalized(self):
        record = _record("Step one \r\n  step two")
        assert "\n" not in record.title
        assert "\r" not in record.title
        assert record.title == "Step one step two"

    def test_derived_title_from_multiline_content_stays_single_line(self):
        # Mirrors the derived-title fallback used by the API route, MCP tool,
        # and CLI clients when the caller omits a title.
        content = "Step 1: do X\nStep 2: do Y"
        record = _record(title=content[:50], content=content)
        assert "\n" not in record.title

    def test_single_line_titles_are_untouched(self):
        record = _record("Plain single-line title")
        assert record.title == "Plain single-line title"


class TestTitleRoundTrip:
    """Stored titles must come back without the internal [TYPE] prefix."""

    def test_multiline_title_round_trip_has_no_type_prefix(self):
        record = _record("Deploy checklist\n(staging first)")
        formatted = _read_back(record)
        assert not formatted["title"].startswith("[FACT]")
        assert formatted["title"] == record.title
        assert formatted["content"] == "Body of the memory."

    def test_legacy_document_with_multiline_title_still_strips_prefix(self):
        # Documents stored before normalization existed still contain raw
        # newlines inside the title line; the reader must strip the [TYPE]
        # prefix rather than leak it into the title.
        service = MemoryReadService(MagicMock())
        formatted = service._format_memory_item(
            {
                "id": "legacy-1",
                "text": "[FACT] Deploy checklist\n(staging first)\n\nBody.",
                "metadata": {},
            }
        )
        assert formatted["title"] == "Deploy checklist\n(staging first)"
        assert formatted["content"] == "Body."

    def test_update_cycle_does_not_compound_type_prefixes(self):
        # Simulates update_memory: read the formatted record, rebuild it with
        # unchanged title/content, store, and read again. The title must be
        # stable instead of gaining one more "[FACT] " prefix per update.
        record = _record("Deploy checklist\n(staging first)")
        formatted = _read_back(record)

        for _ in range(3):
            rebuilt = _record(title=formatted["title"], content=formatted["content"])
            formatted = _read_back(rebuilt)

        assert not formatted["title"].startswith("[FACT]")
        assert formatted["title"] == record.title
