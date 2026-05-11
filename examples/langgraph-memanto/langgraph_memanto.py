"""LangGraph + Memanto cross-session memory example.

The example is intentionally small enough to read in one sitting:

1. Session one teaches the agent a customer's preferences.
2. Memanto stores those facts outside LangGraph state.
3. Session two starts with fresh state and recalls the prior memories.

Run in offline mode by default:

    python run_demo.py

Set ``MEMANTO_BACKEND=memanto`` and ``MOORCHEH_API_KEY`` to use a real
Memanto namespace through the packaged SDK client.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypedDict

from langgraph.graph import END, START, StateGraph


AGENT_ID = "langgraph-memanto-support-agent"
LOCAL_MEMORY_FILE = Path(__file__).with_name(".local_memories.json")


class Memory(TypedDict):
    title: str
    content: str
    tags: list[str]


class SupportState(TypedDict):
    session_id: str
    customer_id: str
    message: str
    recalled_memories: list[Memory]
    response: str


class MemoryStore(Protocol):
    """Minimal adapter shape used by the LangGraph nodes."""

    def remember(self, customer_id: str, title: str, content: str) -> None:
        """Store one durable customer memory."""

    def recall(self, customer_id: str, query: str, limit: int = 5) -> list[Memory]:
        """Retrieve durable customer memories relevant to ``query``."""


@dataclass
class LocalJsonMemoryStore:
    """Offline memory adapter used for demos, tests, and PR review."""

    path: Path = LOCAL_MEMORY_FILE

    def _load(self) -> dict[str, list[Memory]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, list[Memory]]) -> None:
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def remember(self, customer_id: str, title: str, content: str) -> None:
        data = self._load()
        data.setdefault(customer_id, []).append(
            {"title": title, "content": content, "tags": ["support", customer_id]}
        )
        self._save(data)

    def recall(self, customer_id: str, query: str, limit: int = 5) -> list[Memory]:
        del query
        return self._load().get(customer_id, [])[-limit:]


class MemantoSdkMemoryStore:
    """Production adapter that stores memories in Memanto."""

    def __init__(self, api_key: str, agent_id: str = AGENT_ID) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="tool",
                description="LangGraph support agent with durable Memanto memory",
            )
        except Exception:
            pass
        self.client.activate_agent(agent_id, duration_hours=6)

    def remember(self, customer_id: str, title: str, content: str) -> None:
        self.client.remember(
            agent_id=self.agent_id,
            memory_type="preference",
            title=title,
            content=content,
            confidence=0.9,
            tags=["langgraph", "support", customer_id],
            source="langgraph-demo",
            provenance="explicit_statement",
        )

    def recall(self, customer_id: str, query: str, limit: int = 5) -> list[Memory]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            tags=[customer_id],
        )
        memories: list[Memory] = []
        for item in result.get("memories", []):
            memories.append(
                {
                    "title": str(item.get("title", "memory")),
                    "content": str(item.get("content", "")),
                    "tags": list(item.get("tags", [])),
                }
            )
        return memories


def build_memory_store() -> MemoryStore:
    """Select the review-friendly local adapter or real Memanto backend."""

    if os.getenv("MEMANTO_BACKEND") == "memanto":
        api_key = os.getenv("MOORCHEH_API_KEY")
        if not api_key:
            raise RuntimeError("MOORCHEH_API_KEY is required for MEMANTO_BACKEND=memanto")
        return MemantoSdkMemoryStore(api_key)
    return LocalJsonMemoryStore()


def extract_customer_facts(state: SupportState, store: MemoryStore) -> SupportState:
    """Persist obvious support facts from the current session."""

    text = state["message"].lower()
    if "dark mode" in text:
        store.remember(
            state["customer_id"],
            "UI preference",
            "Customer prefers dark mode for account dashboards.",
        )
    if "renewal" in text and "friday" in text:
        store.remember(
            state["customer_id"],
            "Renewal timing",
            "Customer wants renewal reminders sent on Friday mornings.",
        )
    if "sms" in text:
        store.remember(
            state["customer_id"],
            "Contact channel",
            "Customer prefers SMS follow-ups for urgent billing issues.",
        )
    return state


def recall_customer_context(state: SupportState, store: MemoryStore) -> SupportState:
    """Load durable memory into a fresh LangGraph state."""

    memories = store.recall(
        state["customer_id"],
        f"support context for {state['message']}",
    )
    return {**state, "recalled_memories": memories}


def draft_support_reply(state: SupportState) -> SupportState:
    """Draft a deterministic response using current message plus recalled memory."""

    if not state["recalled_memories"]:
        response = "I can help with that. I do not have prior preferences yet."
    else:
        remembered = "; ".join(memory["content"] for memory in state["recalled_memories"])
        response = (
            "I can help with that. I remembered this from prior sessions: "
            f"{remembered}"
        )
    return {**state, "response": response}


def build_graph(store: MemoryStore):
    """Create the LangGraph workflow."""

    graph = StateGraph(SupportState)
    graph.add_node("recall_customer_context", lambda state: recall_customer_context(state, store))
    graph.add_node("draft_support_reply", draft_support_reply)
    graph.add_node("extract_customer_facts", lambda state: extract_customer_facts(state, store))

    graph.add_edge(START, "recall_customer_context")
    graph.add_edge("recall_customer_context", "draft_support_reply")
    graph.add_edge("draft_support_reply", "extract_customer_facts")
    graph.add_edge("extract_customer_facts", END)
    return graph.compile()
