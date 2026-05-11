#!/usr/bin/env python3
"""
LangGraph + Memanto support agent example.

The graph keeps short-lived turn data in LangGraph state and stores durable
customer facts in Memanto. Run the "yesterday" session first, then run "today"
to prove that the agent can recall context that is not present in the current
thread state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

try:
    from memanto.cli.client.sdk_client import SdkClient
except ImportError:  # pragma: no cover - documented setup covers this path.
    SdkClient = None  # type: ignore[assignment]


AGENT_ID = "langgraph-support-memory"
CUSTOMER_ID = "acme-dana"
DEMO_MEMORY_PATH = Path(__file__).with_name(".local_memories.json")

YESTERDAY_MESSAGE = (
    "Hi, I am Dana from Acme. Please send SMS updates for ticket T-42. "
    "Our Enterprise SLA is two hours for checkout incidents."
)

TODAY_MESSAGE = (
    "Any update on ticket T-42? The checkout failure is still blocking launch."
)


@dataclass
class MemoryItem:
    """Normalized memory record used by both Memanto and the local demo backend."""

    type: str
    title: str
    content: str
    confidence: float = 0.9
    tags: list[str] = field(default_factory=list)
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SupportState(TypedDict, total=False):
    """LangGraph state: current-thread data only."""

    customer_id: str
    session_name: str
    incoming_message: str
    current_thread: list[str]
    recalled_memories: list[dict[str, Any]]
    response: str
    stored_memories: list[dict[str, Any]]


class LongTermMemory(Protocol):
    """Storage boundary used by the LangGraph nodes."""

    backend_name: str

    def remember(self, memory: MemoryItem) -> dict[str, Any]:
        """Store one durable memory."""

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return durable memories relevant to the query."""

    def close(self) -> None:
        """Release backend resources."""


class JsonLongTermMemory:
    """Tiny file-backed backend for demos and tests without API keys."""

    backend_name = "local-json"

    def __init__(self, path: Path = DEMO_MEMORY_PATH) -> None:
        self.path = path

    def reset(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def remember(self, memory: MemoryItem) -> dict[str, Any]:
        records = self._load()
        record = asdict(memory)
        records.append(record)
        self.path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        return record

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        records = self._load()
        query_terms = set(_terms(query))
        ranked: list[tuple[int, dict[str, Any]]] = []

        for record in records:
            if memory_types and record.get("type") not in memory_types:
                continue

            haystack = " ".join(
                [
                    str(record.get("title", "")),
                    str(record.get("content", "")),
                    " ".join(record.get("tags", [])),
                ]
            )
            score = len(query_terms.intersection(_terms(haystack)))
            if score:
                ranked.append((score, record))

        ranked.sort(key=lambda item: (item[0], item[1].get("created_at", "")), reverse=True)
        return [record for _, record in ranked[:limit]]

    def close(self) -> None:
        return None

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))


class MemantoLongTermMemory:
    """Memanto-backed durable memory adapter."""

    backend_name = "memanto"

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str = AGENT_ID,
        duration_hours: int = 6,
    ) -> None:
        if SdkClient is None:
            raise RuntimeError(
                "Install memanto in editable mode first: pip install -e ../.."
            )

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)

        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="support",
                description="LangGraph support agent using Memanto long-term memory.",
            )
        except Exception:
            # Reuse the agent if it already exists. Creation may also race with
            # a previous demo run, which is fine for this example.
            pass

        self.client.activate_agent(agent_id, duration_hours=duration_hours)

    def remember(self, memory: MemoryItem) -> dict[str, Any]:
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory.type,
            title=memory.title[:100],
            content=memory.content[:500],
            confidence=memory.confidence,
            tags=memory.tags,
            source="langgraph-demo",
            provenance="explicit_statement",
        )
        return {
            **asdict(memory),
            "memory_id": result.get("memory_id", memory.memory_id),
            "namespace": result.get("namespace"),
            "status": result.get("status"),
        }

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=memory_types,
        )
        return [_normalize_memanto_memory(memory) for memory in result.get("memories", [])]

    def close(self) -> None:
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            pass


def build_support_graph(memory: LongTermMemory):
    """Build the LangGraph workflow with Memanto as the long-term memory layer."""

    graph = StateGraph(SupportState)

    def recall_customer_context(state: SupportState) -> dict[str, Any]:
        query = (
            f"{state['customer_id']} {state['incoming_message']} "
            "preferences sla support commitments"
        )
        memories = memory.recall(
            query,
            limit=5,
            memory_types=["preference", "fact", "commitment"],
        )
        return {"recalled_memories": memories}

    def draft_support_response(state: SupportState) -> dict[str, str]:
        memory_text = " ".join(
            str(item.get("content", "")) for item in state.get("recalled_memories", [])
        ).lower()

        channel = "the ticket thread"
        if "sms" in memory_text:
            channel = "SMS"

        priority = "normal support priority"
        if "enterprise" in memory_text or "two hours" in memory_text:
            priority = "the Enterprise two-hour SLA"

        if state.get("recalled_memories"):
            response = (
                "I found durable customer context outside this LangGraph thread: "
                f"use {channel} updates and handle T-42 under {priority}. "
                "I will keep the customer posted without asking them to repeat it."
            )
        else:
            response = (
                "I do not have durable customer context yet. I will ask for the "
                "preferred update channel and SLA before committing to a path."
            )

        return {"response": response}

    def persist_new_customer_facts(state: SupportState) -> dict[str, Any]:
        memories = extract_customer_memories(
            state["customer_id"],
            state["incoming_message"],
        )
        stored = [memory.remember(item) for item in memories]
        return {"stored_memories": stored}

    graph.add_node("recall_customer_context", recall_customer_context)
    graph.add_node("draft_support_response", draft_support_response)
    graph.add_node("persist_new_customer_facts", persist_new_customer_facts)

    graph.set_entry_point("recall_customer_context")
    graph.add_edge("recall_customer_context", "draft_support_response")
    graph.add_edge("draft_support_response", "persist_new_customer_facts")
    graph.add_edge("persist_new_customer_facts", END)

    return graph.compile()


