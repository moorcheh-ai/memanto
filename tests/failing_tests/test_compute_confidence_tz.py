"""
Failing test: compute_confidence() crashes on timezone-aware created_at.

This test demonstrates BUG-H2: datetime.utcnow() (naive) is subtracted
from created_at which becomes timezone-aware after update_memory parses
ISO timestamps with timezone info.

Expected: should compute confidence without error
Actual: TypeError: can't subtract offset-naive and offset-aware datetimes
"""
import pytest
from datetime import datetime, timezone
from memanto.app.core import MemoryRecord


def test_compute_confidence_with_tz_aware_created_at():
    m = MemoryRecord(
        type="preference",
        title="Theme",
        content="prefers dark mode",
        scope_type="agent",
        scope_id="a1",
        actor_id="a1",
        source="user",
    )
    # Simulate what update_memory does when parsing ISO timestamps
    m.created_at = datetime.fromisoformat("2026-01-01T00:00:00+00:00")

    # Should not raise TypeError
    result = m.compute_confidence()
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0
