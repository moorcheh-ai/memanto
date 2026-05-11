#!/usr/bin/env python3
"""
LangGraph + Memanto research assistant example.

LangGraph keeps only the current session state. Memanto stores durable
memories that survive across sessions. Run the "yesterday" session first,
then "today" to prove that the agent recalls information that is not present
in the current LangGraph state.
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

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is listed for real runs.
    load_dotenv = None  # type: ignore[assignment]

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover - tests can cover pure nodes.
    END = "__end__"
    StateGraph = None  # type: ignore[assignment]

try:
    from memanto.cli.client.sdk_client import SdkClient
except ImportError:  # pragma: no cover - editable install covers this path.
    SdkClient = None  # type: ignore[assignment]


AGENT_ID = "langgraph-research-memory"
RESEARCHER_ID = "dana-research-lead"
DEFAULT_MEMORY_PATH = Path(__file__).with_name(".local_research_memories.json")

YESTERDAY_NOTES = (
    "Dana said future retrieval-memory reports must use a compact benchmark "
    "table, avoid vendor blog posts as primary sources, and keep tracking "
    "AtlasBench 2026 as the north-star evaluation paper."
)

TODAY_QUESTION = (
    "Prepare the next answer about retrieval-memory systems for Dana. "
    "What constraints should I follow?"
)


@dataclass
class MemoryItem:
    """Normalized memory record used by Memanto and the local test backend."""

    memory_type: str
    title: str
    content: str
    confidence: float = 0.9
    tags: list[str] = field(default_factory=list)
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ResearchState(TypedDict, total=False):
    """LangGraph state. This intentionally contains current-session data only."""

    researcher_id: str
    session_name: str
    question: str
    current_notes: list[str]
    recall_queries: list[str]
    recalled_memories: list[dict[str, Any]]
    plan: list[str]
    answer: str
    memories_to_store: list[MemoryItem]
    stored_memories: list[dict[str, Any]]
    used_long_term_memory: bool


class LongTermMemory(Protocol):
    """Boundary between LangGraph nodes and durable memory storage."""

    backend_name: str

    def remember(self, memory: MemoryItem) -> dict[str, Any]:
        """Persist one memory."""

    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return relevant durable memories."""

    def close(self) -> None:
        """Release resources."""


class LocalJsonMemory:
    """Small durable backend for demos and tests without a Moorcheh API key."""

    backend_name = "local-json"

    def __init__(self, path: Path = DEFAULT_MEMORY_PATH) -> None:
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
            if memory_types and record.get("memory_type") not in memory_types:
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

        ranked.sort(
            key=lambda item: (item[0], item[1].get("created_at", "")),
            reverse=True,
        )
        return [record for _, record in ranked[:limit]]

    def close(self) -> None:
        return None

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))


class MemantoMemory:
    """Memanto-backed durable memory adapter used by the LangGraph nodes."""

    backend_name = "memanto"

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str = AGENT_ID,
        duration_hours: int = 6,
    ) -> None:
        if SdkClient is None:
            raise RuntimeError("Install this repo first: pip install -e ../..")

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)

        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="project",
                description="LangGraph research assistant with Memanto memory.",
            )
        except Exception:
            # Reuse an existing demo agent. The example intentionally keeps the
            # same namespace so later sessions can recall earlier memories.
            pass

        self.client.activate_agent(agent_id, duration_hours=duration_hours)

    def remember(self, memory: MemoryItem) -> dict[str, Any]:
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory.memory_type,
            title=memory.title[:100],
            content=memory.content[:500],
            confidence=memory.confidence,
            tags=memory.tags,
            source="langgraph-research-demo",
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
        return [_normalize_memanto_memory(item) for item in result.get("memories", [])]

    def close(self) -> None:
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            pass


def build_research_graph(memory: LongTermMemory):
    """Build the actual LangGraph workflow."""

    if StateGraph is None:
        raise RuntimeError("Install LangGraph first: pip install -r requirements.txt")

    graph = StateGraph(ResearchState)
    graph.add_node("plan", plan_research)
    graph.add_node("recall", make_recall_node(memory))
    graph.add_node("answer", draft_answer)
    graph.add_node("extract_memories", extract_memories_to_store)
    graph.add_node("persist", make_persist_node(memory))

    graph.set_entry_point("plan")
    graph.add_edge("plan", "recall")
    graph.add_edge("recall", "answer")
    graph.add_edge("answer", "extract_memories")
    graph.add_conditional_edges(
        "extract_memories",
        should_persist_memories,
        {"persist": "persist", "done": END},
    )
    graph.add_edge("persist", END)
    return graph.compile()


