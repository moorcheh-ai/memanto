"""Coverage for recalling across several agents in one query."""

import threading
from typing import Any, cast

import pytest
from pydantic import ValidationError

from memanto.app.core import agent_namespace
from memanto.app.routes.memory import MultiRecallRequest
from memanto.app.services.memory_read_service import MemoryReadService


def _memory(
    memory_id: str, *, agent_id: str, score: float, memory_type: str = "fact"
) -> dict:
    """Build one formatted backend row for an agent's namespace."""
    return {
        "id": memory_id,
        "text": f"[{memory_type.upper()}] {memory_id}\n\n{memory_id} content",
        "memory_type": memory_type,
        "agent_id": agent_id,
        "actor_id": agent_id,
        "source": "user",
        "confidence": 0.9,
        "status": "active",
        "created_at": "2026-07-20T00:00:00Z",
        "updated_at": "2026-07-20T00:00:00Z",
        "score": score,
    }


def _rows_by_namespace(rows_by_agent: dict[str, list[dict]], **kwargs) -> list[dict]:
    """Collect the rows whose agent namespace was actually searched."""
    rows: list[dict] = []
    for namespace in kwargs["namespaces"]:
        for agent_id, agent_rows in rows_by_agent.items():
            if namespace == agent_namespace(agent_id):
                rows.extend(agent_rows)
    return rows


class _NamespaceSearch:
    """Return an agent's rows only when that agent's namespace is searched."""

    def __init__(self, rows_by_agent: dict[str, list[dict]]):
        """Retain per-agent rows and a trace of searched namespaces."""
        self.rows_by_agent = rows_by_agent
        self.namespaces_seen: list[tuple[str, ...]] = []

    def query(self, **kwargs):
        """Serve the rows that belong to the requested namespaces."""
        self.namespaces_seen.append(tuple(kwargs["namespaces"]))
        rows = _rows_by_namespace(self.rows_by_agent, **kwargs)
        return {"results": rows[: kwargs["top_k"]], "execution_time": 0.01}


class _BarrierSearch(_NamespaceSearch):
    """Require two agent searches to overlap before either can complete."""

    def __init__(self, rows_by_agent: dict[str, list[dict]]):
        """Initialize per-agent rows and a two-party barrier."""
        super().__init__(rows_by_agent)
        self.barrier = threading.Barrier(2)

    def query(self, **kwargs):
        """Fail deterministically if the two agent searches run sequentially."""
        self.barrier.wait(timeout=5)
        return super().query(**kwargs)


class _Client:
    """Expose the fake search surface expected by MemoryReadService."""

    def __init__(self, search: _NamespaceSearch):
        """Attach the search surface the read service calls into."""
        self.similarity_search = search


def _service(
    rows_by_agent: dict[str, list[dict]],
) -> tuple[_Client, MemoryReadService]:
    """Adapt the deliberately minimal structural fake to the SDK client type."""
    client = _Client(_NamespaceSearch(rows_by_agent))
    return client, MemoryReadService(cast(Any, client))


def test_every_hit_is_labelled_with_the_agent_it_came_from():
    """A merged result set stays attributable to the agent that owns each row."""
    _, service = _service(
        {
            "agent-a": [_memory("a1", agent_id="agent-a", score=0.8)],
            "agent-b": [_memory("b1", agent_id="agent-b", score=0.7)],
        }
    )

    result = service.search_memories_multi(
        agent_ids=["agent-a", "agent-b"], query="deploys", limit=10
    )

    assert [(row["id"], row["agent_id"]) for row in result["results"]] == [
        ("a1", "agent-a"),
        ("b1", "agent-b"),
    ]


def test_agents_are_ranked_against_each_other():
    """The merged ranking is score-ordered across agents, not per agent."""
    _, service = _service(
        {
            "agent-a": [_memory("a-low", agent_id="agent-a", score=0.4)],
            "agent-b": [_memory("b-high", agent_id="agent-b", score=0.95)],
        }
    )

    result = service.search_memories_multi(
        agent_ids=["agent-a", "agent-b"], query="deploys", limit=10
    )

    assert [row["id"] for row in result["results"]] == ["b-high", "a-low"]


