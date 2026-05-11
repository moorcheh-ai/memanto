"""LangGraph + Memanto cross-session memory demo.

This example keeps LangGraph's per-run state deliberately small while using
Memanto as the long-term memory layer. Run the "yesterday" session to store a
traveler's preferences, then run the "today" session with a fresh graph state.
The second run recalls the old preferences from memory, not from the current
state payload.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict

from langgraph.graph import END, StateGraph

MemoryType = Literal[
    "fact",
    "preference",
    "goal",
    "decision",
    "artifact",
    "learning",
    "event",
    "instruction",
    "relationship",
    "context",
    "observation",
    "commitment",
    "error",
]

VALID_MEMORY_TYPES: set[str] = {
    "instruction",
    "fact",
    "decision",
    "goal",
    "commitment",
    "preference",
    "relationship",
    "context",
    "event",
    "learning",
    "observation",
    "artifact",
    "error",
}


@dataclass(slots=True)
class StoredMemory:
    """Minimal memory record shared by local and Memanto-backed stores."""

    memory_type: MemoryType
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.9
    session_id: str = "unknown"
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )


class MemoryStore(Protocol):
    """Storage boundary used by the LangGraph nodes."""

    def remember(self, memory: StoredMemory) -> str:
        """Persist a memory and return its identifier."""

    def recall(
        self,
        query: str,
        *,
        memory_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[StoredMemory]:
        """Recall memories relevant to *query*."""


class LocalJsonMemoryStore:
    """Small deterministic memory store for offline demos and tests.

    The production path is ``MemantoMemoryStore`` below. This local store exists
    so reviewers can run the LangGraph flow without creating API keys.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def remember(self, memory: StoredMemory) -> str:
        records = self._load()
        memory_id = f"local-{len(records) + 1}"
        records.append({"id": memory_id, **asdict(memory)})
        self._save(records)
        return memory_id

    def recall(
        self,
        query: str,
        *,
        memory_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[StoredMemory]:
        records = self._load()
        query_tokens = _tokenize(query)
        scored: list[tuple[int, int, dict[str, Any]]] = []

        for index, record in enumerate(records):
            if memory_types and record["memory_type"] not in memory_types:
                continue
            haystack = " ".join(
                [
                    record["title"],
                    record["content"],
                    " ".join(record.get("tags", [])),
                ]
            )
            overlap = len(query_tokens & _tokenize(haystack))
            if overlap or not query_tokens:
                scored.append((overlap, index, record))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [
            StoredMemory(
                memory_type=item[2]["memory_type"],
                title=item[2]["title"],
                content=item[2]["content"],
                tags=list(item[2].get("tags", [])),
                confidence=float(item[2].get("confidence", 0.9)),
                session_id=item[2].get("session_id", "unknown"),
                created_at=item[2].get("created_at", ""),
            )
            for item in scored[:limit]
        ]

    def reset(self) -> None:
        self._save([])

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, records: list[dict[str, Any]]) -> None:
        self.path.write_text(
            json.dumps(records, indent=2, sort_keys=True),
            encoding="utf-8",
        )


class MemantoMemoryStore:
    """Adapter that stores and recalls memories through Memanto's SDK client."""

    def __init__(self, api_key: str, agent_id: str) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="tool",
                description="LangGraph travel concierge memory demo",
            )
        except Exception:
            # Reusing an existing demo agent is fine.
            pass
        self.client.activate_agent(agent_id, duration_hours=6)

    @classmethod
    def from_env(cls, agent_id: str) -> MemantoMemoryStore:
        api_key = os.environ.get("MOORCHEH_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "MOORCHEH_API_KEY is required for --backend memanto. "
                "Use --backend local for the offline demo."
            )
        return cls(api_key=api_key, agent_id=agent_id)

    def remember(self, memory: StoredMemory) -> str:
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory.memory_type,
            title=memory.title,
            content=memory.content,
            confidence=memory.confidence,
            tags=memory.tags,
            source="langgraph-memanto-example",
            provenance="explicit_statement",
        )
        return str(result.get("memory_id", "memanto-memory"))

    def recall(
        self,
        query: str,
        *,
        memory_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[StoredMemory]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=memory_types,
        )
        memories = result.get("memories", result if isinstance(result, list) else [])
        return [_coerce_memanto_memory(item) for item in memories[:limit]]


class ConciergeState(TypedDict, total=False):
    user_id: str
    session_label: str
    message: str
    recalled_memories: list[StoredMemory]
    stored_memory_ids: list[str]
    response: str


def build_graph(store: MemoryStore):
    """Build the LangGraph workflow with Memanto as an external dependency."""

    def recall_node(state: ConciergeState) -> ConciergeState:
        query = (
            f"{state['user_id']} travel preferences constraints destination "
            f"{state['message']}"
        )
        memories = store.recall(
            query,
            memory_types=["preference", "fact", "goal", "context"],
            limit=6,
        )
        return {**state, "recalled_memories": memories}

    def draft_node(state: ConciergeState) -> ConciergeState:
        memories = state.get("recalled_memories", [])
        response = draft_concierge_response(state["message"], memories)
        return {**state, "response": response}

    def persist_node(state: ConciergeState) -> ConciergeState:
        extracted = extract_travel_memories(
            message=state["message"],
            session_id=state["session_label"],
        )
        stored_ids = [store.remember(memory) for memory in extracted]
        return {**state, "stored_memory_ids": stored_ids}

    graph = StateGraph(ConciergeState)
    graph.add_node("recall_memories", recall_node)
    graph.add_node("draft_response", draft_node)
    graph.add_node("persist_new_memories", persist_node)
    graph.set_entry_point("recall_memories")
    graph.add_edge("recall_memories", "draft_response")
    graph.add_edge("draft_response", "persist_new_memories")
    graph.add_edge("persist_new_memories", END)
    return graph.compile()


