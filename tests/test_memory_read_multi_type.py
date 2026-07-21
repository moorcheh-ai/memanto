"""Regression coverage for union semantics in multi-type recall."""

import re

import pytest

from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.utils.errors import MemoryError


def _memory(memory_id: str, memory_type: str, score: float) -> dict:
    return {
        "id": memory_id,
        "text": f"[{memory_type.upper()}] {memory_id}\n\n{memory_id} content",
        "memory_type": memory_type,
        "agent_id": "agent-1",
        "actor_id": "agent-1",
        "source": "user",
        "confidence": 0.9,
        "status": "active",
        "created_at": "2026-07-20T00:00:00Z",
        "updated_at": "2026-07-20T00:00:00Z",
        "score": score,
    }


class _ExactFilterSearch:
    """Minimal Moorcheh filter semantics: repeated clauses are conjunctive."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.queries: list[str] = []

    def query(self, **kwargs):
        query = kwargs["query"]
        self.queries.append(query)
        requested_types = re.findall(r"#memory_type:([A-Za-z0-9_.-]+)", query)
        results = [
            row
            for row in self.rows
            if all(row["memory_type"] == value for value in requested_types)
        ]
        return {"results": results[: kwargs["top_k"]], "execution_time": 0.01}


class _Client:
    def __init__(self, rows: list[dict]):
        self.similarity_search = _ExactFilterSearch(rows)


def test_multi_type_recall_queries_each_type_and_returns_ranked_union():
    client = _Client(
        [
            _memory("fact-low", "fact", 0.70),
            _memory("preference-high", "preference", 0.95),
            _memory("instruction-excluded", "instruction", 0.99),
        ]
    )
    service = MemoryReadService(client)

    result = service.search_memories(
        query="project context",
        agent_id="agent-1",
        type=["fact", "preference"],
        limit=10,
    )

    assert [memory["id"] for memory in result["results"]] == [
        "preference-high",
        "fact-low",
    ]
    assert client.similarity_search.queries == [
        "project context #memory_type:fact",
        "project context #memory_type:preference",
    ]


def test_duplicate_type_does_not_issue_duplicate_backend_search():
    client = _Client([_memory("fact", "fact", 0.8)])
    service = MemoryReadService(client)

    result = service.search_memories(
        query="project context",
        agent_id="agent-1",
        type=["fact", "fact"],
        limit=10,
    )

    assert [memory["id"] for memory in result["results"]] == ["fact"]
    assert client.similarity_search.queries == ["project context #memory_type:fact"]


def test_invalid_later_type_is_rejected_before_any_backend_search():
    client = _Client([_memory("fact", "fact", 0.8)])
    service = MemoryReadService(client)

    with pytest.raises(MemoryError, match="Invalid memory_type"):
        service.search_memories(
            query="project context",
            agent_id="agent-1",
            type=["fact", "not-a-type"],
            limit=10,
        )

    assert client.similarity_search.queries == []
