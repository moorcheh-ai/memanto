import datetime
from typing import List, Optional

from memanto.memory.models import Memory

class Retrieval:
    # ... existing code ...

    def recall_temporal(
        self,
        relative_time: Optional[str] = None,
        start_time: Optional[datetime.datetime] = None,
        end_time: Optional[datetime.datetime] = None,
    ) -> List[Memory]:
        """Retrieve memories based on temporal criteria."""
        if relative_time == "yesterday":
            # Get yesterday's UTC calendar day
            today = datetime.datetime.utcnow().date()
            yesterday = today - datetime.timedelta(days=1)
            start_time = datetime.datetime.combine(yesterday, datetime.time.min)
            end_time = datetime.datetime.combine(yesterday, datetime.time.max)

        # ... rest of the method ...