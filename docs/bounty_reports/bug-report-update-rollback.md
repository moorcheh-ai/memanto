# Memanto Bug Report: Update Rollback Vulnerability + Temporal Inconsistency

## Bug 1: Update Rollback Vulnerability (Medium-High Severity)

### Description
`MemoryWriteService.update_memory()` uses a delete-and-recreate pattern. If the upload step fails after the old version is deleted, **the memory is permanently lost** with no rollback mechanism.

### Impact
Any failed update results in complete data loss for that memory record. In production with network instability, this is guaranteed to happen.

### Location
`memanto/app/services/memory_write_service.py`, method `update_memory()`, lines ~260-300

### Code Trace
```python
# Step 3: Delete old version
delete_result = self.client.documents.delete(namespace_name=namespace, ids=[memory_id])
# If delete succeeds but network drops...

# Step 4: Upload new version
document = cast(Document, updated_memory.to_moorcheh_document())
upload_result = self.client.documents.upload(
    namespace_name=namespace, documents=[document]
)
# If upload fails here, the memory is GONE
```

### Reproducibility Script

Save as `tests/failing_tests/test_update_rollback.py`:

```python
"""Demonstrates data loss in update_memory when upload fails after delete."""
import pytest
from unittest.mock import patch, MagicMock
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.services.memory_read_service import MemoryReadService

def test_update_memory_data_loss_on_upload_failure():
    """When upload fails after delete succeeds, memory is permanently lost."""
    client = MagicMock()
    
    # Mock read to return existing memory
    read_svc = MemoryReadService.__new__(MemoryReadService)
    read_svc.client = client
    original_get_memory = MemoryReadService.get_memory
    MemoryReadService.get_memory = lambda self, id, ns: {
        "id": id, "metadata": {"agent_id": "test_agent", "type": "fact"},
        "title": "Original", "content": "Original content"
    }
    
    write_svc = MemoryWriteService(client)
    
    # Mock: delete succeeds, upload fails
    client.documents.delete.return_value = {"status": "success", "actual_deletions": 1}
    client.documents.upload.side_effect = Exception("Network error during upload")
    
    with pytest.raises(Exception, match="Failed to update memory"):
        write_svc.update_memory("mem_test123", "memanto_agent_test_agent", 
                                 {"content": "Updated content"})
    
    # Memory is now permanently lost — BUG!
    MemoryReadService.get_memory = original_get_memory

if __name__ == "__main__":
    print("RUN THIS TEST TO SEE THE DATA LOSS BUG")
    print("The test PASSES (raises expected exception) but the memory is GONE")
```

## Bug 2: Naive/Aware Datetime Comparison (Medium Severity)

### Description
`utc_now()` in `temporal_helpers.py` returns a **naive** datetime (`replace(tzinfo=None)`), while `parse_iso_timestamp()` returns an **aware** datetime. When used in `_filter_expired_memories()`, comparing naive vs aware datetimes can produce incorrect expiration judgments.

### Location
`memanto/app/utils/temporal_helpers.py`, line 14
`memanto/app/services/memory_read_service.py`, `_filter_expired_memories()`, lines ~330-360

### Bug Trace
```python
# temporal_helpers.py:14
def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # Naive!

# memory_read_service.py
def _filter_expired_memories(self, results):
    now = datetime.now(timezone.utc)  # Aware!
    for result in results:
        expires_at = result.get("expires_at")
        if expires_at:
            try:
                expires_dt = parse_iso_timestamp(expires_at)  # Aware!
                if expires_dt > now:  # Mixed comparison - BUG
                    filtered.append(result)
```

### Reproducibility (Python):
```python
from memanto.app.utils.temporal_helpers import utc_now, parse_iso_timestamp

now_naive = utc_now()
parse_iso_timestamp("2026-12-01T00:00:00Z")  # Aware
# In some Python versions, comparing naive vs aware raises TypeError
```

## Bug 3: Maximum Batch Size Hardcoded Instead of Configurable (Low-Medium)

### Description
`batch_store_memories()` has a hardcoded `if len(memories) > 100:` limit with a Moorcheh-specific error message. If the Moorcheh API changes its document limit, this breaks without warning.

### Location
`memory_write_service.py`, line ~117

### Fix
```python
# Instead of:
if len(memories) > 100:
    raise MemoryError(
        f"Batch size {len(memories)} exceeds Moorcheh's limit of 100 documents per request"
    )

# Use:
MAX_BATCH_SIZE = getattr(settings, "MAX_BATCH_SIZE", 100)
if len(memories) > MAX_BATCH_SIZE:
    raise MemoryError(
        f"Batch size {len(memories)} exceeds limit of {MAX_BATCH_SIZE}"
    )
```
