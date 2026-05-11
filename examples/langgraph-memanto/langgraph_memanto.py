"""LangGraph + Memanto cross-session memory example.

This example keeps LangGraph state intentionally short-lived while storing
durable support memories in Memanto. A local JSON adapter is included so the
demo and validation can run without API keys; the SDK adapter uses Memanto's
real ``SdkClient`` when ``MOORCHEH_API_KEY`` is available.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, TypedDict

from langgraph.graph import END, StateGraph

try:
    from memanto.cli.client.sdk_client import SdkClient
except Exception:  # pragma: no cover - local mode does not need the package
    SdkClient = None  # type: ignore[assignment]


DEFAULT_AGENT_ID = "langgraph-memanto-support"
LOCAL_MEMORY_FILE = Path(__file__).with_name(".local_memories.json")


class MemoryRecord(TypedDict):
    title: str
    content: str
    type: str
    confidence: float
    tags: list[str]
    created_at: str


class SupportState(TypedDict):
    session_id: str
    customer_id: str
    message: str
    recalled_memories: list[MemoryRecord]
    response: str
    memory_written: str


class MemoryAdapter(Protocol):
    """Minimal memory contract used by the LangGraph nodes."""

    def remember(
        self,
        *,
        title: str,
        content: str,
        memory_type: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> str:
        """Persist one memory and return a memory id."""

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[MemoryRecord]:
        """Return relevant memories for the query."""


@dataclass
class LocalMemoryAdapter:
    """Small JSON-backed adapter for offline review and CI."""

    path: Path = LOCAL_MEMORY_FILE

    def _read(self) -> list[MemoryRecord]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, memories: list[MemoryRecord]) -> None:
        self.path.write_text(json.dumps(memories, indent=2), encoding="utf-8")

    def clear(self) -> None:
        self._write([])

    def remember(
        self,
        *,
        title: str,
        content: str,
        memory_type: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> str:
        memories = self._read()
        memory_id = f"local-{len(memories) + 1}"
        memories.append(
            {
                "title": title,
                "content": content,
                "type": memory_type,
                "confidence": confidence,
                "tags": tags,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._write(memories)
        return memory_id

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[MemoryRecord]:
        terms = {
            token.lower().strip(".,:;!?()[]")
            for token in query.split()
            if len(token.strip(".,:;!?()[]")) >= 3
        }

        scored: list[tuple[int, MemoryRecord]] = []
        for memory in self._read():
            if memory_types and memory["type"] not in memory_types:
                continue
            haystack = " ".join(
                [memory["title"], memory["content"], " ".join(memory["tags"])]
            ).lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, memory))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:limit]]


@dataclass
class MemantoSdkAdapter:
    """Adapter around Memanto's real SDK client."""

    api_key: str
    agent_id: str = DEFAULT_AGENT_ID

    def __post_init__(self) -> None:
        if SdkClient is None:
            raise RuntimeError("memanto package is not importable")
        self.client = SdkClient(api_key=self.api_key)
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="support",
                description="LangGraph support workflow durable memory demo",
            )
        except Exception:
            pass
        self.client.activate_agent(self.agent_id)

    def remember(
        self,
        *,
        title: str,
        content: str,
        memory_type: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> str:
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
            source="langgraph-memanto-example",
            provenance="explicit_statement",
        )
        return str(result.get("memory_id", "memanto-memory"))

    def recall(
        self,
        *,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[MemoryRecord]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=memory_types,
        )
        memories = result.get("memories", [])
        return [
            {
                "title": str(memory.get("title", "Untitled")),
                "content": str(memory.get("content", "")),
                "type": str(memory.get("type", "context")),
                "confidence": float(memory.get("confidence", 0.0) or 0.0),
                "tags": list(memory.get("tags", [])),
                "created_at": str(memory.get("created_at", "")),
            }
            for memory in memories
        ]


def build_adapter(mode: str) -> MemoryAdapter:
    if mode == "local":
        return LocalMemoryAdapter()

    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    if not api_key:
        raise RuntimeError("MOORCHEH_API_KEY is required for --backend memanto")
    return MemantoSdkAdapter(api_key=api_key)


def load_memories(adapter: MemoryAdapter):
    def node(state: SupportState) -> SupportState:
        query = (
            f"customer {state['customer_id']} preferences order approvals "
            f"tone escalation {state['message']}"
        )
        state["recalled_memories"] = adapter.recall(
            query=query,
            limit=6,
            memory_types=["fact", "preference", "instruction", "commitment"],
        )
        return state

    return node


def draft_response(state: SupportState) -> SupportState:
    memories = state["recalled_memories"]
    memory_lines = [f"- {memory['title']}: {memory['content']}" for memory in memories]
    remembered = "\n".join(memory_lines) if memory_lines else "- no durable memory found"

    state["response"] = (
        f"Support reply for {state['customer_id']}:\n"
        f"I found these durable memories outside the current LangGraph state:\n"
        f"{remembered}\n\n"
        f"Current request: {state['message']}\n"
        "Action: respond using the remembered policy, tone, and customer context."
    )
    return state


def write_followup_memory(adapter: MemoryAdapter):
    def node(state: SupportState) -> SupportState:
        memory_id = adapter.remember(
            title=f"{state['customer_id']} latest support request",
            content=(
                f"During {state['session_id']}, customer {state['customer_id']} "
                f"asked: {state['message']}"
            ),
            memory_type="event",
            tags=["langgraph", "support", state["customer_id"].lower()],
            confidence=0.85,
        )
        state["memory_written"] = memory_id
        return state

    return node


def build_graph(adapter: MemoryAdapter):
    graph = StateGraph(SupportState)
    graph.add_node("load_memories", load_memories(adapter))
    graph.add_node("draft_response", draft_response)
    graph.add_node("write_followup_memory", write_followup_memory(adapter))

    graph.set_entry_point("load_memories")
    graph.add_edge("load_memories", "draft_response")
    graph.add_edge("draft_response", "write_followup_memory")
    graph.add_edge("write_followup_memory", END)
    return graph.compile()


def seed_day_one(adapter: MemoryAdapter) -> None:
    """Store memories that a later fresh graph run must recall."""
    adapter.remember(
        title="Ada reply tone",
        content="Customer CUST-042 prefers concise replies with bullet points.",
        memory_type="preference",
        tags=["cust-042", "tone", "support"],
        confidence=0.95,
    )
    adapter.remember(
        title="Ada order approval rule",
        content="For order AR-8841, offer a replacement before issuing a refund.",
        memory_type="instruction",
        tags=["cust-042", "ar-8841", "refund"],
        confidence=0.93,
    )
    adapter.remember(
        title="Ada escalated shipment",
        content="Customer CUST-042 had a delayed shipment on AR-8841 yesterday.",
        memory_type="fact",
        tags=["cust-042", "ar-8841", "shipment"],
        confidence=0.9,
    )


def run_support_session(adapter: MemoryAdapter) -> SupportState:
    graph = build_graph(adapter)
    initial_state: SupportState = {
        "session_id": "day-two-fresh-thread",
        "customer_id": "CUST-042",
        "message": "Ada asks whether the delayed AR-8841 package can be refunded.",
        "recalled_memories": [],
        "response": "",
        "memory_written": "",
    }
    return graph.invoke(initial_state)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["local", "memanto"], default="local")
    parser.add_argument("--reset-local", action="store_true")
    args = parser.parse_args()

    adapter = build_adapter(args.backend)
    if args.reset_local and isinstance(adapter, LocalMemoryAdapter):
        adapter.clear()

    seed_day_one(adapter)
    result = run_support_session(adapter)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