def test_limit_applies_to_the_merged_ranking():
    """Limit is a page size for the union, not a per-agent allowance."""
    _, service = _service(
        {
            "agent-a": [
                _memory("a1", agent_id="agent-a", score=0.9),
                _memory("a2", agent_id="agent-a", score=0.8),
            ],
            "agent-b": [_memory("b1", agent_id="agent-b", score=0.85)],
        }
    )

    result = service.search_memories_multi(
        agent_ids=["agent-a", "agent-b"], query="deploys", limit=2
    )

    assert [row["id"] for row in result["results"]] == ["a1", "b1"]
    assert result["total_found"] == 3


def test_same_id_under_two_agents_is_not_collapsed():
    """Ids are only unique inside one agent's namespace."""
    _, service = _service(
        {
            "agent-a": [_memory("shared", agent_id="agent-a", score=0.9)],
            "agent-b": [_memory("shared", agent_id="agent-b", score=0.8)],
        }
    )

    result = service.search_memories_multi(
        agent_ids=["agent-a", "agent-b"], query="deploys", limit=10
    )

    assert [(row["id"], row["agent_id"]) for row in result["results"]] == [
        ("shared", "agent-a"),
        ("shared", "agent-b"),
    ]


def test_repeated_agents_collapse_to_one_search():
    """Passing an agent twice must not double its weight in the ranking."""
    client, service = _service(
        {"agent-a": [_memory("a1", agent_id="agent-a", score=0.9)]}
    )

    result = service.search_memories_multi(
        agent_ids=["agent-a", "agent-a", "  "], query="deploys", limit=10
    )

    assert [row["id"] for row in result["results"]] == ["a1"]
    assert client.similarity_search.namespaces_seen == [(agent_namespace("agent-a"),)]


def test_blank_agent_list_returns_nothing_without_searching():
    """An unusable agent list is an empty page, not a whole-namespace search."""
    client, service = _service({})

    result = service.search_memories_multi(
        agent_ids=["", "   "], query="deploys", limit=10
    )

    assert result == {"results": [], "total_found": 0, "execution_time": 0}
    assert client.similarity_search.namespaces_seen == []


def test_agent_searches_run_concurrently():
    """Agent searches overlap instead of adding their latencies together."""
    client = _Client(
        _BarrierSearch(
            {
                "agent-a": [_memory("a1", agent_id="agent-a", score=0.7)],
                "agent-b": [_memory("b1", agent_id="agent-b", score=0.8)],
            }
        )
    )
    service = MemoryReadService(cast(Any, client))

    result = service.search_memories_multi(
        agent_ids=["agent-a", "agent-b"], query="deploys", limit=10
    )

    assert {row["id"] for row in result["results"]} == {"a1", "b1"}


def test_request_cleans_agent_ids():
    """Whitespace is trimmed and duplicates collapse before any search runs."""
    request = MultiRecallRequest(
        agent_ids=[" agent-a ", "agent-a", "agent-b"], query="deploys"
    )

    assert request.agent_ids == ["agent-a", "agent-b"]


def test_request_rejects_an_empty_agent_list():
    """A multi-agent recall without agents is a client error, not a broad read."""
    with pytest.raises(ValidationError):
        MultiRecallRequest(agent_ids=[], query="deploys")


def test_request_rejects_blank_agent_ids():
    """Blank ids are rejected rather than treated as a namespace."""
    with pytest.raises(ValidationError):
        MultiRecallRequest(agent_ids=["   ", "\t"], query="deploys")


def test_request_rejects_a_blank_query():
    """Recall filters and limits are inherited from the single-agent request."""
    with pytest.raises(ValidationError):
        MultiRecallRequest(agent_ids=["agent-a"], query="   ")
