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

## Finding 5: Deletion Success False Positive on Zero Deletions (Medium)

**File:** `memanto/app/services/memory_write_service.py`
**Method:** `_deletion_succeeded()`

When Moorcheh returns `{"status": "ok", "actual_deletions": 0}` — a valid response meaning "processed successfully but nothing matched" — the method returns `True` because the fallback checks `status == "ok"`. The caller interprets this as a successful deletion, but 0 documents were actually deleted.

**Impact:** Calling code that relies on `delete_memory()`'s return value for data-integrity decisions may incorrectly assume deletion succeeded.

**Suggested fix:** Check `actual_deletions` first as a required numeric field. Only fall through to `status`-based checking when `actual_deletions` is absent from the response.

---

## Finding 6: Search Offset Miscalculation When limit+offset Exceeds 100 (Medium)

**File:** `memanto/app/services/memory_read_service.py`
**Method:** `search_memories()`

The method implements offset by requesting `limit + offset` documents from Moorcheh, then locally slicing. However, Moorcheh's API enforces max 100 results per query.

When `limit + offset > 100`, e.g. `limit=90, offset=20`:
1. `requested_limit = 110`, but `top_k = 100`
2. Only 100 documents returned
3. Local slicing `all_results[20:110]` returns only 80 documents
4. `has_more` spuriously `False` (`100 > 110 = False`)

**Impact:** Callers paginating through search results will receive fewer results than requested and premature pagination termination.

**Suggested fix:** Implement true server-side offset or reject `offset + limit > 100` with a validation error.

---

## Finding 7: `utc_now()` Produces Naive vs `parse_iso_timestamp()` Produces Aware (Low)

**File:** `memanto/app/utils/temporal_helpers.py`

`utc_now()` returns naive datetime (no `tzinfo`), while `parse_iso_timestamp()` returns aware datetime. Functions like `search_changed_since()` compare the two, causing `TypeError: can't compare offset-naive and offset-aware datetimes`.

**Impact:** Temporal searches and differential queries break at runtime with `TypeError`.

**Suggested fix:** Make `utc_now()` return aware datetime (remove `.replace(tzinfo=None)`) or strip timezone from parsed timestamps. Pick one consistent convention.

---

## Updated Summary

| # | Finding | Severity | Type |
|---|---------|----------|------|
| 1 | Delete-then-recreate data loss | Critical | Architectural |
| 2 | Tz-aware/naive datetime inconsistency | Medium | Logic |
| 3 | Missing import timestamp validation | Medium | Validation |
| 4 | Batch partial failure — missing atomicity indicator | Low | Design |
| 5 | Deletion success false positive on zero deletions | Medium | Logic |
| 6 | Search offset miscalculation when limit+offset > 100 | Medium | Logic |
| 7 | `utc_now()` naive vs `parse_iso_timestamp()` aware | Low | Consistency |
