"""
Regression tests for two silent memory-integrity bugs in MemoryReadService:

1. ``_format_memory_item`` used to wipe or corrupt content when the stored
   text contained a line beginning with ``"Tags: "`` (either as the content
   itself or inside multi-paragraph content).
2. ``_apply_temporal_filter`` used to disable the ENTIRE created_after /
   created_before window if any single record had a missing/unparseable
   ``created_at``, leaking out-of-window memories.

Both paths are pure Python and need no Moorcheh client, network, or API key.
"""

from memanto.app.services.memory_read_service import MemoryReadService


def _service() -> MemoryReadService:
    # These methods never touch the client; a sentinel is enough.
    return MemoryReadService(moorcheh_client=object())


def _wire(memory_type: str, title: str, content: str, tags: list[str]) -> dict:
    """Reproduce MemoryRecord.to_moorcheh_document's text/metadata layout."""
    text = f"[{memory_type.upper()}] {title}\n\n{content}"
    item: dict = {"text": text, "memory_type": memory_type}
    if tags:
        text = f"{text}\n\nTags: {', '.join(tags)}"
        item["text"] = text
        item["tags"] = ",".join(tags)
    return item


# --- Bug 1: content parsing ------------------------------------------------


def test_embedded_tags_paragraph_with_real_tags():
    # Content whose first paragraph starts with "Tags: " AND a genuine trailing
    # tags block: only the LAST block is metadata, so rpartition (not any match)
    # must be used. This is the case the fix hinges on.
    item = _wire("fact", "T", "Tags: this is user content, not metadata", ["urgent"])
    out = _service()._format_memory_item(item)
    assert out["content"] == "Tags: this is user content, not metadata"
    assert out["tags"] == ["urgent"]


# --- Bug 2: temporal filter fail-open --------------------------------------


def test_one_bad_timestamp_does_not_disable_window():
    results = [
        {"id": "old", "created_at": "2020-01-01T00:00:00Z"},
        {"id": "bad", "created_at": "not-a-timestamp"},
        {"id": "june", "created_at": "2026-06-15T00:00:00Z"},
    ]
    out = _service()._apply_temporal_filter(
        results, created_after="2026-06-01T00:00:00Z", created_before=None
    )
    # Only the in-window record survives; the 2020 record must NOT leak through,
    # and the unparseable record is skipped individually.
    assert [r["id"] for r in out] == ["june"]
