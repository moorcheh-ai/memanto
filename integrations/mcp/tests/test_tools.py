"""Tool-layer helpers should preserve Memanto result shape for MCP clients."""

from __future__ import annotations

from memanto_mcp.tools import _to_memory_hit


def test_to_memory_hit_splits_comma_separated_tag_metadata() -> None:
    hit = _to_memory_hit(
        {
            "id": "mem-1",
            "content": "User prefers concise updates.",
            "tags": "alpha, beta,release-notes",
        }
    )

    assert hit.tags == ["alpha", "beta", "release-notes"]


def test_to_memory_hit_keeps_tag_lists_clean() -> None:
    hit = _to_memory_hit(
        {
            "id": "mem-1",
            "content": "User prefers concise updates.",
            "tags": ["alpha", " beta ", ""],
        }
    )

    assert hit.tags == ["alpha", "beta"]


def test_to_memory_hit_defaults_missing_tags_to_empty_list() -> None:
    hit = _to_memory_hit({"id": "mem-1", "content": "No tags here."})

    assert hit.tags == []