def extract_customer_memories(customer_id: str, message: str) -> list[MemoryItem]:
    """Extract durable facts from the current message."""

    lower = message.lower()
    memories: list[MemoryItem] = []

    if "sms" in lower:
        memories.append(
            MemoryItem(
                type="preference",
                title="Customer update channel",
                content=f"{customer_id} prefers SMS updates for support tickets.",
                confidence=0.95,
                tags=[customer_id, "support", "channel", "sms"],
            )
        )

    if "enterprise" in lower or "sla" in lower:
        memories.append(
            MemoryItem(
                type="fact",
                title="Customer support SLA",
                content=(
                    f"{customer_id} is on an Enterprise support plan with a "
                    "two-hour SLA for checkout incidents."
                ),
                confidence=0.92,
                tags=[customer_id, "support", "sla", "enterprise"],
            )
        )

    ticket_match = re.search(r"\bT-\d+\b", message)
    if ticket_match:
        memories.append(
            MemoryItem(
                type="commitment",
                title="Active support ticket",
                content=(
                    f"{customer_id} is tracking active support ticket "
                    f"{ticket_match.group(0)}."
                ),
                confidence=0.9,
                tags=[customer_id, "support", "ticket", ticket_match.group(0)],
            )
        )

    return memories


def run_support_session(
    graph,
    *,
    session_name: str,
    customer_id: str,
    message: str,
) -> SupportState:
    """Run one LangGraph support session."""

    initial_state: SupportState = {
        "customer_id": customer_id,
        "session_name": session_name,
        "incoming_message": message,
        "current_thread": [message],
    }
    return graph.invoke(initial_state)


def create_memory_backend(
    backend: Literal["auto", "memanto", "local"],
    *,
    agent_id: str,
    reset_local: bool,
) -> LongTermMemory:
    """Choose the real Memanto backend when configured, otherwise local JSON."""

    api_key = os.environ.get("MOORCHEH_API_KEY", "").strip()

    if backend == "memanto" or (backend == "auto" and api_key):
        if not api_key:
            raise RuntimeError("MOORCHEH_API_KEY is required for --backend memanto")
        return MemantoLongTermMemory(api_key=api_key, agent_id=agent_id)

    local = JsonLongTermMemory()
    if reset_local:
        local.reset()
    return local


def print_result(state: SupportState, backend_name: str) -> None:
    """Pretty-print a demo session result."""

    print(f"\nSession: {state['session_name']} ({backend_name})")
    print("-" * 72)
    print(f"Customer says: {state['incoming_message']}")

    recalled = state.get("recalled_memories", [])
    print(f"\nRecalled long-term memories: {len(recalled)}")
    for item in recalled:
        print(f"  - [{item.get('type', 'memory')}] {item.get('content', '')}")

    print(f"\nAgent response:\n  {state['response']}")

    stored = state.get("stored_memories", [])
    print(f"\nStored new memories: {len(stored)}")
    for item in stored:
        print(f"  - [{item.get('type', 'memory')}] {item.get('content', '')}")


def _normalize_memanto_memory(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory.get("metadata", {}) if isinstance(memory.get("metadata"), dict) else {}
    return {
        "memory_id": memory.get("id") or memory.get("memory_id"),
        "type": memory.get("type") or metadata.get("memory_type"),
        "title": memory.get("title") or metadata.get("title", "Memory"),
        "content": memory.get("content") or memory.get("text", ""),
        "confidence": memory.get("confidence") or metadata.get("confidence"),
        "tags": memory.get("tags") or metadata.get("tags", []),
    }


def _terms(text: str) -> list[str]:
    return re.findall(r"[a-z0-9-]+", text.lower())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the LangGraph + Memanto support memory demo."
    )
    parser.add_argument(
        "--session",
        choices=["yesterday", "today", "full"],
        default="full",
        help="Run one session or both sessions in order.",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "memanto", "local"],
        default="auto",
        help="Use Memanto when MOORCHEH_API_KEY is set, otherwise local JSON.",
    )
    parser.add_argument(
        "--agent-id",
        default=AGENT_ID,
        help="Memanto agent id / memory namespace.",
    )
    parser.add_argument(
        "--reset-local",
        action="store_true",
        help="Clear the local JSON memory file before running.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    memory = create_memory_backend(
        args.backend,
        agent_id=args.agent_id,
        reset_local=args.reset_local,
    )
    graph = build_support_graph(memory)

    try:
        if args.session in {"yesterday", "full"}:
            yesterday = run_support_session(
                graph,
                session_name="yesterday",
                customer_id=CUSTOMER_ID,
                message=YESTERDAY_MESSAGE,
            )
            print_result(yesterday, memory.backend_name)

        if args.session in {"today", "full"}:
            today = run_support_session(
                graph,
                session_name="today",
                customer_id=CUSTOMER_ID,
                message=TODAY_MESSAGE,
            )
            print_result(today, memory.backend_name)

    finally:
        memory.close()


if __name__ == "__main__":
    main()
