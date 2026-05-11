"""
LangGraph + Memanto cross-session memory example.

This module keeps LangGraph state intentionally short-lived. User memories are
written to and read from a Memanto-compatible store so a new graph invocation
can recall facts that are not present in the current thread state.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TypedDict
from uuid import uuid4

try:
    from langgraph.graph import END, StateGraph
except ImportError as exc:  # pragma: no cover - exercised by setup guidance.
    END = None
    StateGraph = None
    _LANGGRAPH_IMPORT_ERROR = exc
else:
    _LANGGRAPH_IMPORT_ERROR = None


class SupportState(TypedDict, total=False):
    """LangGraph state for one support turn."""

    user_id: str
    question: str
    session_id: str
    recalled_memories: list[dict[str, object]]
    response: str
    memory_written: dict[str, object] | None


@dataclass
class MemoryRecord:
    """Small, serializable memory shape shared by local and SDK stores."""

    memory_id: str
    user_id: str
    memory_type: str
    title: str
    content: str
    confidence: float = 0.9
    tags: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    def to_result(self) -> dict[str, object]:
        return {
            "memory_id": self.memory_id,
            "type": self.memory_type,
            "title": self.title,
            "content": self.content,
            "confidence": self.confidence,
            "tags": self.tags,
            "created_at": self.created_at,
        }


class MemoryStore(Protocol):
    """Minimum Memanto operations used by the LangGraph workflow."""

    def remember(
        self,
        *,
        user_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> dict[str, object]:
        """Persist a memory outside LangGraph state."""

    def recall(
        self,
        *,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, object]]:
        """Retrieve memories for a fresh graph invocation."""


class JsonlMemantoStore:
    """
    Local Memanto-style store for no-key demos and tests.

    Real usage should use ``SdkMemantoStore`` below. This adapter preserves the
    same remember/recall contract while avoiding API keys in the example repo.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def remember(
        self,
        *,
        user_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> dict[str, object]:
        record = MemoryRecord(
            memory_id=f"local-{uuid4()}",
            user_id=user_id,
            memory_type=memory_type,
            title=title[:100],
            content=content[:500],
            confidence=confidence,
            tags=tags or [],
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        return record.to_result()

    def recall(
        self,
        *,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, object]]:
        query_terms = _tokenize(query)
        records = [
            record
            for record in self._load()
            if record.user_id == user_id
            and (not memory_types or record.memory_type in memory_types)
        ]

        scored = []
        for record in records:
            haystack = " ".join(
                [record.title, record.content, " ".join(record.tags)]
            )
            score = len(query_terms.intersection(_tokenize(haystack)))
            if score:
                scored.append((score, record.created_at, record))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [record.to_result() for _, _, record in scored[:limit]]

    def _load(self) -> list[MemoryRecord]:
        if not self.path.exists():
            return []

        records: list[MemoryRecord] = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                payload = json.loads(line)
                records.append(MemoryRecord(**payload))
        return records


class SdkMemantoStore:
    """Real Memanto store backed by the repository's SdkClient."""

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str = "langgraph-support-demo",
        duration_hours: int = 6,
    ) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="tool",
                description="LangGraph + Memanto support demo",
            )
        except Exception:
            pass
        self.client.activate_agent(agent_id, duration_hours=duration_hours)

    def remember(
        self,
        *,
        user_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> dict[str, object]:
        merged_tags = ["langgraph", user_id, *(tags or [])]
        return self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=f"{user_id}: {content}",
            confidence=confidence,
            tags=merged_tags,
            source="langgraph-example",
            provenance="explicit_statement",
        )

    def recall(
        self,
        *,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, object]]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=f"{user_id} {query}",
            limit=limit,
            type=memory_types,
            tags=["langgraph", user_id],
        )
        return result.get("memories", [])


def build_support_graph(store: MemoryStore):
    """Compile the LangGraph workflow."""
    if StateGraph is None or END is None:
        raise RuntimeError(
            "langgraph is not installed. Run: pip install -r requirements.txt"
        ) from _LANGGRAPH_IMPORT_ERROR

    workflow = StateGraph(SupportState)
    workflow.add_node("recall_memanto_memory", _recall_node(store))
    workflow.add_node("draft_answer", _answer_node)
    workflow.add_node("write_memanto_memory", _remember_node(store))

    workflow.set_entry_point("recall_memanto_memory")
    workflow.add_edge("recall_memanto_memory", "draft_answer")
    workflow.add_edge("draft_answer", "write_memanto_memory")
    workflow.add_edge("write_memanto_memory", END)
    return workflow.compile()


def make_store_from_env() -> MemoryStore:
    """Use real Memanto when an API key exists, otherwise local demo storage."""
    api_key = os.getenv("MOORCHEH_API_KEY")
    if api_key:
        return SdkMemantoStore(
            api_key=api_key,
            agent_id=os.getenv("MEMANTO_AGENT_ID", "langgraph-support-demo"),
        )

    memory_file = os.getenv("MEMANTO_MEMORY_FILE", ".memanto-demo-memory.jsonl")
    return JsonlMemantoStore(memory_file)


def run_support_turn(
    *,
    store: MemoryStore,
    user_id: str,
    question: str,
    session_id: str,
) -> SupportState:
    """Run a single fresh LangGraph support turn."""
    graph = build_support_graph(store)
    return graph.invoke(
        {
            "user_id": user_id,
            "question": question,
            "session_id": session_id,
        }
    )


def _recall_node(store: MemoryStore):
    def recall(state: SupportState) -> SupportState:
        query = (
            "support preferences product settings export format dashboard "
            f"{state['question']}"
        )
        memories = store.recall(
            user_id=state["user_id"],
            query=query,
            memory_types=["preference", "fact", "decision", "context"],
            limit=5,
        )
        return {"recalled_memories": memories}

    return recall


def _answer_node(state: SupportState) -> SupportState:
    memories = state.get("recalled_memories", [])
    memory_lines = [
        f"- {memory.get('content', '')}" for memory in memories if memory.get("content")
    ]
    memory_context = "\n".join(memory_lines) if memory_lines else "- No prior memory."

    lower_context = memory_context.lower()
    advice = []
    if "dark mode" in lower_context:
        advice.append("use dark mode")
    if "csv" in lower_context:
        advice.append("export reports as CSV")

    if advice:
        response = (
            f"For {state['user_id']}, " + " and ".join(advice) + ". "
            "Those settings came from Memanto recall, not the current graph state."
        )
    else:
        response = (
            "I do not have prior preferences for this user yet. "
            "I will answer from the current request and store any durable preference."
        )

    return {"response": response}


def _remember_node(store: MemoryStore):
    def remember(state: SupportState) -> SupportState:
        extracted = _extract_preference(state["question"])
        if not extracted:
            return {"memory_written": None}

        memory = store.remember(
            user_id=state["user_id"],
            memory_type="preference",
            title=extracted["title"],
            content=extracted["content"],
            confidence=0.95,
            tags=["support", "cross-session"],
        )
        return {"memory_written": memory}

    return remember


def _extract_preference(text: str) -> dict[str, str] | None:
    lower = text.lower()
    if "remember" not in lower and "prefers" not in lower and "wants" not in lower:
        return None

    if "dark mode" not in lower and "csv" not in lower:
        return None

    preferences = []
    if "dark mode" in lower:
        preferences.append("dashboard walkthroughs should use dark mode")
    if "csv" in lower:
        preferences.append("reports should be exported as CSV")

    content = "; ".join(preferences)
    return {
        "title": "Dashboard delivery preferences",
        "content": content,
    }


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))
