# Bug Report: Memory Write Service — Data Integrity & Architectural Issues

## Bounty: $100 — Memanto Bug & Exploit Challenge

---

## Finding 1: Non-Atomic Update Causes Silent Data Loss (Critical)

**File:** `memanto/app/services/memory_write_service.py`
**Method:** `update_memory()`

The update follows a delete-then-recreate pattern:
1. Step 3: Delete old version (`self.client.documents.delete()`)
2. Step 4: Upload new version (`self.client.documents.upload()`)

If Step 4 fails (network error, server timeout, validation failure, quota exceeded), the memory is permanently **destroyed**. No rollback, no backup, no error recovery path exists. The caller receives a `MemoryError` but the data is already gone.

**Impact:** Any memory update operation risks irreversible data loss under normal failure conditions.

**Suggested fix:** Change to create-then-delete: upload the new version first (with a temporary or versioned ID), then delete the old version only after confirming success. Or implement a soft-delete with a TTL-based cleanup.

---

## Finding 2: Naive vs Timezone-Aware Datetime Inconsistency (Medium)

**File:** `memanto/app/core.py`, `memanto/app/services/memory_write_service.py`

`MemoryRecord.created_at` uses `datetime.utcnow()` (naive datetime) as default:
```python
created_at: datetime = Field(default_factory=datetime.utcnow)
```

But `update_memory()` converts stored ISO strings to aware datetimes:
```python
updated_memory.created_at = datetime.fromisoformat(
    raw_created.replace("Z", "+00:00")
)
```

This creates an inconsistent mix of naive and aware datetimes in the same field. Comparison operations like `created_at < now` will raise `TypeError: can't compare offset-naive and offset-aware datetimes`.

**Impact:** Any code path that compares timestamps from different sources can crash at runtime. This affects search, filtering, TTL enforcement, and sorting operations.

---

## Finding 3: Missing Timestamp Validation for Imported Memories (Medium)

**File:** `memanto/app/services/memory_write_service.py`
**Method:** `_apply_timestamps()`

For imported provenance memories, `_apply_timestamps()` merely naive-converts the existing timestamps without any sanity checks:
```python
if memory.provenance == "imported":
    memory.created_at = as_utc_naive(memory.created_at)
    memory.updated_at = as_utc_naive(memory.updated_at)
    return
```

A memory could be imported with timestamps in the far future (year 3000), the far past (year 1970), or with `created_at > updated_at`. None of these are validated.

**Impact:** Corrupted timeline data that can affect retrieval ordering and TTL calculations.

---

## Finding 4: Batch Operation Partial Failure Ambiguity (Low-Medium)

**File:** `memanto/app/services/memory_write_service.py`
**Method:** `batch_store_memories()`

When a batch contains memories for different namespaces, the method rejects individual items but continues processing:
```python
elif namespace != first_namespace:
    results.append({"status": "failed", "action": "rejected", ...})
    continue
```

However, the method also uploads the remaining items to Moorcheh in a single API call. The caller has no way to distinguish between "all succeeded", "some succeeded", or "all failed" without manually checking each result entry. Critical error handling logic may incorrectly assume operation was atomic.

---

## Summary

| # | Finding | Severity | Type |
|---|---------|----------|------|
| 1 | Delete-then-recreate data loss | Critical | Architectural |
| 2 | Tz-aware/naive datetime mismatch | Medium | Logic |
| 3 | Missing import timestamp validation | Medium | Validation |
| 4 | Partial batch failure ambiguity | Low | Design |

