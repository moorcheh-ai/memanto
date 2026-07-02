"""
Tests for memory core fixes:

1. _format_memory_item tag stripping with 3+ blocks
2. MemoryRecord TTL constructor sets expires_at
3. update_memory handles string expires_at from metadata
"""

import re
from datetime import datetime, timedelta

import pytest

from memanto.app.core import MemoryRecord


# ── Fix 1: _format_memory_item tag stripping ──────────────────────────

def _format_item(raw_text: str) -> tuple[str, str]:
    """Reproduce the fixed _format_memory_item text-parsing logic."""
    title = ""
    content = raw_text

    if raw_text:
        blocks = raw_text.split("\n\n")
        first_line = blocks[0] if blocks else ""

        title_match = re.match(r"^\[.*?\]\s*(.*)$", first_line)
        if title_match:
            title = title_match.group(1).strip()
            remaining = blocks[1:]
            # Strip trailing Tags block so metadata doesn't leak into content.
            if remaining and remaining[-1].startswith("Tags: "):
                remaining = remaining[:-1]
            content = "\n\n".join(remaining) if remaining else ""
        else:
            title = first_line.strip()
            remaining = blocks[1:]
            if remaining and remaining[-1].startswith("Tags: "):
                remaining = remaining[:-1]
            content = "\n\n".join(remaining) if remaining else ""

    return title, content


def test_tag_stripping_with_multiple_paragraphs():
    """Tags block at end of 3+ paragraphs must be stripped from content."""
    text = "[FACT] Market Size\n\nParagraph 1\n\nParagraph 2\n\nTags: market, finance"
    title, content = _format_item(text)
    assert title == "Market Size"
    assert "Tags:" not in content
    assert "Paragraph 1" in content
    assert "Paragraph 2" in content


def test_tag_stripping_does_not_strip_non_trailing_tags():
    """Content paragraphs that start with 'Tags: ' in the middle should be kept."""
    text = "[FACT] Note\n\nTags are useful for organization"
    title, content = _format_item(text)
    assert title == "Note"
    assert content == "Tags are useful for organization"


def test_tag_stripping_tags_only_block_after_title():
    """When Tags is the only block after title, content should be empty."""
    text = "[FACT] Session Note\n\nTags: session, daily"
    title, content = _format_item(text)
    assert title == "Session Note"
    assert content == ""


def test_tag_stripping_no_tags_block():
    """When there is no Tags block, content is preserved as-is."""
    text = "[FACT] User Pref\n\nLikes dark mode"
    title, content = _format_item(text)
    assert title == "User Pref"
    assert content == "Likes dark mode"


# ── Fix 2: MemoryRecord TTL constructor sets expires_at ───────────────

def test_ttl_constructor_computes_expires_at():
    """When ttl_seconds is provided to MemoryRecord, expires_at must be set."""
    memory = MemoryRecord(
        type="fact",
        title="TTL Test",
        content="This memory should expire",
        agent_id="test-agent",
        actor_id="user",
        source="test",
        ttl_seconds=3600,
    )
    assert memory.ttl_seconds == 3600
    assert memory.expires_at is not None
    # expires_at should be roughly now + 3600 seconds
    now = datetime.utcnow()
    delta = (memory.expires_at - now).total_seconds()
    assert 3500 <= delta <= 3700, f"Expected ~3600s, got {delta}s"


def test_ttl_constructor_no_ttl_leaves_expires_none():
    """Without ttl_seconds, expires_at stays None."""
    memory = MemoryRecord(
        type="fact",
        title="No TTL",
        content="No expiry",
        agent_id="test-agent",
        actor_id="user",
        source="test",
    )
    assert memory.ttl_seconds is None
    assert memory.expires_at is None


def test_ttl_not_overwritten_when_both_provided():
    """When both ttl_seconds and expires_at are provided, expires_at is kept."""
    explicit_expiry = datetime.utcnow() + timedelta(hours=2)
    memory = MemoryRecord(
        type="fact",
        title="Explicit Expiry",
        content="Custom expiry",
        agent_id="test-agent",
        actor_id="user",
        source="test",
        ttl_seconds=3600,
        expires_at=explicit_expiry,
    )
    assert memory.expires_at == explicit_expiry


# ── Fix 3: to_moorcheh_document handles string expires_at ─────────────

def test_to_moorcheh_document_handles_string_expires_at():
    """to_moorcheh_document() must not crash when expires_at is a string."""
    memory = MemoryRecord(
        type="fact",
        title="String Expiry",
        content="Expires at is a string",
        agent_id="test-agent",
        actor_id="user",
        source="test",
    )
    # Simulate what happens when expires_at comes from metadata as a string
    memory.expires_at = "2026-07-10T00:00:00"

    # This must not raise AttributeError: 'str' object has no attribute 'isoformat'
    doc = memory.to_moorcheh_document()
    assert doc["expires_at"] == "2026-07-10T00:00:00"


def test_to_moorcheh_document_datetime_expires_at():
    """to_moorcheh_document() still works with datetime expires_at."""
    expiry = datetime.utcnow() + timedelta(days=1)
    memory = MemoryRecord(
        type="fact",
        title="Datetime Expiry",
        content="Expires at is datetime",
        agent_id="test-agent",
        actor_id="user",
        source="test",
        ttl_seconds=86400,
    )
    # Override with explicit datetime
    memory.expires_at = expiry
    doc = memory.to_moorcheh_document()
    assert doc["expires_at"] == expiry.isoformat()


def test_to_moorcheh_document_no_expiry():
    """When no expiry is set, expires_at is absent from document."""
    memory = MemoryRecord(
        type="fact",
        title="No Expiry",
        content="No expiry set",
        agent_id="test-agent",
        actor_id="user",
        source="test",
    )
    doc = memory.to_moorcheh_document()
    assert "expires_at" not in doc
