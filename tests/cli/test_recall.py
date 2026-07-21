import datetime
import pytest
from unittest.mock import patch

from memanto.cli.recall import main

class TestRecallCLI:
    # ... existing tests ...

    @patch("memanto.cli.recall.Retrieval")
    def test_as_of_yesterday(self, mock_retrieval):
        """Test that --as-of yesterday uses end of day."""
        test_args = ["recall", "--as-of", "yesterday"]
        today = datetime.datetime.utcnow().date()
        yesterday = today - datetime.timedelta(days=1)
        expected_end = datetime.datetime.combine(yesterday, datetime.time.max)

        with patch("sys.argv", test_args):
            main()

        # Verify the correct end time was used
        mock_retrieval.return_value.recall_temporal.assert_called_once()
        args, kwargs = mock_retrieval.return_value.recall_temporal.call_args
        assert kwargs["end_time"] == expected_end

    # ... more focused tests ...