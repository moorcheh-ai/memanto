# Timeline Amnesia in `search_as_of` — Bug Report for Bounty #770

> **Severity**: Critical / High
> **Category**: Retrieval Quality & Accuracy · Architectural & Logic Flaws
> **Bounty**: [Memanto Bug & Exploit Challenge #770](https://github.com/moorcheh-ai/memanto/issues/770) ($100 USD)

## 1. Summary

`MemoryReadService.search_as_of` is a **point-in-time query** whose stated
purpose is *"What was true at this point in time?"*. To decide whether a
memory was already superseded at the requested `as_of_date`, it inspects the
memory's `updated_at` field.

The problem: `updated_at` is **shared by every mutating operation** on a
`MemoryRecord` — `validate()`, `detect_contradiction()`, `update_memory()`,
etc. — not just `mark_superseded()`. Any later call to those operations
"refreshes" `updated_at` to a much later timestamp, so `search_as_of` cannot
tell when the supersession actually happened.

The net effect is **timeline amnesia**: a memory that was superseded *before*
`as_of_date` can silently reappear in the result set, causing the agent to
recall a stale, already-replaced preference or fact as if it were still true
at that point in time.

This directly violates three of the bounty's in-scope targets:

- *Retrieval Quality & Accuracy* — fails to recall the correct version
- *Losing track of when an event occurred (timeline amnesia)*
- *Deeply flawed contradiction handling* — supersession is the system's
  primary contradiction-resolution mechanism

## 2. Root Cause

### 2.1 `search_as_of` uses `updated_at` to time supersession

`memanto/app/services/memory_read_service.py` (original code, lines 289-299):

```python
# Skip if superseded before as_of_date
if memory.get("superseded_by"):
    # Memory was superseded - check if supersession happened before as_of_date
    updated_at = memory.get("updated_at")
    if updated_at:
        try:
            updated_dt = parse_iso_timestamp(updated_at)
            if updated_dt <= as_of_dt:
                continue  # Already superseded at as_of_date
        except (ValueError, AttributeError):
            pass
```

### 2.2 `updated_at` is mutated by many unrelated operations

`memanto/app/core.py` — `MemoryRecord`:

| Method | Mutates `updated_at`? |
|--------|------------------------|
| `mark_superseded(id)` | ✅ |
| `validate()` | ✅ |
| `detect_contradiction()` | ✅ |
| `MemoryWriteService.update_memory()` | ✅ (sets `updated_at = datetime.utcnow()`) |

There is **no dedicated field** recording *when* the supersession happened —
the legacy `MemorySupersedeResponse` model has a `supersede_timestamp`, but
the core `MemoryRecord` does not, and `_mark_memory_superseded` in
`app/legacy/universal_services.py` is a no-op stub that only logs.

So the moment any of the four operations above runs *after* a supersession,
`updated_at` no longer reflects the supersession time, and `search_as_of`
becomes unreliable.

### 2.3 `validate()` / `detect_contradiction()` don't check `status`

Even worse, neither `validate()` nor `detect_contradiction()` guards against
operating on a memory whose `status == "superseded"`. A superseded memory is
already replaced by a newer version — validating it or flagging a
contradiction on it is semantically meaningless, yet both methods happily
bump `updated_at`, which is exactly what poisons `search_as_of`.

## 3. Reproducibility

A self-contained PoC is included at
[`docs/bounty_reports/poc_timeline_amnesia.py`](./poc_timeline_amnesia.py).
It requires only the `memanto` package importable (no Moorcheh API key, no
network) — the Moorcheh client is mocked.

### 3.1 Reproduction steps

```bash
cd <memanto repo root>
python docs/bounty_reports/poc_timeline_amnesia.py
```

### 3.2 Timeline used by the PoC

| Time | Event |
|------|-------|
| 2026-01-01 | Memory A created ("用户喜欢咖啡") |
| 2026-02-01 | Memory B created; A is superseded by B |
| 2026-03-01 | A is (mistakenly) `validate()`-d → `updated_at` refreshed to 2026-03-01 |
| Query | `search_as_of(as_of_date="2026-02-15")` |

### 3.3 Expected vs actual (pre-fix)

| | Expected | Actual (buggy) |
|---|----------|----------------|
| Result IDs | `["mem-B"]` | `["mem-A", "mem-B"]` |
| A present? | ❌ No (already superseded) | ✅ Yes (wrongly recalled) |

`search_as_of` returns the *already-replaced* preference A as if it were
still true at 2026-02-15 — even though A was superseded on 2026-02-01.

## 4. Impact

- **Incorrect point-in-time retrieval.** Agents consuming `search_as_of`
  will see superseded memories as if they were active, producing
  self-contradictory context ("the user likes coffee" and "the user likes
  tea" both returned for the same point in time).
- **Silent regression.** The bug only manifests when *any* post-supersession
  mutation happens — exactly the kind of long-tail edge case that survives
  testing and bites in production.
- **Contradiction-handling defeat.** Supersession is Memanto's primary
  contradiction-resolution primitive; if superseded memories leak back into
  point-in-time queries, the contradiction effectively re-appears.
- **Backwards compatibility.** The legacy `MemorySupersedeResponse` model
  already exposes `supersede_timestamp`, so the concept exists in the code
  base — it just never made it to the core `MemoryRecord`.

## 5. Fix

The fix is split across three files. The central idea: introduce a dedicated
`superseded_at` field that is set *only* by `mark_superseded()` and never
touched by `validate()` / `detect_contradiction()` / `update_memory()`.

### 5.1 `memanto/app/core.py`

1. New field on `MemoryRecord`:
   ```python
   superseded_at: datetime | None = None
   ```
2. `mark_superseded()` now sets `superseded_at = now` alongside `updated_at`.
3. `validate()` and `detect_contradiction()` early-return when
   `self.status == "superseded"` — no state change, no `updated_at` bump.
4. `to_moorcheh_document()` emits `superseded_at` so the field round-trips
   through Moorcheh storage.

### 5.2 `memanto/app/services/memory_read_service.py`

1. `search_as_of` now reads `superseded_at` first, falling back to
   `updated_at` only for legacy data that predates the field:
   ```python
   supersede_ts = memory.get("superseded_at") or memory.get("updated_at")
   ```
   This keeps existing stored memories working unchanged.
2. `_format_memory_item` extracts `superseded_at` into the formatted dict so
   downstream consumers (including `search_as_of`) can see it.

### 5.3 `memanto/app/services/memory_write_service.py`

`update_memory()` now preserves `superseded_by`, `supersedes`, and
`superseded_at` from the existing memory (unless explicitly overridden in
`updates`). Previously the reconstructed `MemoryRecord` dropped these fields,
which would have made a superseded memory look active again after an edit.

### 5.4 Verification

`python docs/bounty_reports/poc_timeline_amnesia.py` now exits 0:

```
[场景 2] 修复后（有 superseded_at=2026-02-01）—— 验证 bug 已修复
  search_as_of 返回: ['mem-B-fixed']
  [OK] 记忆 A 被正确排除！superseded_at=2026-02-01 <= as_of=2026-02-15
  即使 updated_at=2026-03-01 被污染，search_as_of 仍用 superseded_at 判断。

[场景 3] 验证 MemoryRecord.mark_superseded 正确设置 superseded_at
  [OK] superseded_at 字段已正确设置

[场景 4] 验证 validate/detect_contradiction 不操作 superseded memory
  [OK] updated_at 未被污染（validate/detect_contradiction 被正确跳过）
```

A pytest-based regression test is also included at
`tests/failing_tests/test_timeline_amnesia.py`.

## 6. Backwards Compatibility

- **Old stored memories** (no `superseded_at` field): `search_as_of` falls
  back to `updated_at`, so behavior is unchanged from before this fix —
  these memories continue to work, they just don't get the new protection
  until they are re-superseded.
- **No schema migration required**: `superseded_at` is an optional field;
  existing Moorcheh documents are not touched.
- **No API change**: no endpoint signature is modified; `superseded_at` is
  surfaced in response payloads only when present.

## 7. Files Changed

| File | Change |
|------|--------|
| `memanto/app/core.py` | New `superseded_at` field; `mark_superseded` sets it; `validate` / `detect_contradiction` skip superseded memories; `to_moorcheh_document` emits it |
| `memanto/app/services/memory_read_service.py` | `search_as_of` prefers `superseded_at`; `_format_memory_item` extracts it |
| `memanto/app/services/memory_write_service.py` | `update_memory` preserves `superseded_at` / `superseded_by` / `supersedes` |
| `tests/failing_tests/test_timeline_amnesia.py` | Regression test (was failing pre-fix, passes post-fix) |
| `docs/bounty_reports/poc_timeline_amnesia.py` | Self-contained PoC |
| `docs/bounty_reports/timeline_amnesia_supersession.md` | This report |
