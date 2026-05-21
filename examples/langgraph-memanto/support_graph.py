from __future__ import annotations

import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from memory_store import MemoryHit, MemoryStore


class SupportState(TypedDict):
    user_id: str
    message: str
    recalled_memories: list[str]
    extracted_preferences: list[str]
    response: str


PREFERENCE_PATTERNS = (
    re.compile(r"\bi prefer (?P<value>.+)", re.IGNORECASE),
    re.compile(r"\bremember that (?P<value>.+)", re.IGNORECASE),
    re.compile(r"\bmy preference is (?P<value>.+)", re.IGNORECASE),
)


def _memory_lines(memories: list[MemoryHit]) -> list[str]:
    return [f"{item.memory_type}: {item.content}" for item in memories]


def _extract_preferences(message: str) -> list[str]:
    preferences: list[str] = []
    for pattern in PREFERENCE_PATTERNS:
        match = pattern.search(message)
        if match:
            preferences.append(match.group("value").strip().rstrip("."))
    return preferences


def build_support_graph(memory_store: MemoryStore):
    def recall_memories(state: SupportState) -> dict[str, list[str]]:
        memories = memory_store.recall(
            user_id=state["user_id"],
            query=state["message"],
            limit=5,
        )
        return {"recalled_memories": _memory_lines(memories)}

    def draft_response(state: SupportState) -> dict[str, str]:
        recalled = state.get("recalled_memories", [])
        if recalled:
            memory_context = " ".join(recalled)
            response = (
                "I found prior Memanto memory for this fresh graph run: "
                f"{memory_context} Based on that, I would keep the dashboard concise "
                "and use dark-mode-friendly defaults."
            )
        else:
            response = (
                "I do not have prior Memanto memory for this user yet. "
                "I can answer normally and save any durable preferences you share."
            )
        return {"response": response}

    def store_new_preferences(state: SupportState) -> dict[str, list[str]]:
        preferences = _extract_preferences(state["message"])
        for preference in preferences:
            memory_store.remember_preference(
                user_id=state["user_id"],
                content=preference,
            )
        return {"extracted_preferences": preferences}

    builder = StateGraph(SupportState)
    builder.add_node("recall_memories", recall_memories)
    builder.add_node("draft_response", draft_response)
    builder.add_node("store_new_preferences", store_new_preferences)
    builder.add_edge(START, "recall_memories")
    builder.add_edge("recall_memories", "draft_response")
    builder.add_edge("draft_response", "store_new_preferences")
    builder.add_edge("store_new_preferences", END)
    return builder.compile()


def run_support_turn(memory_store: MemoryStore, user_id: str, message: str) -> SupportState:
    graph = build_support_graph(memory_store)
    return graph.invoke(
        {
            "user_id": user_id,
            "message": message,
            "recalled_memories": [],
            "extracted_preferences": [],
            "response": "",
        }
    )

