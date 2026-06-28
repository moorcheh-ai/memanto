"""Tool output normalization helpers."""

from __future__ import annotations

from memanto_mcp.tools import _to_memory_hit


def test_to_memory_hit_splits_comma_separated_tags() -> None:
    hit = _to_memory_hit(
        {
            "id": "memory-1",
            "title": "Client preference",
            "content": "Use the enterprise workspace.",
            "tags": "urgent, client , ,enterprise",
            "score": 0.91,
        }
    )

    assert hit.tags == ["urgent", "client", "enterprise"]


def test_to_memory_hit_preserves_list_tags() -> None:
    hit = _to_memory_hit(
        {
            "id": "memory-2",
            "tags": ["support", " escalation ", ""],
            "similarity_score": 0.73,
        }
    )

    assert hit.tags == ["support", "escalation"]
