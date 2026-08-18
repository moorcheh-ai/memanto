"""Test memory format round-trip integrity: content/tag parsing in _format_memory_item."""

from unittest.mock import MagicMock

from memanto.app.core import MemoryRecord
from memanto.app.models import RecallResponse, TemporalRecallResponse
from memanto.app.services.memory_read_service import MemoryReadService


def _make_read_service():
    return MemoryReadService(MagicMock())


def _formatted_memory_with_source_ref():
    memory = MemoryRecord(
        type="fact",
        title="Imported fact",
        content="This memory came from an external document.",
        agent_id="test-agent",
        actor_id="user",
        source="system",
        source_ref="document://guide/section-2",
    )

    return _make_read_service()._format_memory_item(memory.to_moorcheh_document())


def test_recall_response_preserves_formatted_source_ref():
    formatted = _formatted_memory_with_source_ref()

    response = RecallResponse(
        agent_id="test-agent",
        session_id="test-session",
        query="external document",
        memories=[formatted],
        count=1,
    )

    assert formatted["source_ref"] == "document://guide/section-2"
    assert response.model_dump()["memories"][0]["source_ref"] == formatted["source_ref"]


def test_temporal_recall_response_preserves_formatted_source_ref():
    formatted = _formatted_memory_with_source_ref()

    response = TemporalRecallResponse(
        agent_id="test-agent",
        session_id="test-session",
        memories=[formatted],
        count=1,
        temporal_mode="recent",
    )

    assert formatted["source_ref"] == "document://guide/section-2"
    assert response.model_dump()["memories"][0]["source_ref"] == formatted["source_ref"]


def test_content_with_newlines_and_tags_preserves_content_integrity():
    """
    When memory content contains \\n\\n (multiple paragraphs), the Tags: suffix
    must NOT leak into the content field after round-tripping through
    to_moorcheh_document → _format_memory_item.

    Regression test for the bug where split("\\n\\n", 2) in _format_memory_item
    fails to separate the Tags line when content has multiple paragraphs.
    """
    memory = MemoryRecord(
        type="fact",
        title="Test Memory",
        content="This is paragraph one.\n\nThis is paragraph two.",
        agent_id="test-agent",
        actor_id="user",
        source="system",
        tags=["important", "test"],
    )

    document = memory.to_moorcheh_document()

    formatted = MemoryReadService._format_memory_item(
        MemoryReadService(MagicMock()), document
    )

    assert "Tags:" not in formatted["content"], (
        f"Tags suffix leaked into content field: {formatted['content']!r}"
    )
    assert formatted["content"] == "This is paragraph one.\n\nThis is paragraph two.", (
        f"Content was corrupted: expected paragraphs, got {formatted['content']!r}"
    )
    assert formatted["tags"] == ["important", "test"], (
        f"Tags were corrupted: {formatted['tags']}"
    )


def test_content_without_newlines_is_unchanged():
    """Memories without newlines in content should round-trip unchanged."""
    memory = MemoryRecord(
        type="fact",
        title="Simple",
        content="Single line content.",
        agent_id="test-agent",
        actor_id="user",
        source="system",
        tags=["tag1"],
    )

    document = memory.to_moorcheh_document()
    formatted = MemoryReadService._format_memory_item(
        MemoryReadService(MagicMock()), document
    )

    assert formatted["content"] == "Single line content."
    assert formatted["tags"] == ["tag1"]


def test_content_with_multiple_newlines_and_no_tags():
    """Content with \\n\\n but no tags should still work."""
    memory = MemoryRecord(
        type="fact",
        title="Multi Para",
        content="Para one.\n\nPara two.\n\nPara three.",
        agent_id="test-agent",
        actor_id="user",
        source="system",
    )

    document = memory.to_moorcheh_document()
    formatted = MemoryReadService._format_memory_item(
        MemoryReadService(MagicMock()), document
    )

    assert "Tags:" not in formatted["content"]
    assert formatted["content"] == "Para one.\n\nPara two.\n\nPara three."
    assert formatted["tags"] == []


def test_memory_without_type_prefix_round_trips_tags():
    """Documents without [TYPE] prefix should also strip tags correctly."""
    document = {
        "id": "test-id",
        "text": "My Title\n\nContent here\n\nTags: tag1, tag2",
        "memory_type": "fact",
        "tags": "tag1,tag2",
    }

    formatted = MemoryReadService._format_memory_item(
        MemoryReadService(MagicMock()), document
    )

    assert "Tags:" not in formatted["content"]
    assert formatted["content"] == "Content here"
    assert formatted["tags"] == ["tag1", "tag2"]


def test_memory_with_tags_in_middle_paragraph_does_not_leak():
    """
    Content where the 'Tags:' substring appears naturally in the text
    should not be stripped.  Only an exact "Tags: " at the start of a
    \\n\\n-delimited segment is the tag suffix.
    """
    memory = MemoryRecord(
        type="fact",
        title="Tags in Content",
        content="Use the #Tags: feature for organization.\n\nThis is fine.",
        agent_id="test-agent",
        actor_id="user",
        source="system",
        tags=["label"],
    )

    document = memory.to_moorcheh_document()
    formatted = MemoryReadService._format_memory_item(
        MemoryReadService(MagicMock()), document
    )

    assert "#Tags: feature" in formatted["content"]
    assert formatted["tags"] == ["label"]