def run_session(
    store: MemoryStore,
    *,
    message: str,
    session_label: str,
    user_id: str = "taku",
) -> ConciergeState:
    graph = build_graph(store)
    initial_state: ConciergeState = {
        "user_id": user_id,
        "session_label": session_label,
        "message": message,
    }
    return graph.invoke(initial_state)


def extract_travel_memories(message: str, session_id: str) -> list[StoredMemory]:
    """Extract deterministic memories from the user's latest travel message."""

    lowered = message.lower()
    memories: list[StoredMemory] = []

    if "vegetarian" in lowered or "vegan" in lowered:
        memories.append(
            StoredMemory(
                memory_type="preference",
                title="Meal preference",
                content="The traveler prefers vegetarian meal options.",
                tags=["travel", "meal", "preference"],
                session_id=session_id,
            )
        )

    if "aisle" in lowered:
        memories.append(
            StoredMemory(
                memory_type="preference",
                title="Seat preference",
                content="The traveler prefers aisle seats when flying.",
                tags=["travel", "flight", "seat"],
                session_id=session_id,
            )
        )

    destination = _extract_destination(message)
    if destination:
        memories.append(
            StoredMemory(
                memory_type="goal",
                title="Active destination",
                content=f"The traveler is planning a trip to {destination}.",
                tags=["travel", "destination", destination.lower()],
                session_id=session_id,
            )
        )

    if "next tuesday" in lowered:
        memories.append(
            StoredMemory(
                memory_type="context",
                title="Travel timing",
                content="The traveler mentioned a departure next Tuesday.",
                tags=["travel", "date"],
                session_id=session_id,
            )
        )

    if not memories:
        memories.append(
            StoredMemory(
                memory_type="observation",
                title="Latest travel request",
                content=f"Traveler said: {message[:420]}",
                tags=["travel", "request"],
                session_id=session_id,
                confidence=0.75,
            )
        )

    return memories


def draft_concierge_response(message: str, memories: list[StoredMemory]) -> str:
    if not memories:
        return (
            "I do not have long-term travel memories yet, so I would ask for "
            "meal, seat, timing, and destination preferences before booking."
        )

    bullets = "\n".join(f"- {memory.content}" for memory in memories)
    return (
        "I recalled these long-term memories before responding:\n"
        f"{bullets}\n\n"
        "Plan: choose options that preserve those constraints, then ask only "
        "for missing details. Current request: "
        f"{message}"
    )


def _coerce_memanto_memory(item: Any) -> StoredMemory:
    if hasattr(item, "model_dump"):
        item = item.model_dump(mode="json")
    if not isinstance(item, dict):
        item = {"content": str(item)}

    content = (
        item.get("content")
        or item.get("text")
        or item.get("memory")
        or item.get("document")
        or ""
    )
    memory_type = item.get("memory_type") or item.get("type") or "observation"
    if memory_type not in VALID_MEMORY_TYPES:
        memory_type = "observation"
    return StoredMemory(
        memory_type=memory_type,
        title=item.get("title") or content[:80] or "Memanto memory",
        content=content,
        tags=list(item.get("tags") or []),
        confidence=float(item.get("confidence", 0.9)),
        session_id=item.get("session_id", "memanto"),
        created_at=item.get("created_at", ""),
    )


def _extract_destination(message: str) -> str | None:
    match = re.search(r"\bto\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)", message)
    if match:
        return match.group(1)
    return None


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2
    }


def _create_store(args: argparse.Namespace) -> MemoryStore:
    if args.backend == "memanto":
        return MemantoMemoryStore.from_env(agent_id=args.agent_id)

    store = LocalJsonMemoryStore(Path(args.store_path))
    if args.reset_local:
        store.reset()
    return store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["local", "memanto"], default="local")
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("MEMANTO_AGENT_ID", "langgraph-travel-concierge"),
    )
    parser.add_argument(
        "--store-path",
        default="examples/langgraph-memanto/.local_memory.json",
    )
    parser.add_argument(
        "--session",
        choices=["yesterday", "today", "full"],
        default="full",
    )
    parser.add_argument("--reset-local", action="store_true")
    args = parser.parse_args()

    store = _create_store(args)
    sessions = []
    if args.session in {"yesterday", "full"}:
        sessions.append(
            (
                "yesterday",
                "I am Taku. I prefer vegetarian meals, need aisle seats, "
                "and I am traveling to Lisbon next Tuesday.",
            )
        )
    if args.session in {"today", "full"}:
        sessions.append(
            (
                "today",
                "Please suggest a flight and hotel that fit my usual constraints.",
            )
        )

    for label, message in sessions:
        result = run_session(store, message=message, session_label=label)
        print(f"\n=== {label.upper()} SESSION ===")
        print(result["response"])
        if result.get("stored_memory_ids"):
            print("Stored:", ", ".join(result["stored_memory_ids"]))


if __name__ == "__main__":
    main()
