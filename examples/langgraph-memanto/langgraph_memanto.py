"""LangGraph support handoff example backed by Memanto long-term memory."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

try:
    from langgraph.checkpoint.memory import MemorySaver
except ImportError:  # pragma: no cover - compatibility with newer LangGraph names
    from langgraph.checkpoint.memory import InMemorySaver as MemorySaver


VALID_MEMORY_TYPES = {
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


class SupportState(TypedDict, total=False):
    """State that LangGraph keeps for one support turn only."""

    session_id: str
    user_message: str
    memory_query: str
    recalled_memories: list[dict[str, Any]]
    durable_answer: str
    memories_to_store: list[dict[str, Any]]
    stored_memory_ids: list[str]
    answer: str


@dataclass(slots=True)
class MemoryRecord:
    """Normalized memory record used by the graph and both storage adapters."""

    id: str
    type: str
    title: str
    content: str
    confidence: float = 0.86
    tags: list[str] = field(default_factory=list)
    source: str = "langgraph-support-handoff"
    score: float | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> MemoryRecord:
        """Normalize SDK or local memory rows into one shape."""

        content = (
            data.get("content")
            or data.get("text")
            or data.get("document")
            or data.get("memory")
            or ""
        )
        title = data.get("title") or content[:80] or "Memory"
        memory_type = data.get("type") or data.get("memory_type") or "fact"
        confidence = float(data.get("confidence") or data.get("score") or 0.86)
        tags = data.get("tags") or []
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",") if tag.strip()]

        return cls(
            id=str(data.get("id") or data.get("memory_id") or uuid.uuid4().hex[:12]),
            type=str(memory_type),
            title=str(title),
            content=str(content),
            confidence=confidence,
            tags=list(tags),
            source=str(data.get("source") or "memanto"),
            score=data.get("score") or data.get("similarity"),
        )

    def as_public_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict for LangGraph state and test assertions."""

        return asdict(self)


