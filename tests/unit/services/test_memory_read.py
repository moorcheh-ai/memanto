import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from memanto.services.memory_read import MemoryReadService

class TestMemoryReadService(unittest.TestCase):
    # ... existing test cases ...

    def test_temporal_filter_malformed_timestamp(self):
        """Test that memories with malformed timestamps are skipped."""
        svc = MemoryReadService(MagicMock())
        now = datetime.now().isoformat()
        results = [
            {'id': 'valid', 'created_at': now},
            {'id': 'malformed', 'created_at': 'GARBAGE'},
            {'id': 'another_valid', 'created_at': now},
        ]

        filtered = svc._apply_temporal_filter(results)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0]['id'], 'valid')
        self.assertEqual(filtered[1]['id'], 'another_valid')

    def test_temporal_filter_invalid_boundary(self):
        """Test that invalid boundaries raise ValueError."""
        svc = MemoryReadService(MagicMock())
        now = datetime.now().isoformat()
        results = [{'id': 'valid', 'created_at': now}]

        with self.assertRaises(ValueError):
            svc._apply_temporal_filter(results, created_after='GARBAGE')

        with self.assertRaises(ValueError):
            svc._apply_temporal_filter(results, created_before='GARBAGE')

    def test_temporal_filter_boundary_inclusion(self):
        """Test that boundary timestamps are included."""
        svc = MemoryReadService(MagicMock())
        now = datetime.now()
        results = [
            {'id': 'before', 'created_at': (now - timedelta(days=1)).isoformat()},
            {'id': 'exact', 'created_at': now.isoformat()},
            {'id': 'after', 'created_at': (now + timedelta(days=1)).isoformat()},
        ]

        filtered = svc._apply_temporal_filter(
            results,
            created_after=now.isoformat(),
            created_before=now.isoformat()
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['id'], 'exact')