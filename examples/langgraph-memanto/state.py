"""State and memory types for the LangGraph + Memanto example."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class MemoryHit(TypedDict):
    """A normalized memory returned by either Memanto or preview storage."""

    title: str
    content: str
    type: str
    score: float
    tags: list[str]


class StoredMemory(TypedDict):
    """A memory candidate stored after a support interaction."""

    title: str
    content: str
    type: str
    tags: list[str]


class SupportState(TypedDict):
    """LangGraph state passed between support-agent nodes."""

    customer_id: str
    message: str
    session_label: str
    intent: NotRequired[str]
    recalled_memories: NotRequired[list[MemoryHit]]
    response: NotRequired[str]
    new_memories: NotRequired[list[StoredMemory]]