def test_content_only_tag_line_not_confused_with_tags_suffix():
    """A line that starts with 'Tags: ' but is actual content should be kept when
    it is NOT the last \\n\\n-delimited segment that starts with 'Tags: '."""
    memory = MemoryRecord(
        type="fact",
        title="Strange",
        content="Tags: this is not a tag line\n\nActual second paragraph.",
        agent_id="test-agent",
        actor_id="user",
        source="system",
        tags=["foo"],
    )

    document = memory.to_moorcheh_document()
    formatted = MemoryReadService._format_memory_item(
        MemoryReadService(MagicMock()), document
    )

    assert "Tags: this is not a tag line" in formatted["content"]


def test_content_with_tags_line_but_no_metadata_tags_is_not_stripped():
    """
    When the content itself ends with a line that starts with 'Tags: ' (e.g.
    'Tags: my custom notes') but no tags are stored in the flat metadata
    field, the content must NOT be stripped.

    The Tags-suffix heuristic should only fire when the document actually
    has tags in its metadata.  Without this guard, legitimate content
    is silently truncated.
    """
    memory = MemoryRecord(
        type="fact",
        title="Formatting Note",
        content="First paragraph.\n\nTags: this is not actually tag metadata",
        agent_id="test-agent",
        actor_id="user",
        source="system",
        tags=[],  # No tags stored — "Tags: ..." is content, not metadata
    )

    document = memory.to_moorcheh_document()
    formatted = MemoryReadService._format_memory_item(
        MemoryReadService(MagicMock()), document
    )

    # The content must contain the "Tags: ..." line since it was never
    # a real metadata suffix.
    assert "Tags: this is not actually tag metadata" in formatted["content"], (
        f"Content was incorrectly stripped: {formatted['content']!r}"
    )
    assert (
        formatted["content"]
        == "First paragraph.\n\nTags: this is not actually tag metadata"
    ), f"Content was corrupted: {formatted['content']!r}"
    assert formatted["tags"] == [], f"Tags should be empty: {formatted['tags']}"


def test_content_with_tags_line_and_real_tags_keeps_content_intact():
    """
    When the document has both real tags AND content that contains a
    'Tags: ...' line in a non-final paragraph, everything should survive.
    """
    memory = MemoryRecord(
        type="fact",
        title="Mixed Content",
        content="Tags: this is inline in the content\n\nMore content here.",
        agent_id="test-agent",
        actor_id="user",
        source="system",
        tags=["real-tag"],
    )

    document = memory.to_moorcheh_document()
    formatted = MemoryReadService._format_memory_item(
        MemoryReadService(MagicMock()), document
    )

    # The internal line "Tags: this is inline in the content" must stay
    # (only the final "Tags: real-tag" segment is the metadata suffix).
    assert "Tags: this is inline in the content" in formatted["content"], (
        f"Inline Tags: line was incorrectly stripped: {formatted['content']!r}"
    )
    assert formatted["tags"] == ["real-tag"]


def test_format_memory_item_coerces_epoch_timestamps_to_iso_strings():
    """
    Documents written outside Memanto's own store path (e.g. manual test
    data sharing a namespace) can carry raw Unix-epoch numbers instead of
    ISO strings for created_at/updated_at. The MemoryItem response model
    requires a string, so a raw int previously made FastAPI's response
    serialization raise ResponseValidationError and 500 the whole recall.
    """
    document = {
        "id": "mem-legacy",
        "text": "[FACT] Legacy\n\nImported without ISO timestamps",
        "metadata": {
            "memory_type": "fact",
            "created_at": 1778461885,
            "updated_at": 1778461885,
        },
    }

    formatted = MemoryReadService._format_memory_item(
        MemoryReadService(MagicMock()), document
    )

    assert isinstance(formatted["created_at"], str)
    assert isinstance(formatted["updated_at"], str)
    assert formatted["created_at"] == "2026-05-11T01:11:25+00:00"


def test_format_memory_item_preserves_iso_string_timestamps():
    """Normal ISO string timestamps must pass through unchanged."""
    document = {
        "id": "mem-normal",
        "text": "[FACT] Normal\n\nWritten via Memanto",
        "metadata": {
            "memory_type": "fact",
            "created_at": "2026-05-11T01:11:25+00:00",
            "updated_at": "2026-05-11T01:11:25+00:00",
        },
    }

    formatted = MemoryReadService._format_memory_item(
        MemoryReadService(MagicMock()), document
    )

    assert formatted["created_at"] == "2026-05-11T01:11:25+00:00"
    assert formatted["updated_at"] == "2026-05-11T01:11:25+00:00"
