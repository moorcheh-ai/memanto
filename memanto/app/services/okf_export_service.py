import datetime
from datetime import timezone

class OkfExportService:
    # ... existing code ...

    def _parse_ts(self, ts):
        """Parse timestamp and ensure it's timezone-aware UTC datetime."""
        if ts is None or ts == "":
            return datetime.datetime.now(timezone.utc)

        if isinstance(ts, str):
            # Parse string to datetime, then ensure it's timezone-aware
            dt = datetime.datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        if isinstance(ts, datetime.datetime):
            if ts.tzinfo is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts

        raise ValueError(f"Unsupported timestamp type: {type(ts)}")

    def batch_store_memories(self, memories):
        """Store memories in batches and track results."""
        successful = 0
        rejected = 0
        failed = 0
        results = []

        for memory in memories:
            try:
                result = self._store_memory(memory)
                results.append(result)
            except Exception as e:
                results.append({"status": "error", "error": str(e)})

        # Count results in a single pass
        for r in results:
            status = str(r["status"]).lower()
            if status in SUCCESSFUL_UPLOAD_STATUSES:
                successful += 1
            elif status == "rejected":
                rejected += 1
            else:
                failed += 1
                r["status"] = "failed"

        return {
            "successful": successful,
            "rejected": rejected,
            "failed": failed,
            "results": results
        }

    # ... rest of the class ...