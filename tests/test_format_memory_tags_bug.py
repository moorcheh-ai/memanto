"""
Test for _format_memory_item tags stripping bug (bounty #770).

Verifies that legitimate content paragraphs starting with "Tags: "
are not silently stripped during readback.
"""
import pytest
from unittest.mock import MagicMock


def _make_item(text, tags=None, memory_type="fact"):
    """Build a Moorcheh document dict matching the wire format."""
    metadata = {
        "memory_type": memory_type,
        "tags": ",".join(tags) if tags else "",
        "confidence": 0.9,
        "status": "active",
        "agent_id": "test-agent",
        "actor_id": "test-agent",
        "source": "system",
        "provenance": "explicit_statement",
    }
    return {
        "id": "mem-001",
        "text": text,
        "metadata": metadata,
    }


def test_content_paragraph_starting_with_tags_not_stripped():
    """Content paragraphs that happen to start with 'Tags: ' must not be removed."""
    from memanto.app.services.memory_read_service import MemoryReadService

    client = MagicMock()
    svc = MemoryReadService(client)

    # A memory whose content legitimately mentions "Tags: " in a paragraph
    item = _make_item(
        "[FACT] Tagging system overview

Tags: are useful for categorization",
        tags=["python", "ai"],
    )
    result = svc._format_memory_item(item)

    # The content must still contain the "Tags: are useful" paragraph
    assert "Tags: are useful for categorization" in result["content"], (
        f"Content was incorrectly stripped! Got: {result['content']!r}"
    )


def test_actual_trailing_tags_block_is_stripped():
    """The genuine trailing Tags block appended by the serializer should be stripped."""
    from memanto.app.services.memory_read_service import MemoryReadService

    client = MagicMock()
    svc = MemoryReadService(client)

    # Simulate what to_moorcheh_document produces:
    # [TYPE] title

content

Tags: tag1, tag2
    item = _make_item(
        "[FACT] Test title

Real content here

Tags: python, ai",
        tags=["python", "ai"],
    )
    result = svc._format_memory_item(item)

    # The trailing "Tags: python, ai" block should be stripped
    assert result["content"] == "Real content here", (
        f"Trailing tags block not stripped! Got: {result['content']!r}"
    )


def test_no_tags_no_stripping():
    """When there are no tags, content starting with 'Tags: ' is preserved."""
    from memanto.app.services.memory_read_service import MemoryReadService

    client = MagicMock()
    svc = MemoryReadService(client)

    item = _make_item(
        "[FACT] Tagging discussion

Tags: should be discussed carefully",
        tags=[],
    )
    result = svc._format_memory_item(item)

    assert "Tags: should be discussed carefully" in result["content"]
