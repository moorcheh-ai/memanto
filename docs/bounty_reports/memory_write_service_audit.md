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

But `update_memory()` converts stored ISO strings to datetimes via `datetime.fromisoformat()`:
```python
updated_memory.created_at = datetime.fromisoformat(
    raw_created.replace("Z", "+00:00")
)
```

`datetime.fromisoformat()` preserves the input timezone information: Z-suffixed or offset-bearing strings produce aware datetimes, while offset-less ISO strings remain naive. This means the same code path can produce **both** naive and aware representations depending on input format, creating an inconsistent mix in the same field at runtime.

**Impact:** Any code path that compares timestamps from different sources may raise `TypeError: can't compare offset-naive and offset-aware datetimes`. This affects search filtering, TTL enforcement, and sorting operations.

**Suggested fix:** Always normalize to a consistent representation — either use `datetime.utcnow()` everywhere with naive datetimes, or use `datetime.now(timezone.utc)` everywhere with aware datetimes. Convertincoming stored values to match during deserialization.

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

**Suggested fix:** Add validation in `_apply_timestamps()` to reject or clamp imported timestamps that are unreasonably far from the current time or that violate the `created_at <= updated_at` invariant.

---

## Finding 4: Batch Operation Partial Failure — Missing Atomicity Indicator (Low)

**File:** `memanto/app/services/memory_write_service.py`
**Method:** `batch_store_memories()`

When a batch contains memories for different namespaces, the method rejects individual items but continues processing:
```python
elif namespace != first_namespace:
    results.append({"status": "failed", "action": "rejected", ...})
    continue
```

The method does return per-item statuses and success/failure counts, so callers **can** distinguish outcomes after the fact. The missing piece is the lack of an explicit **atomicity indicator** — a single boolean that tells the caller whether the batch completed with full atomicity (all succeeded or the entire batch was rejected). Without this, callers must manually inspect every result entry, making error-handling logic fragile when batches are large.

**Impact:** Code consuming `batch_store_memories()` may incorrectly assume 100% success when only a subset of items were stored.

**Suggested fix:** Add a top-level `"atomic": true/false` key to the return dict so callers can immediately detect partial failures without iterating results.

---

## Summary

| # | Finding | Severity | Type |
|---|---------|----------|------|
| 1 | Delete-then-recreate data loss | Critical | Architectural |
| 2 | Tz-aware/naive datetime inconsistency | Medium | Logic |
| 3 | Missing import timestamp validation | Medium | Validation |
| 4 | Batch partial failure — missing atomicity indicator | Low | Design |