def plan_research(state: ResearchState) -> dict[str, Any]:
    """Create a small plan and memory search queries from current state."""

    researcher_id = state["researcher_id"]
    question = state["question"]
    recall_queries = [
        f"{researcher_id} preferred report format retrieval memory systems",
        f"{researcher_id} source policy vendor blogs primary sources",
        f"{researcher_id} benchmark paper AtlasBench 2026",
        question,
    ]
    plan = [
        "Check durable preferences and source policy before answering.",
        "Answer using only current state plus recalled Memanto memories.",
        "Store any new stable preference, source policy, or tracked artifact.",
    ]
    return {"plan": plan, "recall_queries": recall_queries}


def make_recall_node(memory: LongTermMemory):
    """Create a LangGraph node that recalls from Memanto."""

    def recall_long_term_memory(state: ResearchState) -> dict[str, Any]:
        seen_ids: set[str] = set()
        recalled: list[dict[str, Any]] = []
        for query in state.get("recall_queries", []):
            for item in memory.recall(
                query,
                limit=4,
                memory_types=["preference", "instruction", "artifact"],
            ):
                memory_id = str(item.get("memory_id") or item.get("id") or item)
                if memory_id not in seen_ids:
                    seen_ids.add(memory_id)
                    recalled.append(item)

        return {
            "recalled_memories": recalled,
            "used_long_term_memory": bool(recalled),
        }

    return recall_long_term_memory


def draft_answer(state: ResearchState) -> dict[str, Any]:
    """Draft an answer using only current state and recalled memories."""

    memory_text = " ".join(
        str(item.get("content", "")) for item in state.get("recalled_memories", [])
    ).lower()

    format_rule = "a concise narrative"
    if "benchmark table" in memory_text or "compact table" in memory_text:
        format_rule = "a compact benchmark table"

    source_rule = "cite credible sources"
    if "avoid vendor blog" in memory_text:
        source_rule = "avoid vendor blog posts as primary sources"

    tracked_artifact = ""
    if "atlasbench 2026" in memory_text:
        tracked_artifact = " Include AtlasBench 2026 in the evaluation notes."

    if state.get("recalled_memories"):
        answer = (
            f"Use {format_rule}; {source_rule}; and keep the response scoped "
            f"to retrieval-memory systems.{tracked_artifact}"
        )
    else:
        answer = (
            "No durable preferences were found. Ask Dana for preferred format, "
            "source policy, and any benchmark papers to track."
        )

    return {"answer": answer}


def extract_memories_to_store(state: ResearchState) -> dict[str, Any]:
    """Extract stable memories from current notes."""

    notes = " ".join(state.get("current_notes", []))
    lower = notes.lower()
    researcher_id = state["researcher_id"]
    memories: list[MemoryItem] = []

    if "benchmark table" in lower or "compact table" in lower:
        memories.append(
            MemoryItem(
                memory_type="preference",
                title="Research report format",
                content=(
                    f"{researcher_id} prefers compact benchmark tables for "
                    "retrieval-memory system comparisons."
                ),
                confidence=0.95,
                tags=[researcher_id, "research", "format", "benchmark-table"],
            )
        )

    if "avoid vendor blog" in lower:
        memories.append(
            MemoryItem(
                memory_type="instruction",
                title="Primary source policy",
                content=(
                    f"{researcher_id} wants retrieval-memory reports to avoid "
                    "vendor blog posts as primary sources."
                ),
                confidence=0.94,
                tags=[researcher_id, "research", "sources", "vendor-blogs"],
            )
        )

    if "atlasbench 2026" in lower:
        memories.append(
            MemoryItem(
                memory_type="artifact",
                title="Tracked benchmark paper",
                content=(
                    f"{researcher_id} is tracking AtlasBench 2026 as a "
                    "north-star evaluation paper for retrieval-memory systems."
                ),
                confidence=0.9,
                tags=[researcher_id, "research", "paper", "atlasbench-2026"],
            )
        )

    return {"memories_to_store": memories}


