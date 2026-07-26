"""Test: memories with None confidence must not be silently dropped.

Regression test for #770 — imported/migrated memories that lack a confidence
score were silently excluded from recall results when min_confidence > 0.
The fix treats unknown confidence as "include" (fail-open), consistent with
how _filter_expired_memories handles unparseable expiration dates.
"""

import pytest
from unittest.mock import MagicMock

from memanto.app.services.memory_read_service import MemoryReadService


def _make_read_service():
    return MemoryReadService(MagicMock())


class TestConfidenceFilterNoneHandling:
    """Memories with None/missing confidence must survive min_confidence filtering."""

    def test_none_confidence_included_with_positive_threshold(self):
        """A memory with confidence=None must NOT be dropped when min_confidence > 0."""
        svc = _make_read_service()
        results = [
            {"id": "1", "content": "Has confidence", "confidence": 0.9},
            {"id": "2", "content": "Imported memory", "confidence": None},
            {"id": "3", "content": "Low confidence", "confidence": 0.2},
        ]
        filtered = svc._filter_by_min_confidence(results, min_confidence=0.5)

        ids = [r["id"] for r in filtered]
        assert "1" in ids, "High confidence memory should be included"
        assert "2" in ids, "None confidence memory must NOT be dropped"
        assert "3" not in ids, "Low confidence memory should be excluded"

    def test_none_confidence_included_with_zero_threshold(self):
        """None confidence included when threshold is 0 (baseline behavior)."""
        svc = _make_read_service()
        results = [
            {"id": "1", "content": "Normal", "confidence": 0.5},
            {"id": "2", "content": "No confidence", "confidence": None},
        ]
        filtered = svc._filter_by_min_confidence(results, min_confidence=0.0)
        assert len(filtered) == 2

    def test_empty_string_confidence_treated_as_unknown(self):
        """Empty string confidence is unparseable — treated as unknown, included."""
        svc = _make_read_service()
        results = [
            {"id": "1", "content": "Empty conf", "confidence": ""},
        ]
        filtered = svc._filter_by_min_confidence(results, min_confidence=0.5)
        assert len(filtered) == 1

    def test_non_numeric_confidence_treated_as_unknown(self):
        """Non-numeric confidence string is treated as unknown, included."""
        svc = _make_read_service()
        results = [
            {"id": "1", "content": "Bad conf", "confidence": "high"},
        ]
        filtered = svc._filter_by_min_confidence(results, min_confidence=0.3)
        assert len(filtered) == 1

    def test_missing_confidence_key_treated_as_unknown(self):
        """Memory dict without 'confidence' key at all is included."""
        svc = _make_read_service()
        results = [
            {"id": "1", "content": "No key"},  # No confidence key
        ]
        filtered = svc._filter_by_min_confidence(results, min_confidence=0.5)
        assert len(filtered) == 1

    def test_numeric_filtering_still_works(self):
        """Normal numeric confidence filtering is unaffected by the fix."""
        svc = _make_read_service()
        results = [
            {"id": "1", "confidence": 0.9},
            {"id": "2", "confidence": 0.7},
            {"id": "3", "confidence": 0.3},
            {"id": "4", "confidence": 0.1},
        ]
        filtered = svc._filter_by_min_confidence(results, min_confidence=0.5)
        ids = [r["id"] for r in filtered]
        assert ids == ["1", "2"]

    def test_overflow_confidence_treated_as_unknown(self):
        """float() OverflowError (e.g. huge int) fail-opens like other unknowns."""
        svc = _make_read_service()
        results = [
            {"id": "1", "content": "Overflow conf", "confidence": 10**10000},
        ]
        filtered = svc._filter_by_min_confidence(results, min_confidence=0.5)
        assert len(filtered) == 1
