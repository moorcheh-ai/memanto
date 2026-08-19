"""Regression coverage for union semantics in multi-type recall."""

import re
import threading
from typing import Any, cast

import pytest

import memanto.app.services.memory_read_service as memory_read_service_module
from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.utils.errors import MemoryError


def _memory(memory_id: str, memory_type: str, score: float) -> dict:
    """Build one formatted backend row for a memory type."""
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
        """Retain candidate rows and a trace of dispatched queries."""
        self.rows = rows
        self.queries: list[str] = []

    def query(self, **kwargs):
        """Apply every exact type filter to the in-memory rows."""
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
    """Expose the fake search surface expected by MemoryReadService."""

    def __init__(self, rows: list[dict]):
        """Initialize a client with exact-filter search behavior."""
        self.similarity_search = _ExactFilterSearch(rows)


def _service(client: _Client) -> MemoryReadService:
    """Adapt the deliberately minimal structural fake to the SDK client type."""
    return MemoryReadService(cast(Any, client))


class _BarrierSearch:
    """Require two type searches to overlap before either can complete."""

    def __init__(self, rows: list[dict]):
        """Initialize candidate rows and a two-party synchronization barrier."""
        self.rows = rows
        self.barrier = threading.Barrier(2)

    def query(self, **kwargs):
        """Fail deterministically if the two searches run sequentially."""
        requested_type = re.search(r"#memory_type:([A-Za-z0-9_.-]+)", kwargs["query"])
        assert requested_type is not None
        self.barrier.wait(timeout=5)
        results = [
            row for row in self.rows if row["memory_type"] == requested_type.group(1)
        ]
        return {"results": results, "execution_time": 0.01}


def test_multi_type_recall_queries_each_type_and_returns_ranked_union():
    """Multi-type recall returns the score-ranked union of requested types."""
    client = _Client(
        [
            _memory("fact-low", "fact", 0.70),
            _memory("preference-high", "preference", 0.95),
            _memory("instruction-excluded", "instruction", 0.99),
        ]
    )
    service = _service(client)

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
    assert sorted(client.similarity_search.queries) == sorted(
        [
            "project context #memory_type:fact",
            "project context #memory_type:preference",
        ]
    )


def test_multi_type_searches_run_concurrently():
    """Independent exact-type searches overlap instead of adding their latency."""
    client = _Client([])
    client.similarity_search = _BarrierSearch(
        [
            _memory("fact", "fact", 0.8),
            _memory("preference", "preference", 0.9),
        ]
    )
    service = _service(client)

    result = service.search_memories(
        query="project context",
        agent_id="agent-1",
        type=["fact", "preference"],
        limit=10,
    )

    assert {memory["id"] for memory in result["results"]} == {
        "fact",
        "preference",
    }


def test_multi_type_execution_time_reports_parallel_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
):
    """Reported latency measures the dispatch window, not summed worker time."""
    timestamps = iter([100.0, 100.025])
    monkeypatch.setattr(
        memory_read_service_module, "monotonic", lambda: next(timestamps)
    )
    client = _Client(
        [
            _memory("fact", "fact", 0.8),
            _memory("preference", "preference", 0.9),
        ]
    )
    service = _service(client)

    result = service.search_memories(
        query="project context",
        agent_id="agent-1",
        type=["fact", "preference"],
        limit=10,
    )

    assert result["execution_time"] == pytest.approx(0.025)


def test_duplicate_type_does_not_issue_duplicate_backend_search():
    """Repeated input types collapse to one backend query."""
    client = _Client([_memory("fact", "fact", 0.8)])
    service = _service(client)

    result = service.search_memories(
        query="project context",
        agent_id="agent-1",
        type=["fact", "fact"],
        limit=10,
    )

    assert [memory["id"] for memory in result["results"]] == ["fact"]
    assert client.similarity_search.queries == ["project context #memory_type:fact"]


def test_invalid_later_type_is_rejected_before_any_backend_search():
    """Validation completes before any query is dispatched."""
    client = _Client([_memory("fact", "fact", 0.8)])
    service = _service(client)

    with pytest.raises(MemoryError, match="Invalid memory_type"):
        service.search_memories(
            query="project context",
            agent_id="agent-1",
            type=["fact", "not-a-type"],
            limit=10,
        )

    assert client.similarity_search.queries == []
