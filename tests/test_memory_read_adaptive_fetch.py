"""Tests for opt-in adaptive candidate fetching in active-only memory recall."""

from datetime import datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memanto.app.models.session import Session
from memanto.app.services.memory_read_service import (
    ADAPTIVE_ACTIVE_MIN_POOL,
    MOORCHEH_MAX_TOP_K,
    MemoryReadService,
)
from memanto.app.utils.errors import MemoryOperationError


def _raw_item(
    mem_id: str,
    status: str | None = "active",
    *,
    score: float = 0.9,
    nested_status: bool = False,
) -> dict[str, Any]:
    """Build a raw backend search result row."""
    item: dict[str, Any] = {
        "id": mem_id,
        "text": f"[FACT] Memory {mem_id}\n\nBody for {mem_id}",
        "memory_type": "fact",
        "agent_id": "agent-1",
        "actor_id": "agent-1",
        "source": "user",
        "confidence": 0.9,
        "created_at": "2026-07-01T00:00:00Z",
        "updated_at": "2026-07-01T00:00:00Z",
        "score": score,
    }
    if status is not None:
        if nested_status:
            item["metadata"] = {"status": status}
        else:
            item["status"] = status
    return item


class _RankedSearch:
    """Fake similarity_search backend slicing ranked rows by ``top_k``."""

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        top_k = kwargs.get("top_k")
        sliced = self.rows[:top_k] if top_k is not None else self.rows
        return {"results": sliced, "execution_time": 0.01}


