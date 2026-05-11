"""
LangGraph workflow that uses Memanto as long-term memory.

Only the current user message and current recall results live in graph state.
Facts/preferences that must survive later sessions are written to Memanto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from memory_backend import MemoryBackend, MemoryItem


class SupportState(TypedDict, total=False):
    """State passed between LangGraph nodes for one request."""

    user_message: str
    recalled_memories: list[MemoryItem]
    stored_memory_ids: list[str]
    response: str


@dataclass(frozen=True)
class ExtractedMemory:
    """A memory candidate parsed from the current user message."""

    memory_type: str
    title: str
    content: str
    confidence: float
    tags: list[str]


def _clean_clause(value: str) -> str:
    value = re.split(r"\s+and\s+I\s+", value, maxsplit=1, flags=re.IGNORECASE)[0]
    return value.strip().strip(".!?:;").strip()


def extract_memories(message: str) -> list[ExtractedMemory]:
    """
    Extract simple explicit memories from a user message.

    The example keeps extraction deterministic so it can run without an LLM.
    In a production agent, this node is the right place to swap in model-based
    extraction while keeping the same Memanto write contract.
    """

    memories: list[ExtractedMemory] = []

    name_match = re.search(
        r"\bmy name is ([A-Z][A-Za-z '-]{1,40})",
        message,
        flags=re.IGNORECASE,
    )
    if name_match:
        name = _clean_clause(name_match.group(1))
        memories.append(
            ExtractedMemory(
                memory_type="fact",
                title="User name",
                content=f"User's name is {name}.",
                confidence=0.98,
                tags=["identity", "support"],
            )
        )

    for pattern, title, polarity in (
        (r"\bI prefer ([^.?!]+)", "User preference", "prefers"),
        (r"\bI like ([^.?!]+)", "User preference", "likes"),
        (r"\bI hate ([^.?!]+)", "User aversion", "dislikes"),
        (r"\bI dislike ([^.?!]+)", "User aversion", "dislikes"),
    ):
        for match in re.finditer(pattern, message, flags=re.IGNORECASE):
            preference = _clean_clause(match.group(1))
            if preference:
                memories.append(
                    ExtractedMemory(
                        memory_type="preference",
                        title=title,
                        content=f"User {polarity} {preference}.",
                        confidence=0.92,
                        tags=["preference", "support"],
                    )
                )

    return memories


def _format_memories(memories: list[MemoryItem]) -> str:
    if not memories:
        return "No relevant persistent memories were found."

    lines = []
    for index, item in enumerate(memories, start=1):
        lines.append(f"{index}. [{item.memory_type}] {item.title}: {item.content}")
    return "\n".join(lines)


def build_support_graph(memory: MemoryBackend):
    """Build the support-agent graph bound to a memory backend."""

    def recall_context(state: SupportState) -> SupportState:
        user_message = state["user_message"]
        memories = memory.recall(
            query=user_message,
            limit=5,
            memory_types=["fact", "preference", "instruction", "decision"],
        )
        return {"recalled_memories": memories}

    def remember_context(state: SupportState) -> SupportState:
        stored_ids: list[str] = []

        for item in extract_memories(state["user_message"]):
            memory_id = memory.remember(
                memory_type=item.memory_type,
                title=item.title,
                content=item.content,
                confidence=item.confidence,
                tags=item.tags,
            )
            stored_ids.append(memory_id)

        return {"stored_memory_ids": stored_ids}

    def draft_response(state: SupportState) -> SupportState:
        recalled = state.get("recalled_memories", [])
        stored_ids = state.get("stored_memory_ids", [])

        response_parts = [
            "Persistent memory recalled from Memanto:",
            _format_memories(recalled),
        ]

        if stored_ids:
            response_parts.extend(
                [
                    "",
                    "New explicit memories stored for future sessions:",
                    ", ".join(stored_ids),
                ]
            )

        if recalled:
            response_parts.extend(
                [
                    "",
                    "Support answer:",
                    (
                        "I will use the recalled preferences above instead of asking "
                        "you to repeat them."
                    ),
                ]
            )
        else:
            response_parts.extend(
                [
                    "",
                    "Support answer:",
                    (
                        "I do not have prior context for this request yet. I stored "
                        "any explicit facts or preferences you gave me."
                    ),
                ]
            )

        return {"response": "\n".join(response_parts)}

    builder = StateGraph(SupportState)
    builder.add_node("recall_context", recall_context)
    builder.add_node("remember_context", remember_context)
    builder.add_node("draft_response", draft_response)
    builder.add_edge(START, "recall_context")
    builder.add_edge("recall_context", "remember_context")
    builder.add_edge("remember_context", "draft_response")
    builder.add_edge("draft_response", END)
    return builder.compile()
