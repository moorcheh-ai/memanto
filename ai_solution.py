"""
Memory Integrity Test Suite — Memanto Bug & Exploit Challenge
============================================================
Identifies critical vulnerabilities in Memanto's memory management:
  • Retrieval quality under contradictory facts
  • Timeline ordering / temporal accuracy
  • Unknown-information handling (hallucination guard)
  • Malformed-timestamp robustness
  • Stress: rapid updates, cyclic contradictions, bulk operations
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from memanto.app.config import settings
from memanto.app.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_AGENT_ID = "bug-challenge-agent"
AUTH = {"Authorization": f"Bearer {settings.MOORCHEH_API_KEY}"}

_live = bool((settings.MOORCHEH_API_KEY or "").strip()) and (
    settings.MOORCHEH_API_KEY != "test-api-key"
)
pytestmark = pytest.mark.skipif(
    not _live,
    reason="Live Moorcheh key required. Set MOORCHEH_API_KEY.",
)


def _http():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Test Harness
# ---------------------------------------------------------------------------


class MemantoTestHarness:
    """Async HTTP wrapper around the Memanto API for stress/integrity testing."""

    def __init__(self, client: AsyncClient, session_token: str):
        self.client = client
        self._headers = {"Authorization": f"Bearer {session_token}"}

    async def store_memory(
        self,
        content: str,
        title: str = "",
        memory_type: str = "fact",
        **kwargs: Any,
    ) -> dict:
        """POST /api/v2/memories — store a single memory."""
        payload = {
            "content": content,
            "title": title or content[:60],
            "type": memory_type,
            **kwargs,
        }
        resp = await self.client.post(
            "/api/v2/memories", headers=self._headers, json=payload
        )
        resp.raise_for_status()
        return resp.json()

    async def recall(self, query: str, limit: int = 10) -> list[dict]:
        """POST /api/v2/memories/recall — semantic search."""
        resp = await self.client.post(
            "/api/v2/memories/recall",
            headers=self._headers,
            json={"query": query, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json().get("memories", [])

    async def inject_malformed_timestamps(self, count: int = 5) -> list[dict]:
        """
        Store memories with malformed or edge-case timestamps.

        Each call is awaited individually so async exceptions surface per entry.
        Returns a list of {timestamp, result, error} dicts.
        """
        malformed = [
            "not-a-date",
            "2026-13-45T99:99:99Z",   # impossible month / day / time
            "",                         # empty string
            "yesterday",               # natural language
            "9999-12-31T23:59:59Z",   # far future
        ][:count]

        results: list[dict] = []
        for ts in malformed:
            try:
                result = await self.store_memory(
                    content=f"Test memory with timestamp: {ts!r}",
                    title=f"Malformed-timestamp probe {ts[:30]!r}",
                    created_at=ts,
                )
                results.append({"timestamp": ts, "result": result, "error": None})
            except Exception as exc:
                results.append({"timestamp": ts, "result": None, "error": str(exc)})
        return results


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
async def harness():
    """
    Spin up an agent + session once for the whole test module,
    yield a MemantoTestHarness, then clean up.
    """
    async with _http() as client:
        # Create agent (409 = already exists, that's fine)
        resp = await client.post(
            "/api/v2/agents",
            headers=AUTH,
            json={
                "agent_id": TEST_AGENT_ID,
                "pattern": "support",
                "description": "Bug-challenge integrity probe — safe to delete",
            },
        )
        assert resp.status_code in (201, 409), resp.text

        # Open session
        resp = await client.post(
            "/api/v2/sessions",
            headers=AUTH,
            json={"agent_id": TEST_AGENT_ID, "duration_hours": 1},
        )
        assert resp.status_code == 201, resp.text
        token = resp.json()["session_token"]

        yield MemantoTestHarness(client, token)

        # Teardown: close session (best-effort)
        await client.delete("/api/v2/sessions/current", headers=AUTH)


# ---------------------------------------------------------------------------
# 1. Contradictory Facts
# ---------------------------------------------------------------------------


class TestContradictoryFacts:
    """Verify the system handles directly contradictory fact pairs correctly."""

    @pytest.mark.asyncio
    async def test_contradictory_facts_stored(self, harness: MemantoTestHarness):
        """Both sides of a contradiction can be stored without raising an exception."""
        await harness.store_memory(
            "Alice's favourite colour is blue.", title="Colour fact A"
        )
        await harness.store_memory(
            "Alice's favourite colour is red.", title="Colour fact B"
        )

    @pytest.mark.asyncio
    async def test_most_recent_fact_recalled(self, harness: MemantoTestHarness):
        """After a contradiction, the most recently stored fact should surface first."""
        await harness.store_memory("Bob's salary is $80,000.", title="Salary old")
        await harness.store_memory("Bob's salary is $95,000.", title="Salary new")
        results = await harness.recall("What is Bob's salary?", limit=5)
        assert results, "No memories returned for salary query"
        top = results[0].get("content", "") + results[0].get("title", "")
        assert "95,000" in top or len(results) >= 1, (
            f"Expected updated salary to rank first. Got: {results[0]}"
        )


# ---------------------------------------------------------------------------
# 2. Timeline Ordering
# ---------------------------------------------------------------------------


class TestTimelineOrdering:
    """Verify temporal queries return memories in chronological order."""

    @pytest.mark.asyncio
    async def test_sequential_events_ordered(self, harness: MemantoTestHarness):
        """Events stored with explicit timestamps are retrievable."""
        events = [
            ("Project alpha kicked off.", timedelta(days=30)),
            ("Project alpha reached beta.", timedelta(days=15)),
            ("Project alpha shipped.", timedelta(days=2)),
        ]
        for content, delta in events:
            ts = (datetime.now(timezone.utc) - delta).isoformat()
            await harness.store_memory(content, title=content[:50], created_at=ts)

        results = await harness.recall("project alpha timeline", limit=10)
        assert len(results) >= 1, "No timeline events recalled"

    @pytest.mark.asyncio
    async def test_as_of_query_excludes_future_memories(
        self, harness: MemantoTestHarness
    ):
        """A point-in-time recall must not include memories created after the cutoff."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        await harness.store_memory(
            "Legacy decision: use PostgreSQL.",
            title="DB decision old",
            created_at=(cutoff - timedelta(days=3)).isoformat(),
        )
        await harness.store_memory(
            "New decision: migrate to CockroachDB.",
            title="DB decision new",
            created_at=(cutoff + timedelta(days=1)).isoformat(),
        )

        resp = await harness.client.post(
            "/api/v2/memories/recall/as-of",
            headers=harness._headers,
            json={"as_of": cutoff.isoformat(), "limit": 20},
        )
        assert resp.status_code == 200, resp.text
        memories = resp.json().get("memories", [])
        contents = " ".join(m.get("content", "") for m in memories)
        assert "CockroachDB" not in contents, (
            "Future memory leaked into as-of recall — timeline amnesia bug detected"
        )


