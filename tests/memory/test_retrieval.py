import datetime
import pytest

from memanto.memory.retrieval import Retrieval

class TestRetrieval:
    # ... existing tests ...

    def test_recall_yesterday_boundary(self):
        """Test that recall for yesterday properly bounds to UTC calendar day."""
        retrieval = Retrieval()
        today = datetime.datetime.utcnow().date()
        yesterday = today - datetime.timedelta(days=1)

        # Test relative time parameter
        memories = retrieval.recall_temporal(relative_time="yesterday")
        assert all(
            memory.timestamp.date() == yesterday
            for memory in memories
        )

        # Test explicit time range
        start = datetime.datetime.combine(yesterday, datetime.time.min)
        end = datetime.datetime.combine(yesterday, datetime.time.max)
        memories = retrieval.recall_temporal(start_time=start, end_time=end)
        assert all(
            memory.timestamp.date() == yesterday
            for memory in memories
        )

    # ... more focused tests ...