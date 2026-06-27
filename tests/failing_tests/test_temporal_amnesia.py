"""
Failing test: search_as_of temporal amnesia - cannot see memories that have since expired.

This test demonstrates BUG-C7: _fetch_all_memories applies current-expiry
filtering before search_as_of can check historical state. Memories that
were alive at as_of_date but expired by now are invisible.

Expected: search_as_of returns memories that were alive at the target date
Actual: returns empty because _filter_expired_memories removes them first
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from memanto.app.services.memory_read_service import MemoryReadService


def test_search_as_of_sees_expired_memories():
    """A memory that was alive 30 min ago but expired now should appear in search_as_of."""

    now = datetime.now(timezone.utc)
    thirty_min_ago = now - timedelta(minutes=30)

    # Memory was created 1 hour ago with 30 min TTL (already expired)
    expired_memory = {
        "id": "mem_expired",
        "text": "[FACT] Deploy succeeded",
        "metadata": {
            "type": "fact",
            "scope_type": "agent",
            "scope_id": "a1",
            "confidence": 0.9,
            "status": "active",
            "created_at": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "expires_at": (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
            "title": "Deploy Status",
            "tags": [],
        },
    }

    client = MagicMock()
    client.documents.fetch_text_data.return_value = {
        "items": [expired_memory],
        "pagination": {"has_more": False},
    }

    read_svc = MemoryReadService(client)

    # Query what was known 15 minutes ago (memory was still alive then)
    result = read_svc.search_as_of(
        agent_id="a1",
        as_of_date=thirty_min_ago.isoformat(),
        query="deploy",
    )

    # The expired memory should appear because it was alive 15 min ago
    # Bug: it gets filtered out by _filter_expired_memories first
    assert len(result["results"]) > 0, (
        "Temporal amnesia: memory alive at as_of_date is invisible because "
        "current-expiry filtering runs before the as-of check"
    )
