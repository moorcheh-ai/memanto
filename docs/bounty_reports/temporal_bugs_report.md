# Bug Report: Three Memory Integrity Flaws in Temporal Recall & Write Pipeline

**Severity:** High (Bugs 1 & 2) | Medium (Bug 3)  
**Scope:** `memanto/app/services/memory_read_service.py`, `memanto/app/services/memory_write_service.py`  
**Reporter:** mitchellecm7  
**Reproduction:** See `tests/failing_tests/test_temporal_bugs.py`

---

## Summary

Three distinct bugs were found by reading source code and exercising the temporal recall API (`recall/as-of`, `recall/changed-since`). Together they cause **silent data loss**, **incorrect point-in-time recall**, and **a hidden memory cap** that makes temporal queries unreliable for agents with > 100 stored memories.

---

## Bug 1 — Naive/Aware Datetime Comparison Crash in `search_as_of` and `search_changed_since`

### Severity: High — Silent Incorrect Results / Potential TypeError Crash

### Location
`memory_write_service.py` lines 39, 107, 284:
```python
now = datetime.utcnow()          # ← naive (no tzinfo)
memory.created_at = now          # stored as naive UTC
```

`memory_read_service.py` line 595:
```python
now = datetime.now(timezone.utc) # ← timezone-aware
```

`_apply_temporal_filter` and `search_as_of`:
```python
expires_dt = parse_iso_timestamp(expires_at)  # returns aware datetime
if expires_dt <= as_of_dt:                     # as_of_dt is also aware — OK
```

But `created_at` timestamps written by `store_memory()` are **naive UTC** (no `+00:00`), while `parse_iso_timestamp()` in `temporal_helpers.py` adds `tzinfo=timezone.utc` when missing. This means comparisons work — **except** when Moorcheh returns the timestamp without the `Z` suffix and `parse_iso_timestamp` path fails to add tzinfo, producing a naive datetime that is then compared to an aware one, raising:

```
TypeError: can't compare offset-naive and offset-aware datetimes
```

This error is silently swallowed by the `except (ValueError, AttributeError): pass` handlers in `_apply_temporal_filter`, causing memories to **pass through the temporal filter unfiltered** — returning memories outside the requested time window.

### Reproduction
```python
# tests/failing_tests/test_temporal_bugs.py — test_naive_aware_comparison
```

### Root Cause
`memory_write_service.py` uses `datetime.utcnow()` (naive) for `created_at`/`updated_at`. All temporal comparison code uses `datetime.now(timezone.utc)` (aware). The mismatch is masked by try/except, causing the filter to silently fail open.

### Fix
Replace all `datetime.utcnow()` in `memory_write_service.py` with `datetime.now(timezone.utc)`:

```python
# Before (lines 39, 107, 284):
now = datetime.utcnow()

# After:
now = datetime.now(timezone.utc)
```

Also add the import at the top of `memory_write_service.py`:
```python
from datetime import datetime, timezone
```

---

## Bug 2 — `search_as_of` Has No Semantic Query — Returns Random Memories, Not Relevant Ones

### Severity: High — Incorrect Recall Results (Timeline Amnesia)

### Location
`memory_read_service.py`, `search_as_of()`:

```python
def search_as_of(self, as_of_date, agent_id, type=None, tags=None, limit=10):
    ...
    all_memories = self._fetch_all_memories(namespaces, type=type, tags=tags)
    all_memories = self._apply_temporal_filter(all_memories, created_before=as_of_date)
    ...
    valid_memories = valid_memories[:limit]   # ← plain slice, no ranking
```

The `recall/as-of` endpoint accepts no `query` parameter. It fetches **all memories** created before `as_of`, applies expiry/supersession filters, then returns the first `limit` items in **arbitrary order** (whatever `fetch_text_data` returns).

Compare this to `search_changed_since`, which also has no query, and `recall` (the main endpoint), which takes a `query` and uses similarity search. The temporal endpoints silently degrade to unordered list truncation.

**Practical impact:** An agent asking "what did we know about the user's food preferences on 2025-11-01?" gets back the first 10 documents in storage order — not the 10 most relevant to the question. This is **timeline amnesia**: the system has the data but returns wrong memories.

The `RecallAsOfRequest` schema in `memory.py` also confirms no `query` field exists:
```python
class RecallAsOfRequest(BaseModel):
    as_of: datetime
    limit: int | None
    type: list[str] | None
    # ← no query field
```

### Reproduction
```python
# tests/failing_tests/test_temporal_bugs.py — test_as_of_no_query_field
```

### Proposed Fix
Add an optional `query` field to `RecallAsOfRequest` and `RecallChangedSinceRequest`, and use similarity search when provided:

```python
class RecallAsOfRequest(BaseModel):
    as_of: datetime
    query: str | None = Field(default=None, description="Optional semantic query to rank results")
    limit: int | None = Field(default=None, ge=1)
    type: list[str] | None = Field(default=None)
```

In `search_as_of`, after temporal filtering, apply similarity ranking if query is provided:
```python
if query:
    # Re-rank valid_memories by semantic similarity to query
    # using client.similarity_search or a local cosine rank
    ...
```

This would make `recall/as-of` consistent with `recall` in returning *relevant* memories at a point in time, not just *any* memories.

---

## Bug 3 — Silent 100-Memory Hard Cap on All Temporal Queries

### Severity: Medium — Data Loss for Large Agents

### Location
`memory_read_service.py`, `_fetch_all_memories()`:

```python
Note: Moorcheh's fetch_text_data currently returns up to 100 items per
namespace and does not paginate.
```

```python
result = self.client.documents.fetch_text_data(namespace_name=ns)
# ← returns at most 100 items, no pagination
```

Both `search_as_of` and `search_changed_since` use `_fetch_all_memories()` as their data source. This means:

1. An agent with 150 stored memories will have 50 memories silently excluded from all temporal queries.
2. There is no error, warning, or `has_more` flag in the response.
3. Which 50 are excluded depends on Moorcheh's internal ordering — typically oldest memories are dropped, meaning the agent's **earliest historical state is unqueryable**.

This directly contradicts the purpose of `recall/as-of` — you cannot reconstruct "what was true on day 1" if day 1's memories were silently dropped.

### Reproduction
```python
# tests/failing_tests/test_temporal_bugs.py — test_fetch_all_memories_cap
```

### Proposed Fix
Add a `truncated` flag and `total_available` count to temporal recall responses so callers know when results are incomplete:

```python
return {
    "results": valid_memories,
    "total_found": len(valid_memories),
    "as_of_date": as_of_date,
    "temporal_mode": "as_of",
    "truncated": len(all_memories_raw) >= 100,  # warn caller
    "fetch_limit": 100,
}
```

Longer term: implement pagination in `_fetch_all_memories` using Moorcheh's offset parameter once it becomes available, or use `similarity_search` with a broad query as a workaround.

---

## Impact Matrix

| Bug | Endpoint Affected | Production Impact |
|---|---|---|
| 1 — naive/aware mismatch | `recall/as-of`, `recall/changed-since`, `recall/recent` | Temporal filter silently fails open; expired/future memories returned |
| 2 — no query in as-of | `recall/as-of`, `recall/changed-since` | Returns arbitrary memories, not relevant ones; timeline amnesia |
| 3 — 100-item cap | `recall/as-of`, `recall/changed-since`, `recall/recent` | Silent data loss for agents with > 100 memories |

---

## Reproduction Environment

```
moorcheh-sdk==1.3.5
Python 3.11+
OS: Windows 11 / Ubuntu (both affected)
```

See `tests/failing_tests/test_temporal_bugs.py` for full reproducible test cases.