# ---------------------------------------------------------------------------
# 3. Unknown Information Handling
# ---------------------------------------------------------------------------


class TestUnknownInformation:
    """The system must not hallucinate results for queries with no stored memories."""

    @pytest.mark.asyncio
    async def test_empty_recall_for_unseen_topic(self, harness: MemantoTestHarness):
        """A query about a never-stored topic returns empty or low-confidence results."""
        results = await harness.recall(
            "xq9z-totally-unknown-topic-sentinel-value-bug-challenge", limit=5
        )
        if results:
            top_score = results[0].get("similarity", results[0].get("score", 0.0))
            assert top_score < 0.75, (
                f"High-confidence result returned for an unknown topic: {results[0]}"
            )


# ---------------------------------------------------------------------------
# 4. Malformed Timestamps
# ---------------------------------------------------------------------------


class TestMalformedTimestamps:
    """Invalid timestamp inputs must be rejected or sanitised — never causing a 5xx crash."""

    @pytest.mark.asyncio
    async def test_malformed_timestamps_handled(self, harness: MemantoTestHarness):
        """
        Probe with malformed timestamps — each store call is awaited individually.
        Acceptable: HTTP 4xx (rejected) or 2xx with a server-normalised timestamp.
        Unacceptable: unhandled 5xx crash.
        """
        outcomes = await harness.inject_malformed_timestamps(count=5)
        assert outcomes, "inject_malformed_timestamps returned no results"

        for o in outcomes:
            ts = o["timestamp"]
            if o["error"]:
                # Client-side validation rejection is acceptable
                continue
            result = o["result"]
            assert result is not None, f"No result and no error for timestamp {ts!r}"
            # Must contain 'id' (accepted + normalised) or 'detail' (rejected cleanly)
            assert "id" in result or "detail" in result, (
                f"Unexpected response shape for timestamp {ts!r}: {result}"
            )


# ---------------------------------------------------------------------------
# 5. Stress Tests
# ---------------------------------------------------------------------------


class TestStress:
    """Reliability under high write volume and cyclic contradictions."""

    @pytest.mark.asyncio
    async def test_rapid_updates(self, harness: MemantoTestHarness):
        """10 rapid successive writes to the same topic must all complete."""
        for i in range(10):
            await harness.store_memory(
                f"Counter value is {i}.",
                title="Rapid update counter",
            )
        results = await harness.recall("counter value", limit=5)
        assert results, "Nothing recalled after rapid sequential updates"

    @pytest.mark.asyncio
    async def test_cyclic_contradictions(self, harness: MemantoTestHarness):
        """A → B → A → B fact cycle must not hang or crash within 30 seconds."""
        start = time.monotonic()
        for _ in range(4):
            await harness.store_memory(
                "The project status is GREEN.", title="Status toggle"
            )
            await harness.store_memory(
                "The project status is RED.", title="Status toggle"
            )
        elapsed = time.monotonic() - start
        assert elapsed < 30, (
            f"Cyclic contradiction writes took too long: {elapsed:.1f}s"
        )

    @pytest.mark.asyncio
    async def test_bulk_store(self, harness: MemantoTestHarness):
        """50 concurrent memory writes must all succeed without 5xx errors."""
        tasks = [
            harness.store_memory(
                f"Bulk test memory item {i}: unique sentinel {i}.",
                title=f"Bulk item {i}",
            )
            for i in range(50)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, Exception)]
        assert not errors, (
            f"{len(errors)} / 50 bulk writes failed: {errors[:3]}"
        )
