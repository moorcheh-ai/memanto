"""Focused tests for MCP tool output helpers."""

from __future__ import annotations

from memanto_mcp.tools import _to_memory_hit


def test_to_memory_hit_skips_malformed_recall_rows() -> None:
    """Malformed recall rows should be ignored by MCP recall tools."""
    assert _to_memory_hit("truncated") is None


def test_to_memory_hit_formats_valid_recall_rows() -> None:
    """Valid recall rows should still map to the stable MemoryHit schema."""
    hit = _to_memory_hit(
        {
            "id": "mem-1",
            "type": "fact",
            "title": "Valid",
            "content": "Kept",
            "tags": ["alpha"],
            "similarity_score": 0.91,
        }
    )

    assert hit is not None
    assert hit.id == "mem-1"
    assert hit.content == "Kept"
    assert hit.tags == ["alpha"]
    assert hit.score == 0.91
