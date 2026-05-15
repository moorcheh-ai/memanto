"""LangGraph support agent backed by persistent Memanto memory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from memanto_client import JsonMemoryClient, MemantoMemoryClient, Memory


class MemoryClient(Protocol):
    def setup(self) -> None: ...

    def remember(self, memory: Memory) -> dict: ...

    def recall(self, query: str, limit: int = 5) -> list[dict]: ...


class SupportState(TypedDict):
    user_id: str
    message: str
    recalled_memories: list[dict]
    reply: str
    memories_to_store: list[Memory]


def build_memory_client() -> MemoryClient:
    load_dotenv()
    dry_run = os.getenv("MEMANTO_DRY_RUN", "1") == "1"
    if dry_run:
        store = os.getenv("MEMANTO_DRY_RUN_STORE", ".memanto-demo-store.json")
        return JsonMemoryClient(Path(store))

    base_url = os.getenv("MEMANTO_BASE_URL", "http://127.0.0.1:8000")
    agent_id = os.getenv("MEMANTO_AGENT_ID", "langgraph-support-agent")
    return MemantoMemoryClient(base_url=base_url, agent_id=agent_id)


def build_graph(memory_client: MemoryClient):
    memory_client.setup()

    def recall_context(state: SupportState) -> SupportState:
        query = f"{state['user_id']} preferences delivery support history"
        state["recalled_memories"] = memory_client.recall(query, limit=5)
        return state

    def draft_reply(state: SupportState) -> SupportState:
        memory_text = "\n".join(
            f"- {item.get('content', item)}" for item in state["recalled_memories"]
        )
        if not memory_text:
            memory_text = "- No prior memories found."

        prefers_sms = "sms" in memory_text.lower()
        channel = "SMS" if prefers_sms else "email"
        state["reply"] = (
            f"I found your previous support context:\n{memory_text}\n\n"
            f"I will send the replacement update by {channel} and keep the tone brief."
        )
        return state

    def extract_memories(state: SupportState) -> SupportState:
        message = state["message"].lower()
        memories: list[Memory] = []
        if "sms" in message:
            memories.append(
                Memory(
                    content=(
                        f"{state['user_id']} prefers SMS updates for urgent delivery "
                        "or replacement issues."
                    ),
                    type="preference",
                    title="Customer prefers SMS updates",
                    tags=["support", "communication", state["user_id"]],
                )
            )
        if "brief" in message or "concise" in message:
            memories.append(
                Memory(
                    content=f"{state['user_id']} prefers brief, concise support replies.",
                    type="preference",
                    title="Customer prefers concise replies",
                    tags=["support", "tone", state["user_id"]],
                )
            )
        state["memories_to_store"] = memories
        return state

    def persist_memories(state: SupportState) -> SupportState:
        for memory in state["memories_to_store"]:
            memory_client.remember(memory)
        return state

    graph = StateGraph(SupportState)
    graph.add_node("recall_context", recall_context)
    graph.add_node("draft_reply", draft_reply)
    graph.add_node("extract_memories", extract_memories)
    graph.add_node("persist_memories", persist_memories)

    graph.set_entry_point("recall_context")
    graph.add_edge("recall_context", "draft_reply")
    graph.add_edge("draft_reply", "extract_memories")
    graph.add_edge("extract_memories", "persist_memories")
    graph.add_edge("persist_memories", END)
    return graph.compile()


def run_support_turn(user_id: str, message: str) -> SupportState:
    graph = build_graph(build_memory_client())
    return graph.invoke(
        {
            "user_id": user_id,
            "message": message,
            "recalled_memories": [],
            "reply": "",
            "memories_to_store": [],
        }
    )
