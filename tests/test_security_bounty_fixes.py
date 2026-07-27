"""
Security & memory-integrity fixes for the Memanto Bug & Exploit Challenge
(issue #770).

Two proven vulnerabilities in the ``memanto/app/services/memory_read_service.py``
core package, plus a follow-on caller fix in the legacy ``/answer`` REST route.

Fixes implemented
=================

1. [HIGH] ``MemoryReadService.generate_answer()`` was ``fail-open`` on a missing
   ``agent_id``: it fell back to ``self.namespace_service.list_namespaces()[0]``,
   which lists ALL ``memanto_*`` namespaces across all agents/tenants and picked
   the first one. A caller omitting its agent constraint would silently read
   another agent's memories -> cross-tenant information leak.

   Fix: reject a missing agent identifier with a ``MemoryError`` and require the
   namespace to be derived from the caller's own identifier. The method still
   accepts the legacy ``scope_id`` parameter so the ``/answer`` REST route keeps
   working, but both paths are now fail-close.

2. [MEDIUM] ``MemoryReadService._apply_temporal_filter()`` caught parsing errors
   for ``created_after``/``created_before`` with a bare ``pass`` and returned the
   full unfiltered result set (fail-open). A malformed caller-supplied timestamp
   silently dropped the time-window constraint, potentially leaking memories
   outside the requested window.

   Fix: let a malformed boundary propagate as an explicit error (fail-close),
   consistent with how other filters (e.g. ``memory_type``) reject bad input.
"""

from datetime import datetime, timezone

from unittest.mock import MagicMock

import pytest

from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.utils.errors import MemoryError


def _make_service():
    """Build a MemoryReadService with a fully mocked Moorcheh client."""
    client = MagicMock()
    client.answer = MagicMock()
    service = MemoryReadService(client)
    service._namespace_service = MagicMock()
    return service, client


class TestGenerateAnswerRejection:
    """A missing agent identifier MUST be rejected, never answered against
    another agent's namespace."""

    def test_missing_agent_id_raises(self):
        """A missing agent_id argument must raise MemoryError."""
        service, _ = _make_service()
        with pytest.raises(MemoryError, match="required"):
            service.generate_answer(query="hello")

    def test_none_agent_id_raises(self):
        """An explicit None agent_id must raise MemoryError."""
        service, _ = _make_service()
        with pytest.raises(MemoryError, match="required"):
            service.generate_answer(query="hello", agent_id=None)

    def test_empty_agent_id_raises(self):
        """An empty-string agent_id must raise MemoryError."""
        service, _ = _make_service()
        with pytest.raises(MemoryError, match="required"):
            service.generate_answer(query="hello", agent_id="")

    def test_legacy_scope_id_empty_raises(self):
        """The /answer route still passes scope_id=None by default -> rejected."""
        service, _ = _make_service()
        with pytest.raises(MemoryError, match="required"):
            service.generate_answer(query="hello", scope_type=None, scope_id=None)

    def test_explicit_agent_id_is_used(self):
        """With an agent_id, answer is generated against that agent's namespace
        and never falls back to an arbitrary one."""
        service, client = _make_service()
        service.namespace_service.list_namespaces.return_value = [
            "memanto_agent_other",
        ]
        client.answer.generate.return_value = {"answer": "ok"}

        result = service.generate_answer(query="hello", agent_id="alice")

        client.answer.generate.assert_called_once_with(
            namespace="memanto_agent_alice",
            query="hello",
            ai_model=client.answer.generate.call_args.kwargs["ai_model"],
        )
        # The other agent's namespace must NOT have been consulted.
        assert result["namespace"] == "memanto_agent_alice"


class TestTemporalFilterFailClose:
    """Invalid time boundaries must NOT silently disable the filter."""

    def _service(self):
        """Return a MemoryReadService with a fully mocked client."""
        service, _ = _make_service()
        return service

    def test_invalid_created_after_raises(self):
        """A malformed created_after timestamp must raise, not silently pass."""
        svc = self._service()
        with pytest.raises((ValueError, AttributeError, TypeError)):
            svc._apply_temporal_filter(
                results=[{"created_at": "2025-01-01T00:00:00Z"}],
                created_after="not-a-timestamp",
            )

    def test_invalid_created_before_raises(self):
        """A malformed created_before timestamp must raise, not silently pass."""
        svc = self._service()
        with pytest.raises((ValueError, AttributeError, TypeError)):
            svc._apply_temporal_filter(
                results=[{"created_at": "2025-01-01T00:00:00Z"}],
                created_before="also-bad",
            )

    def test_one_valid_one_invalid_raises(self):
        """Even if one boundary is fine, a bad boundary must not silently drop
        the entire filter."""
        svc = self._service()
        with pytest.raises((ValueError, AttributeError, TypeError)):
            svc._apply_temporal_filter(
                results=[{"created_at": "2025-01-01T00:00:00Z"}],
                created_after="2024-01-01T00:00:00Z",
                created_before="bad",
            )

    def test_valid_boundaries_filter_results(self):
        """Valid after/before boundaries must correctly filter results."""
        svc = self._service()
        out = svc._apply_temporal_filter(
            results=[
                {"created_at": "2024-06-01T00:00:00Z"},
                {"created_at": "2025-01-01T00:00:00Z"},
                {"created_at": "2025-12-01T00:00:00Z"},
            ],
            created_after="2024-12-01T00:00:00Z",
            created_before="2025-06-01T00:00:00Z",
        )
        assert len(out) == 1
        assert out[0]["created_at"] == "2025-01-01T00:00:00Z"

    def test_no_filters_returns_full_set(self):
        """Calling with no temporal boundaries must return the full result set unchanged."""
        svc = self._service()
        results = [{"created_at": "2024-01-01T00:00:00Z"}]
        assert svc._apply_temporal_filter(results) is results
