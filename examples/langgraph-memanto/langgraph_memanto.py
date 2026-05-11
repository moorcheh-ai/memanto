from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypedDict

from langgraph.graph import END, StateGraph

DEFAULT_AGENT_ID = "langgraph-memanto-demo"
DEFAULT_LOCAL_STORE = Path(__file__).with_name(".memanto_local_store.json")


@dataclass(frozen=True)
class Memory:
    title: str
    content: str
    memory_type: str = "fact"
    confidence: float = 0.9
    tags: tuple[str, ...] = ()
    session_id: str = ""
    created_at: str = ""


class MemoryBackend(Protocol):
    def remember(self, memory: Memory) -> dict[str, Any]:
        ...

    def recall(self, query: str, limit: int = 5) -> list[Memory]:
        ...


class LocalJsonMemoryBackend:
    """Tiny durable store used for review and CI without external services."""

    def __init__(self, path: Path = DEFAULT_LOCAL_STORE) -> None:
        self.path = path

    def reset(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def remember(self, memory: Memory) -> dict[str, Any]:
        records = self._load()
        memory_id = f"local-{len(records) + 1}"
        payload = asdict(
            Memory(
                title=memory.title,
                content=memory.content,
                memory_type=memory.memory_type,
                confidence=memory.confidence,
                tags=memory.tags,
                session_id=memory.session_id,
                created_at=memory.created_at or _utc_now(),
            )
        )
        payload["memory_id"] = memory_id
        records.append(payload)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)
        return {"memory_id": memory_id, "status": "stored"}

    def recall(self, query: str, limit: int = 5) -> list[Memory]:
        query_terms = _terms(query)
        scored: list[tuple[int, Memory]] = []
        for item in self._load():
            memory = _memory_from_dict(item)
            haystack = " ".join(
                [memory.title, memory.content, " ".join(memory.tags)]
            ).lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score:
                scored.append((score, memory))

        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [memory for _, memory in scored[:limit]]

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []


class MemantoSdkMemoryBackend:
    """Live Memanto adapter using the repository's SDK client."""

    def __init__(
        self,
        api_key: str | None = None,
        agent_id: str = DEFAULT_AGENT_ID,
    ) -> None:
        self.agent_id = agent_id
        resolved_api_key = api_key or os.environ.get("MOORCHEH_API_KEY", "")
        if not resolved_api_key:
            raise ValueError("MOORCHEH_API_KEY is required for backend='memanto'")

        from memanto.app.utils.errors import AgentAlreadyExistsError
        from memanto.cli.client.sdk_client import SdkClient

        self.client = SdkClient(resolved_api_key)
        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern="support",
                description="LangGraph durable memory demo",
            )
        except AgentAlreadyExistsError:
            pass
        self.client.activate_agent(agent_id)

    def remember(self, memory: Memory) -> dict[str, Any]:
        return self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory.memory_type,
            title=memory.title,
            content=memory.content,
            confidence=memory.confidence,
            tags=list(memory.tags),
            source="langgraph",
            provenance="explicit_statement",
        )

    def recall(self, query: str, limit: int = 5) -> list[Memory]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
        )
        memories = []
        for item in result.get("memories", []):
            memories.append(
                Memory(
                    title=str(item.get("title", "Memanto memory")),
                    content=str(item.get("content", item)),
                    memory_type=str(item.get("type", "fact")),
                    confidence=float(item.get("confidence", 0.9)),
                    tags=tuple(item.get("tags", [])),
                    created_at=str(item.get("created_at", "")),
                )
            )
        return memories


class SupportState(TypedDict, total=False):
    session_id: str
    user_message: str
    recalled_memories: list[Memory]
    response: str
    written_memories: list[str]


def build_support_graph(backend: MemoryBackend):
    graph = StateGraph(SupportState)

    def load_context(state: SupportState) -> SupportState:
        query = state["user_message"]
        memories = backend.recall(query, limit=5)
        return {**state, "recalled_memories": memories}

    def draft_response(state: SupportState) -> SupportState:
        memories = state.get("recalled_memories", [])
        context = "\n".join(f"- {memory.content}" for memory in memories)
        if memories:
            response = (
                "I found prior context and will use it: "
                f"\n{context}\nCurrent request: {state['user_message']}"
            )
        else:
            response = (
                "I do not have prior context yet. "
                f"I will handle: {state['user_message']}"
            )
        return {**state, "response": response}

    def write_followup_memory(state: SupportState) -> SupportState:
        facts = extract_memories(state["user_message"])
        written: list[str] = []
        for fact in facts:
            memory = Memory(
                title=fact["title"],
                content=fact["content"],
                memory_type=fact["type"],
                confidence=0.92,
                tags=tuple(fact["tags"]),
                session_id=state["session_id"],
            )
            result = backend.remember(memory)
            written.append(str(result.get("memory_id", memory.title)))
        return {**state, "written_memories": written}

    graph.add_node("load_context", load_context)
    graph.add_node("draft_response", draft_response)
    graph.add_node("write_followup_memory", write_followup_memory)
    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "draft_response")
    graph.add_edge("draft_response", "write_followup_memory")
    graph.add_edge("write_followup_memory", END)
    return graph.compile()


def run_two_session_demo(
    backend: MemoryBackend,
) -> dict[Literal["session_1", "session_2"], SupportState]:
    app = build_support_graph(backend)

    session_1 = app.invoke(
        {
            "session_id": "day-one",
            "user_message": (
                "Customer Riley from Acme Robotics opened order AR-8841. "
                "Riley prefers concise answers with no marketing language. "
                "Refunds above $500 require manager approval."
            ),
        }
    )

    session_2 = app.invoke(
        {
            "session_id": "day-two",
            "user_message": (
                "Riley is back asking about the Acme Robotics refund. "
                "What prior details should I remember before replying?"
            ),
        }
    )

    return {"session_1": session_1, "session_2": session_2}


def extract_memories(message: str) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    order_match = re.search(r"order\s+([A-Z]+-\d+)", message)
    if order_match:
        facts.append(
            {
                "title": "Customer order reference",
                "content": (
                    "Customer Riley runs Acme Robotics order "
                    f"{order_match.group(1)}."
                ),
                "type": "fact",
                "tags": ["customer", "order", "acme"],
            }
        )

    if "concise answers" in message.lower():
        facts.append(
            {
                "title": "Riley communication preference",
                "content": (
                    "Riley prefers concise answers with no marketing language."
                ),
                "type": "preference",
                "tags": ["customer", "preference", "riley"],
            }
        )

    if "manager approval" in message.lower():
        facts.append(
            {
                "title": "Refund approval rule",
                "content": "Refunds above $500 require manager approval.",
                "type": "instruction",
                "tags": ["refund", "approval", "policy"],
            }
        )

    return facts


def backend_from_name(name: str, agent_id: str = DEFAULT_AGENT_ID) -> MemoryBackend:
    if name == "local":
        return LocalJsonMemoryBackend()
    if name == "memanto":
        return MemantoSdkMemoryBackend(agent_id=agent_id)
    raise ValueError(f"Unsupported backend: {name}")


def _memory_from_dict(item: dict[str, Any]) -> Memory:
    return Memory(
        title=str(item["title"]),
        content=str(item["content"]),
        memory_type=str(item.get("memory_type", "fact")),
        confidence=float(item.get("confidence", 0.9)),
        tags=tuple(item.get("tags", [])),
        session_id=str(item.get("session_id", "")),
        created_at=str(item.get("created_at", "")),
    )


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[a-zA-Z0-9$-]+", text.lower()) if len(term) > 2}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