class _SequenceSearch:
    """Fake similarity_search backend returning pre-canned responses per call."""

    def __init__(self, responses: list[Any]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def query(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _Client:
    """Minimal client exposing ``similarity_search``."""

    def __init__(self, search: Any):
        self.similarity_search = search


def _service(search: Any) -> MemoryReadService:
    return MemoryReadService(cast(Any, _Client(search)))


@pytest.mark.parametrize(
    ("limit", "expected_top_k"),
    [
        (1, ADAPTIVE_ACTIVE_MIN_POOL),
        (10, ADAPTIVE_ACTIVE_MIN_POOL),
        (12, ADAPTIVE_ACTIVE_MIN_POOL),
        (13, 26),
        (20, 40),
        (49, 98),
        (50, MOORCHEH_MAX_TOP_K),
        (60, MOORCHEH_MAX_TOP_K),
    ],
)
def test_adaptive_fetch_computes_initial_small_candidate_pool(
    limit: int, expected_top_k: int
):
    rows = [_raw_item(f"active-{i}", "active") for i in range(120)]
    search = _RankedSearch(rows)
    service = _service(search)

    result = service.search_memories(
        query="project notes",
        agent_id="agent-1",
        status="active",
        limit=limit,
        _adaptive_fetch=True,
    )

    assert len(search.calls) == 1
    assert search.calls[0]["top_k"] == expected_top_k
    assert len(result["results"]) == min(limit, MOORCHEH_MAX_TOP_K)
    assert "#status:" not in search.calls[0]["query"]


def test_adaptive_fetch_retries_when_filtering_leaves_insufficient_active_results():
    # First 25 rows have only 4 active items (< limit=10); ranks 25..44 have 10 active.
    rows = (
        [_raw_item(f"exp-head-{i}", "expired") for i in range(21)]
        + [_raw_item(f"act-head-{i}", "active") for i in range(4)]
        + [_raw_item(f"act-tail-{i}", "active") for i in range(10)]
        + [_raw_item(f"exp-tail-{i}", "expired") for i in range(20)]
    )
    search = _RankedSearch(rows)
    service = _service(search)

    result = service.search_memories(
        query="project notes",
        agent_id="agent-1",
        status="active",
        limit=10,
        _adaptive_fetch=True,
    )

    assert [call["top_k"] for call in search.calls] == [25, MOORCHEH_MAX_TOP_K]
    assert [item["id"] for item in result["results"]] == (
        [f"act-head-{i}" for i in range(4)] + [f"act-tail-{i}" for i in range(6)]
    )
    assert result["total_found"] == 10
    assert result["total_available"] == 14
    assert result["has_more"] is True


def test_adaptive_fetch_treats_legacy_missing_status_and_nested_status_correctly():
    rows = (
        [_raw_item(f"nested-exp-{i}", "expired", nested_status=True) for i in range(20)]
        + [_raw_item(f"legacy-{i}", None) for i in range(5)]
        + [
            _raw_item(f"nested-act-{i}", "active", nested_status=True)
            for i in range(10)
        ]
    )
    search = _RankedSearch(rows)
    service = _service(search)

    result = service.search_memories(
        query="legacy",
        agent_id="agent-1",
        status="active",
        limit=10,
        _adaptive_fetch=True,
    )

    assert [call["top_k"] for call in search.calls] == [25, MOORCHEH_MAX_TOP_K]
    assert [item["id"] for item in result["results"]] == (
        [f"legacy-{i}" for i in range(5)] + [f"nested-act-{i}" for i in range(5)]
    )


def test_adaptive_fetch_does_not_retry_when_enough_active_results_found():
    # Exact boundary: 15 expired + 10 active in the first 25 satisfies limit=10.
    rows = (
        [_raw_item(f"exp-{i}", "expired") for i in range(15)]
        + [_raw_item(f"act-{i}", "active") for i in range(10)]
        + [_raw_item("act-extra", "active")]
    )
    search = _RankedSearch(rows)
    service = _service(search)

    result = service.search_memories(
        query="project notes",
        agent_id="agent-1",
        status="active",
        limit=10,
        _adaptive_fetch=True,
    )

    assert [call["top_k"] for call in search.calls] == [25]
    assert [item["id"] for item in result["results"]] == [f"act-{i}" for i in range(10)]


def test_adaptive_fetch_does_not_retry_when_initial_response_is_not_full():
    # Backend only has 12 total items (< top_k=25), so retrying at 100 cannot help.
    rows = [_raw_item(f"exp-{i}", "expired") for i in range(9)] + [
        _raw_item(f"act-{i}", "active") for i in range(3)
    ]
    search = _RankedSearch(rows)
    service = _service(search)

    result = service.search_memories(
        query="project notes",
        agent_id="agent-1",
        status="active",
        limit=10,
        _adaptive_fetch=True,
    )

    assert [call["top_k"] for call in search.calls] == [25]
    assert [item["id"] for item in result["results"]] == [f"act-{i}" for i in range(3)]


def test_adaptive_fetch_does_not_retry_when_initial_pool_already_at_max():
    # limit=60 computes initial top_k=100; do not issue a duplicate top_k=100 call.
    rows = [_raw_item(f"exp-{i}", "expired") for i in range(80)] + [
        _raw_item(f"act-{i}", "active") for i in range(20)
    ]
    search = _RankedSearch(rows)
    service = _service(search)

    result = service.search_memories(
        query="project notes",
        agent_id="agent-1",
        status="active",
        limit=60,
        _adaptive_fetch=True,
    )

    assert [call["top_k"] for call in search.calls] == [MOORCHEH_MAX_TOP_K]
    assert result["total_found"] == 20


def test_adaptive_fetch_retry_replaces_rather_than_appends_results():
    initial_rows = [_raw_item(f"initial-exp-{i}", "expired") for i in range(23)] + [
        _raw_item("initial-act-0", "active"),
        _raw_item("initial-act-1", "active"),
    ]
    retry_rows = [_raw_item(f"retry-act-{i}", "active") for i in range(6)]
    search = _SequenceSearch(
        [
            {"results": initial_rows, "execution_time": 0.01},
            {"results": retry_rows, "execution_time": 0.02},
        ]
    )
    service = _service(search)

    result = service.search_memories(
        query="project notes",
        agent_id="agent-1",
        status="active",
        limit=5,
        _adaptive_fetch=True,
    )

    assert [call["top_k"] for call in search.calls] == [25, MOORCHEH_MAX_TOP_K]
    assert [item["id"] for item in result["results"]] == [
        f"retry-act-{i}" for i in range(5)
    ]
    assert result["total_found"] == 5
    assert result["total_available"] == 6
    assert result["has_more"] is True


def test_adaptive_fetch_disabled_by_default_and_keyword_only():
    rows = [_raw_item(f"act-{i}", "active") for i in range(10)]
    search = _RankedSearch(rows)
    service = _service(search)

    service.search_memories(query="project notes", agent_id="agent-1", status="active")
    service.search_memories(
        query="project notes",
        agent_id="agent-1",
        status="active",
        limit=10,
        _adaptive_fetch=False,
    )

    assert [call["top_k"] for call in search.calls] == [
        MOORCHEH_MAX_TOP_K,
        MOORCHEH_MAX_TOP_K,
    ]

    with pytest.raises(TypeError):
        cast(Any, service.search_memories)(
            "q",
            "agent-1",
            None,
            None,
            None,
            "active",
            10,
            0,
            None,
            None,
            None,
            None,
            True,
        )


@pytest.mark.parametrize(
    ("extra_kwargs", "expected_top_k"),
    [
        ({"status": "all", "limit": 7}, 7),
        ({"status": "expired", "limit": 10}, MOORCHEH_MAX_TOP_K),
        (
            {"status": "active", "limit": 10, "created_after": "2026-01-01T00:00:00Z"},
            MOORCHEH_MAX_TOP_K,
        ),
        (
            {"status": "active", "limit": 10, "created_before": "2026-12-31T00:00:00Z"},
            MOORCHEH_MAX_TOP_K,
        ),
        ({"status": "active", "limit": 10, "min_confidence": 0.5}, MOORCHEH_MAX_TOP_K),
        ({"status": "active", "limit": 10, "min_confidence": 0.0}, MOORCHEH_MAX_TOP_K),
        ({"status": "active", "limit": 10, "offset": 5}, MOORCHEH_MAX_TOP_K),
        ({"status": "active", "limit": 0}, MOORCHEH_MAX_TOP_K),
    ],
)
def test_ineligible_single_query_paths_preserve_existing_behavior(
    extra_kwargs: dict[str, Any], expected_top_k: int
):
    rows = [_raw_item(f"exp-{i}", "expired") for i in range(30)]
    search = _RankedSearch(rows)
    service = _service(search)

    service.search_memories(
        query="project notes",
        agent_id="agent-1",
        _adaptive_fetch=True,
        **extra_kwargs,
    )

    assert [call["top_k"] for call in search.calls] == [expected_top_k]


def test_ineligible_multi_type_query_preserves_existing_behavior():
    rows = [_raw_item(f"exp-{i}", "expired") for i in range(30)]
    search = _RankedSearch(rows)
    service = _service(search)

    service.search_memories(
        query="project notes",
        agent_id="agent-1",
        type=["fact", "preference"],
        status="active",
        limit=10,
        _adaptive_fetch=True,
    )

    assert [call["top_k"] for call in search.calls] == [
        MOORCHEH_MAX_TOP_K,
        MOORCHEH_MAX_TOP_K,
    ]


def test_eligible_query_with_server_side_filters_uses_adaptive_fetch():
    rows = [_raw_item(f"act-{i}", "active") for i in range(15)]
    search = _RankedSearch(rows)
    service = _service(search)

    result = service.search_memories(
        query="project notes",
        agent_id="agent-1",
        type=["fact"],
        tags=["release"],
        min_similarity_score=0.5,
        metadata_filters={"source": "cli"},
        status="active",
        limit=10,
        _adaptive_fetch=True,
    )

    assert [call["top_k"] for call in search.calls] == [25]
    assert result["total_found"] == 10


def test_empty_results_list_handled_safely():
    search = _SequenceSearch([{"results": [], "execution_time": 0.01}])
    service = _service(search)

    result = service.search_memories(
        query="project notes",
        agent_id="agent-1",
        status="active",
        limit=10,
        _adaptive_fetch=True,
    )

    assert [call["top_k"] for call in search.calls] == [25]
    assert result["results"] == []
    assert result["total_found"] == 0
    assert result["total_available"] == 0


@pytest.mark.parametrize("envelope", [{}, {"execution_time": 0.01}])
def test_extract_search_items_rejects_missing_results_key(envelope: dict[str, Any]):
    with pytest.raises(MemoryOperationError, match="Missing 'results'"):
        MemoryReadService._extract_search_items([envelope])


@pytest.mark.parametrize("envelope", [{}, {"execution_time": 0.01}])
def test_missing_results_key_on_initial_response_raises(envelope: dict[str, Any]):
    search = _SequenceSearch([envelope])
    service = _service(search)

    with pytest.raises(MemoryOperationError, match="Missing 'results'"):
        service.search_memories(
            query="project notes",
            agent_id="agent-1",
            status="active",
            limit=10,
            _adaptive_fetch=True,
        )

    assert [call["top_k"] for call in search.calls] == [25]


@pytest.mark.parametrize("retry_envelope", [{}, {"execution_time": 0.02}])
def test_missing_results_key_on_retry_response_raises(retry_envelope: dict[str, Any]):
    initial_rows = [_raw_item(f"exp-{i}", "expired") for i in range(24)] + [
        _raw_item("act-0", "active")
    ]
    search = _SequenceSearch(
        [
            {"results": initial_rows, "execution_time": 0.01},
            retry_envelope,
        ]
    )
    service = _service(search)

    with pytest.raises(MemoryOperationError, match="Missing 'results'"):
        service.search_memories(
            query="project notes",
            agent_id="agent-1",
            status="active",
            limit=10,
            _adaptive_fetch=True,
        )

    assert [call["top_k"] for call in search.calls] == [25, MOORCHEH_MAX_TOP_K]


@pytest.mark.parametrize(
    "bad_response",
    [
        None,
        "corrupt",
        {},
        {"execution_time": 0.01},
        {"results": None},
        {"results": "not-a-list"},
        {"results": ["not-a-dict"]},
        {"results": [{"id": "1", "metadata": "not-a-dict"}]},
    ],
)
def test_malformed_initial_search_response_raises_memory_operation_error(
    bad_response: Any,
):
    search = _SequenceSearch([bad_response])
    service = _service(search)

    with pytest.raises(MemoryOperationError, match="Data corruption detected"):
        service.search_memories(
            query="project notes",
            agent_id="agent-1",
            status="active",
            limit=10,
            _adaptive_fetch=True,
        )


@pytest.mark.parametrize(
    "bad_retry",
    [
        None,
        {},
        {"results": None},
        {"results": ["not-a-dict"]},
        {"results": [{"id": "1", "metadata": "not-a-dict"}]},
    ],
)
def test_malformed_retry_search_response_raises_memory_operation_error(bad_retry: Any):
    initial_rows = [_raw_item(f"exp-{i}", "expired") for i in range(25)]
    search = _SequenceSearch(
        [{"results": initial_rows, "execution_time": 0.01}, bad_retry]
    )
    service = _service(search)

    with pytest.raises(MemoryOperationError, match="Data corruption detected"):
        service.search_memories(
            query="project notes",
            agent_id="agent-1",
            status="active",
            limit=10,
            _adaptive_fetch=True,
        )


def test_fastapi_recall_route_enables_adaptive_fetch():
    from memanto.app.clients.moorcheh import get_moorcheh_client
    from memanto.app.routes import memory as memory_routes
    from memanto.app.routes.auth_deps import get_current_session

    now = datetime.now(timezone.utc)
    fake_session = Session(
        session_id="sess-adaptive-1",
        session_token="tok-adaptive-1",
        agent_id="agent-1",
        namespace="memanto_agent_agent-1",
        started_at=now,
        expires_at=now + timedelta(hours=6),
    )
    rows = [_raw_item(f"act-{i}", "active") for i in range(30)]
    search = _RankedSearch(rows)
    fake_client = _Client(search)

    test_app = FastAPI()
    test_app.include_router(memory_routes.router, prefix="/api/v2/agents")
    test_app.dependency_overrides[get_current_session] = lambda: fake_session
    test_app.dependency_overrides[get_moorcheh_client] = lambda: fake_client

    client = TestClient(test_app)
    with patch.object(
        memory_routes._config_manager,
        "get_recall_config",
        return_value={"limit": 10, "min_similarity": None},
    ):
        resp = client.post(
            "/api/v2/agents/agent-1/recall",
            json={"query": "project notes", "status": "active", "limit": 10},
        )

    assert resp.status_code == 200, resp.text
    assert [call["top_k"] for call in search.calls] == [25]
    assert resp.json()["count"] == 10


@pytest.mark.parametrize("client_path", ["direct_client", "sdk_client"])
def test_client_recall_enables_adaptive_fetch(client_path: str):
    client_cls: Any
    if client_path == "direct_client":
        from memanto.cli.client.direct_client import DirectClient

        client_cls = DirectClient
        config_target = "memanto.cli.client.direct_client.ConfigManager"
    else:
        from memanto.cli.client.sdk_client import SdkClient

        client_cls = SdkClient
        config_target = "memanto.cli.client.sdk_client.ConfigManager"

    rows = [_raw_item(f"act-{i}", "active") for i in range(30)]
    search = _RankedSearch(rows)
    read_service = _service(search)

    client = client_cls.__new__(client_cls)
    with (
        patch(config_target) as mock_cfg_cls,
        patch.object(
            client_cls, "_get_validated_session_for_agent", return_value=MagicMock()
        ),
        patch.object(client_cls, "_get_read_service", return_value=read_service),
    ):
        mock_cfg_cls.return_value.get_recall_config.return_value = {
            "limit": 10,
            "min_similarity": None,
        }
        result = client.recall(
            agent_id="agent-1",
            query="project notes",
            limit=10,
            status="active",
        )

    assert [call["top_k"] for call in search.calls] == [25]
    assert result["count"] == 10
    assert len(result["memories"]) == 10
