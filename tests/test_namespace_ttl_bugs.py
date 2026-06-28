"""
Regression tests for namespace parsing and TTL timezone bugs.

Bug 1: MemoryScope.from_namespace() crashes when scope_id contains underscores.
  - namespace "memanto_user_john_doe" would split into 4 parts and raise ValueError
  - Fix: use split("_", maxsplit=1) on the remainder after "memanto_"

Bug 2: _filter_expired_memories() raises TypeError when comparing timezone-aware
  datetime.now(timezone.utc) with naive datetime.utcnow() used by MemoryRecord.
  - Fix: normalize both to the same timezone awareness before comparison
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from memanto.app.core import MemoryScope


class TestFromNamespaceUnderscoreBug:
    """Regression tests for from_namespace with underscore-containing scope_id."""

    def test_simple_scope_id(self):
        """Basic case: scope_id without underscores works as before."""
        scope = MemoryScope.from_namespace("memanto_user_123")
        assert scope.scope_type == "user"
        assert scope.scope_id == "123"

    def test_scope_id_with_underscore(self):
        """scope_id containing underscores should not break parsing."""
        scope = MemoryScope.from_namespace("memanto_user_john_doe")
        assert scope.scope_type == "user"
        assert scope.scope_id == "john_doe"

    def test_scope_id_with_multiple_underscores(self):
        """scope_id with multiple underscores should be preserved fully."""
        scope = MemoryScope.from_namespace("memanto_agent_my_bot_v2")
        assert scope.scope_type == "agent"
        assert scope.scope_id == "my_bot_v2"

    def test_roundtrip_with_underscore_scope_id(self):
        """to_namespace -> from_namespace roundtrip preserves scope_id."""
        original = MemoryScope(scope_type="user", scope_id="complex_id_123_456")
        namespace = original.to_namespace()
        parsed = MemoryScope.from_namespace(namespace)
        assert parsed.scope_type == original.scope_type
        assert parsed.scope_id == original.scope_id

    def test_invalid_namespace_no_prefix(self):
        """Namespaces without memanto_ prefix should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid MEMANTO namespace"):
            MemoryScope.from_namespace("other_user_123")

    def test_invalid_namespace_empty(self):
        """Empty namespace should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid MEMANTO namespace"):
            MemoryScope.from_namespace("")

    def test_invalid_namespace_only_prefix(self):
        """Namespace with only the prefix should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid MEMANTO namespace"):
            MemoryScope.from_namespace("memanto_")


class TestTTLTimezoneMismatch:
    """Regression tests for TTL filtering with mixed timezone awareness."""

    def _make_read_service(self):
        """Create a MemoryReadService with a mock client."""
        from memanto.app.services.memory_read_service import MemoryReadService
        return MemoryReadService(MagicMock())

    def test_naive_expires_at_not_expired(self):
        """Naive datetime expires_at in the future should be kept."""
        service = self._make_read_service()
        future = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        results = [{"id": "1", "expires_at": future}]
        filtered = service._filter_expired_memories(results)
        assert len(filtered) == 1

    def test_naive_expires_at_expired(self):
        """Naive datetime expires_at in the past should be filtered out."""
        service = self._make_read_service()
        past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        results = [{"id": "1", "expires_at": past}]
        filtered = service._filter_expired_memories(results)
        assert len(filtered) == 0

    def test_aware_expires_at_not_expired(self):
        """Timezone-aware expires_at in the future should be kept."""
        service = self._make_read_service()
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        results = [{"id": "1", "expires_at": future}]
        filtered = service._filter_expired_memories(results)
        assert len(filtered) == 1

    def test_aware_expires_at_expired(self):
        """Timezone-aware expires_at in the past should be filtered out."""
        service = self._make_read_service()
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        results = [{"id": "1", "expires_at": past}]
        filtered = service._filter_expired_memories(results)
        assert len(filtered) == 0

    def test_no_expires_at_kept(self):
        """Memories without expires_at should always be kept."""
        service = self._make_read_service()
        results = [{"id": "1"}, {"id": "2", "expires_at": None}]
        filtered = service._filter_expired_memories(results)
        assert len(filtered) == 2

    def test_mixed_naive_and_aware(self):
        """Mix of naive and aware datetimes should not raise TypeError."""
        service = self._make_read_service()
        naive_future = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        aware_past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        results = [
            {"id": "1", "expires_at": naive_future},
            {"id": "2", "expires_at": aware_past},
        ]
        filtered = service._filter_expired_memories(results)
        assert len(filtered) == 1
        assert filtered[0]["id"] == "1"
