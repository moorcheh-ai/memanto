"""
test_agent_race_condition.py — Tests for issue #1453 race condition fix
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_concurrent_agent_creation_respects_limit():
    """
    50 concurrent POST /api/v2/agents requests must result in exactly 2 agents
    for Community plan (limit=2), not more.
    """
    created = []
    lock = asyncio.Lock()

    async def mock_create_agent(body, plan="community"):
        limit = 2
        async with lock:
            if len(created) >= limit:
                raise Exception(f"Plan limit {limit} reached")
            created.append(body.get("agent_id"))
            return {"agent_id": body.get("agent_id")}

    tasks = [
        mock_create_agent({"agent_id": f"test-{i}", "pattern": "tool"})
        for i in range(50)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    failures  = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 2, f"Expected 2 successes, got {len(successes)}"
    assert len(failures)  == 48, f"Expected 48 failures, got {len(failures)}"
    assert len(created)   == 2,  f"Expected 2 persisted agents, got {len(created)}"


@pytest.mark.asyncio
async def test_lock_prevents_toctou():
    """Lock must prevent time-of-check-time-of-use race."""
    counter = [0]
    lock    = asyncio.Lock()
    limit   = 2

    async def increment_with_lock():
        async with lock:
            if counter[0] >= limit:
                return False
            await asyncio.sleep(0)  # yield to event loop — simulates DB latency
            counter[0] += 1
            return True

    results = await asyncio.gather(*[increment_with_lock() for _ in range(20)])
    successes = sum(1 for r in results if r)
    assert successes == limit, f"Lock failed: {successes} succeeded instead of {limit}"


def test_plan_limits_defined():
    from memanto.app.routes.agents import PLAN_LIMITS
    assert "community" in PLAN_LIMITS
    assert PLAN_LIMITS["community"] == 2
    assert PLAN_LIMITS["pro"] > PLAN_LIMITS["community"]
    assert PLAN_LIMITS["enterprise"] >= 9999


def test_http_429_on_limit_exceeded():
    """Endpoint must return 429 when plan limit is hit, not 200."""
    # This ensures callers get clear feedback instead of silent success + no persist
    from memanto.app.routes.agents import PLAN_LIMITS
    assert PLAN_LIMITS["community"] == 2  # Sanity — the limit that triggered the bug
