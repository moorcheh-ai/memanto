import pytest
from datetime import datetime, timezone
from memanto.app.services.okf_export_service import OkfExportService

class TestOkfExportService:
    # ... existing test cases ...

    def test_parse_ts_returns_aware_datetime(self):
        service = OkfExportService()

        # Test None input
        result = service._parse_ts(None)
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc

        # Test empty string input
        result = service._parse_ts("")
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc

        # Test naive datetime string
        naive_str = "2026-01-01T12:00:00"
        result = service._parse_ts(naive_str)
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc

        # Test naive datetime object
        naive_dt = datetime(2026, 1, 1, 12, 0, 0)
        result = service._parse_ts(naive_dt)
        assert result.tzinfo is not None
        assert result.tzinfo == timezone.utc

        # Test already aware datetime
        aware_dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = service._parse_ts(aware_dt)
        assert result == aware_dt

    def test_batch_store_memories_counts_correctly(self):
        service = OkfExportService()
        memories = [
            {"content": "memory1", "status": "success"},
            {"content": "memory2", "status": "rejected"},
            {"content": "memory3", "status": "error"},
            {"content": "memory4", "status": "success"},
            {"content": "memory5", "status": "pending"}
        ]

        result = service.batch_store_memories(memories)

        assert result["successful"] == 2
        assert result["rejected"] == 1
        assert result["failed"] == 2
        assert len(result["results"]) == 5

        # Verify failed items are marked as "failed"
        for r in result["results"]:
            if r["status"] != "success" and r["status"] != "rejected":
                assert r["status"] == "failed"