def should_persist_memories(state: ResearchState) -> Literal["persist", "done"]:
    """Only write when the current session produced durable facts."""

    return "persist" if state.get("memories_to_store") else "done"


def make_persist_node(memory: LongTermMemory):
    """Create a LangGraph node that stores extracted memories."""

    def persist_memories(state: ResearchState) -> dict[str, Any]:
        stored = [memory.remember(item) for item in state.get("memories_to_store", [])]
        return {"stored_memories": stored}

    return persist_memories


def run_research_session(
    memory: LongTermMemory,
    *,
    session_name: str,
    researcher_id: str,
    question: str,
    current_notes: list[str],
) -> ResearchState:
    """Run one LangGraph session."""

    graph = build_research_graph(memory)
    initial_state: ResearchState = {
        "researcher_id": researcher_id,
        "session_name": session_name,
        "question": question,
        "current_notes": current_notes,
    }
    return graph.invoke(initial_state)


def create_memory_backend(
    backend: Literal["auto", "memanto", "local"],
    *,
    agent_id: str,
    local_path: Path,
    reset_local: bool,
) -> LongTermMemory:
    """Use Memanto when configured, otherwise a local durable JSON file."""

    api_key = os.environ.get("MOORCHEH_API_KEY", "").strip()
    if backend == "memanto" or (backend == "auto" and api_key):
        if not api_key:
            raise RuntimeError("MOORCHEH_API_KEY is required for --backend memanto")
        return MemantoMemory(api_key=api_key, agent_id=agent_id)

    local = LocalJsonMemory(local_path)
    if reset_local:
        local.reset()
    return local


def print_session(state: ResearchState, backend_name: str) -> None:
    """Print a concise demo transcript."""

    print(f"\nSession: {state['session_name']} ({backend_name})")
    print("-" * 72)
    print(f"Question: {state['question']}")
    print(f"Current notes: {' | '.join(state.get('current_notes', []))}")
    print("\nRecalled long-term memories:")
    for item in state.get("recalled_memories", []):
        print(f"  - [{item.get('memory_type')}] {item.get('content')}")
    if not state.get("recalled_memories"):
        print("  - none")
    print(f"\nAnswer: {state['answer']}")
    print(f"\nStored memories: {len(state.get('stored_memories', []))}")


def _normalize_memanto_memory(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "memory_id": memory.get("id") or memory.get("memory_id"),
        "memory_type": memory.get("type") or metadata.get("memory_type"),
        "title": memory.get("title") or metadata.get("title", "Memory"),
        "content": memory.get("content") or memory.get("text", ""),
        "confidence": memory.get("confidence") or metadata.get("confidence"),
        "tags": memory.get("tags") or metadata.get("tags", []),
    }


def _terms(text: str) -> list[str]:
    return re.findall(r"[a-z0-9-]+", text.lower())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the LangGraph + Memanto research memory demo."
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
        help="Use Memanto when MOORCHEH_API_KEY exists, otherwise local JSON.",
    )
    parser.add_argument("--agent-id", default=AGENT_ID)
    parser.add_argument(
        "--memory-file",
        type=Path,
        default=DEFAULT_MEMORY_PATH,
        help="Local JSON memory path used by --backend local.",
    )
    parser.add_argument(
        "--reset-local",
        action="store_true",
        help="Clear the local JSON memory file before running.",
    )
    return parser.parse_args()


def main() -> None:
    if load_dotenv is not None:
        load_dotenv()

    args = parse_args()
    memory = create_memory_backend(
        args.backend,
        agent_id=args.agent_id,
        local_path=args.memory_file,
        reset_local=args.reset_local,
    )

    try:
        if args.session in {"yesterday", "full"}:
            yesterday = run_research_session(
                memory,
                session_name="yesterday",
                researcher_id=RESEARCHER_ID,
                question=(
                    "Capture durable preferences from today's research kickoff."
                ),
                current_notes=[YESTERDAY_NOTES],
            )
            print_session(yesterday, memory.backend_name)

        if args.session in {"today", "full"}:
            today = run_research_session(
                memory,
                session_name="today",
                researcher_id=RESEARCHER_ID,
                question=TODAY_QUESTION,
                current_notes=[
                    "No preferred format or source policy was restated today."
                ],
            )
            print_session(today, memory.backend_name)
    finally:
        memory.close()


if __name__ == "__main__":
    main()
