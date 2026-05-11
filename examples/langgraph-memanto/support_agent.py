"""LangGraph + Memanto cross-session support memory demo.

The example is intentionally deterministic: it demonstrates the integration
pattern without requiring LLM or Memanto API keys. Swap the adapter with a real
Memanto SdkClient-backed implementation for production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph


class SupportState(TypedDict, total=False):
    session_id: str
    user_id: str
    ticket: str
    recalled_memories: list[str]
    stored_memories: list[str]
    response_plan: str


@dataclass
class MemoryRecord:
    memory_type: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)


class InMemoryMemantoAdapter:
    """Tiny Memanto-shaped adapter for local demos and tests."""

    def __init__(self) -> None:
        self._records: dict[str, list[MemoryRecord]] = {}

    def remember(
        self,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        record = MemoryRecord(
            memory_type=memory_type,
            title=title,
            content=content,
            tags=tags or [],
        )
        self._records.setdefault(agent_id, []).append(record)
        return {"memory_id": f"{agent_id}:{len(self._records[agent_id])}"}

    def recall(self, agent_id: str, query: str, limit: int = 5) -> list[MemoryRecord]:
        query_terms = {term.lower() for term in query.split()}
        records = self._records.get(agent_id, [])

        scored: list[tuple[int, MemoryRecord]] = []
        for record in records:
            haystack = " ".join(
                [record.memory_type, record.title, record.content, *record.tags]
            ).lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score:
                scored.append((score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in scored[:limit]]

    def answer(self, agent_id: str, question: str) -> str:
        memories = self.recall(agent_id, question, limit=3)
        if not memories:
            return "No durable memory found."
        return " ".join(memory.content for memory in memories)


def build_support_graph(memory: InMemoryMemantoAdapter, agent_id: str):
    graph = StateGraph(SupportState)

    def recall_preferences(state: SupportState) -> SupportState:
        memories = memory.recall(
            agent_id=agent_id,
            query=f"{state['user_id']} support preference communication follow-up",
            limit=5,
        )
        return {
            **state,
            "recalled_memories": [item.content for item in memories],
        }

    def extract_and_store_preferences(state: SupportState) -> SupportState:
        stored = []
        ticket = state["ticket"].lower()
        user_id = state["user_id"]

        if "short" in ticket or "concise" in ticket:
            content = "User prefers concise support answers."
            memory.remember(
                agent_id=agent_id,
                memory_type="preference",
                title=f"{user_id} concise answers",
                content=content,
                tags=[user_id, "support", "communication"],
            )
            stored.append(f"preference: {content}")

        if "email" in ticket:
            content = "User prefers email follow-up."
            memory.remember(
                agent_id=agent_id,
                memory_type="preference",
                title=f"{user_id} email follow-up",
                content=content,
                tags=[user_id, "support", "follow-up"],
            )
            stored.append(f"preference: {content}")

        return {**state, "stored_memories": stored}

    def plan_response(state: SupportState) -> SupportState:
        memories = " ".join(state.get("recalled_memories", []))
        tone = "a concise tone" if "concise" in memories.lower() else "normal detail"
        channel = "email" if "email" in memories.lower() else "the current channel"
        return {
            **state,
            "response_plan": f"Use {tone} and send the follow-up over {channel}.",
        }

    graph.add_node("recall_preferences", recall_preferences)
    graph.add_node("extract_and_store_preferences", extract_and_store_preferences)
    graph.add_node("plan_response", plan_response)

    graph.set_entry_point("recall_preferences")
    graph.add_edge("recall_preferences", "extract_and_store_preferences")
    graph.add_edge("extract_and_store_preferences", "plan_response")
    graph.add_edge("plan_response", END)

    return graph.compile()


def run_demo() -> tuple[SupportState, SupportState]:
    agent_id = "support-agent"
    memory = InMemoryMemantoAdapter()
    app = build_support_graph(memory, agent_id)

    session_1 = app.invoke(
        {
            "session_id": "2026-05-10",
            "user_id": "customer-42",
            "ticket": "Please keep replies short and follow up by email.",
        }
    )

    session_2 = app.invoke(
        {
            "session_id": "2026-05-11",
            "user_id": "customer-42",
            "ticket": "My invoice export is failing again.",
        }
    )

    return session_1, session_2


def main() -> None:
    session_1, session_2 = run_demo()

    print("Session 1 stored memories:")
    for memory in session_1["stored_memories"]:
        print(f"- {memory}")

    print("\nSession 2 recalled memories:")
    for memory in session_2["recalled_memories"]:
        print(f"- {memory}")

    print("\nFinal response plan:")
    print(session_2["response_plan"])


if __name__ == "__main__":
    main()