class LongTermMemory(Protocol):
    """Storage contract used by the LangGraph nodes."""

    def remember(self, memory: MemoryRecord) -> str:
        """Persist one memory and return its durable ID."""

    def recall(
        self,
        query: str,
        *,
        memory_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        """Return memories ranked by relevance."""

    def answer(self, question: str, *, limit: int = 5) -> str:
        """Answer a question from durable memory."""


class JsonMemoryStore:
    """Offline store with the same behavior shape as Memanto for demos/tests."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def remember(self, memory: MemoryRecord) -> str:
        memory_id = memory.id if memory.id != "pending" else uuid.uuid4().hex[:12]
        stored = MemoryRecord(
            id=memory_id,
            type=memory.type,
            title=memory.title,
            content=memory.content,
            confidence=memory.confidence,
            tags=memory.tags,
            source=memory.source,
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(stored.as_public_dict(), sort_keys=True) + "\n")
        return memory_id

    def recall(
        self,
        query: str,
        *,
        memory_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        query_terms = _terms(query)
        ranked: list[tuple[float, MemoryRecord]] = []
        for memory in self._load():
            if memory_types and memory.type not in memory_types:
                continue
            searchable = " ".join([memory.title, memory.content, *memory.tags])
            overlap = query_terms & _terms(searchable)
            if not overlap:
                continue
            score = len(overlap) / max(len(query_terms), 1)
            ranked.append((score, MemoryRecord(**{**asdict(memory), "score": score})))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in ranked[:limit]]

    def answer(self, question: str, *, limit: int = 5) -> str:
        memories = self.recall(question, limit=limit)
        if not memories:
            return "No durable memory matched this question."
        facts = "; ".join(memory.content for memory in memories)
        return f"Durable memory says: {facts}"

    def reset(self) -> None:
        self.path.unlink(missing_ok=True)

    def _load(self) -> list[MemoryRecord]:
        if not self.path.exists():
            return []

        rows: list[MemoryRecord] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(MemoryRecord.from_mapping(json.loads(line)))
        return rows


class MemantoMemoryStore:
    """Memanto SDK-backed implementation of the long-term memory contract."""

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        description: str = "LangGraph support handoff example",
    ) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)
        self._ensure_agent(description)

    @classmethod
    def from_env(cls) -> MemantoMemoryStore:
        api_key = os.environ.get("MOORCHEH_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("Set MOORCHEH_API_KEY or run the demo with --backend local.")

        agent_id = os.environ.get(
            "MEMANTO_LANGGRAPH_AGENT_ID",
            "langgraph-support-handoff",
        )
        return cls(api_key=api_key, agent_id=agent_id)

    def remember(self, memory: MemoryRecord) -> str:
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory.type,
            title=_limit(memory.title, 100),
            content=_limit(memory.content, 500),
            confidence=memory.confidence,
            tags=memory.tags,
            source=memory.source,
            provenance="explicit_statement",
        )
        return str(result["memory_id"])

    def recall(
        self,
        query: str,
        *,
        memory_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=memory_types,
        )
        return [
            MemoryRecord.from_mapping(row)
            for row in result.get("memories", [])
        ]

    def answer(self, question: str, *, limit: int = 5) -> str:
        result = self.client.answer(
            agent_id=self.agent_id,
            question=question,
            limit=limit,
        )
        return str(result.get("answer") or "No answer generated.")

    def _ensure_agent(self, description: str) -> None:
        try:
            self.client.get_agent(self.agent_id)
        except Exception:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="support",
                description=description,
            )
        self.client.activate_agent(self.agent_id, duration_hours=6)


def build_graph(memory: LongTermMemory):
    """Build the LangGraph workflow with Memanto as an external memory node."""

    graph = StateGraph(SupportState)

    def recall_memory(state: SupportState) -> SupportState:
        query = _build_memory_query(state["user_message"])
        memories = memory.recall(query, limit=5)
        return {
            "memory_query": query,
            "recalled_memories": [item.as_public_dict() for item in memories],
        }

    def ask_memory(state: SupportState) -> SupportState:
        if not state.get("recalled_memories"):
            return {
                "durable_answer": (
                    "No durable memory answer was requested because recall "
                    "returned no matches."
                )
            }
        return {
            "durable_answer": memory.answer(state["memory_query"], limit=5),
        }

    def extract_memory(state: SupportState) -> SupportState:
        memories = extract_memories(state["user_message"])
        return {"memories_to_store": [item.as_public_dict() for item in memories]}

    def store_memory(state: SupportState) -> SupportState:
        stored_ids: list[str] = []
        for payload in state.get("memories_to_store", []):
            stored_ids.append(memory.remember(MemoryRecord.from_mapping(payload)))
        return {"stored_memory_ids": stored_ids}

    def draft_answer(state: SupportState) -> SupportState:
        recalled = [
            MemoryRecord.from_mapping(row)
            for row in state.get("recalled_memories", [])
        ]
        stored_count = len(state.get("stored_memory_ids", []))
        answer = render_support_answer(
            message=state["user_message"],
            recalled=recalled,
            durable_answer=state.get("durable_answer", ""),
            stored_count=stored_count,
        )
        return {"answer": answer}

    graph.add_node("recall_memory", recall_memory)
    graph.add_node("ask_memory", ask_memory)
    graph.add_node("extract_memory", extract_memory)
    graph.add_node("store_memory", store_memory)
    graph.add_node("draft_answer", draft_answer)

    graph.add_edge(START, "recall_memory")
    graph.add_edge("recall_memory", "ask_memory")
    graph.add_edge("ask_memory", "extract_memory")
    graph.add_edge("extract_memory", "store_memory")
    graph.add_edge("store_memory", "draft_answer")
    graph.add_edge("draft_answer", END)

    return graph.compile(checkpointer=MemorySaver())


def run_turn(
    *,
    graph: Any,
    session_id: str,
    user_message: str,
) -> SupportState:
    """Run one independent LangGraph support turn."""

    initial_state: SupportState = {
        "session_id": session_id,
        "user_message": user_message,
        "recalled_memories": [],
        "durable_answer": "",
        "memories_to_store": [],
        "stored_memory_ids": [],
    }
    config = {"configurable": {"thread_id": session_id}}
    return graph.invoke(initial_state, config=config)


def extract_memories(message: str) -> list[MemoryRecord]:
    """Extract concise typed memories from the current support message."""

    memories: list[MemoryRecord] = []
    normalized = " ".join(message.split())
    lower = normalized.lower()

    identity = re.search(
        r"\b(?:i am|i'm)\s+([A-Z][a-z]+)(?:\s+from\s+([A-Z][A-Za-z\s]+?))?[,.]",
        normalized,
        flags=re.IGNORECASE,
    )
    if identity:
        name = identity.group(1)
        company = (identity.group(2) or "").strip()
        content = f"The customer contact is {name}"
        if company:
            content += f" from {company}"
        memories.append(_memory("relationship", "Customer contact", content))

    if "prefer" in lower or "please keep" in lower:
        preference = _sentence_with_any(normalized, ["prefer", "please keep"])
        memories.append(
            _memory(
                "preference",
                "Customer communication preference",
                preference,
                tags=["communication", "support-style"],
            )
        )

    if "always" in lower or "escalate" in lower:
        instruction = _sentence_with_any(normalized, ["always", "escalate"])
        memories.append(
            _memory(
                "instruction",
                "Standing support instruction",
                instruction,
                tags=["handoff", "support"],
            )
        )

    if "deadline" in lower or "launch" in lower or "review" in lower:
        commitment = _sentence_with_any(normalized, ["deadline", "launch", "review"])
        memories.append(
            _memory(
                "commitment",
                "Time-sensitive support context",
                commitment,
                confidence=0.9,
                tags=["deadline", "launch"],
            )
        )

    return _dedupe_memories(memories)


def render_support_answer(
    *,
    message: str,
    recalled: list[MemoryRecord],
    durable_answer: str,
    stored_count: int,
) -> str:
    """Create a deterministic answer so the demo works without an LLM key."""

    if recalled:
        bullets = [
            f"- {memory.type}: {memory.content}"
            for memory in recalled[:4]
        ]
        context = "\n".join(bullets)
        lead = "Memanto recalled durable context from an earlier session:"
    else:
        context = "- No durable memory matched this turn yet."
        lead = "This appears to be a new support context:"
        durable_answer = ""

    write_note = (
        f"Stored {stored_count} new typed memories for future LangGraph sessions."
        if stored_count
        else "No new durable memory was stored from this turn."
    )

    return (
        f"{lead}\n{context}\n\n"
        f"{_format_durable_answer(durable_answer)}"
        f"Current ticket: {message}\n"
        f"{write_note}"
    )


def _format_durable_answer(answer: str) -> str:
    if not answer:
        return ""
    return f"Memanto answer: {answer}\n\n"


def _build_memory_query(message: str) -> str:
    return (
        "support handoff context, customer preferences, escalation rules, "
        f"launch deadlines, and prior facts for: {message}"
    )


def _memory(
    memory_type: str,
    title: str,
    content: str,
    *,
    confidence: float = 0.86,
    tags: list[str] | None = None,
) -> MemoryRecord:
    if memory_type not in VALID_MEMORY_TYPES:
        raise ValueError(f"Unsupported memory type: {memory_type}")
    return MemoryRecord(
        id="pending",
        type=memory_type,
        title=_limit(title, 100),
        content=_limit(content, 500),
        confidence=confidence,
        tags=tags or [],
    )


def _sentence_with_any(text: str, needles: list[str]) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        if any(needle in sentence.lower() for needle in needles):
            return sentence.strip()
    return text.strip()


def _dedupe_memories(memories: list[MemoryRecord]) -> list[MemoryRecord]:
    seen: set[tuple[str, str]] = set()
    deduped: list[MemoryRecord] = []
    for memory in memories:
        key = (memory.type, memory.content.lower())
        if key not in seen:
            seen.add(key)
            deduped.append(memory)
    return deduped


def _terms(text: str) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "for",
        "from",
        "is",
        "of",
        "or",
        "the",
        "this",
        "to",
        "what",
        "with",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in stopwords
    }


def _limit(value: str, max_length: int) -> str:
    value = " ".join(value.split())
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip() + "..."
