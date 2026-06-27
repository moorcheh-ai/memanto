# Bug Report: Double `memanto` prefix in import path causes `search_multi_scope` to fail

## Summary

The `search_multi_scope` method in `MemoryReadService` contains an incorrect import path (`from memanto.memanto.app.constants import ScopeType`) that will raise `ModuleNotFoundError` at runtime whenever a user searches across multiple scopes.

## Affected File

`memanto/app/services/memory_read_service.py`, line 178

## Severity

**High** — The `search_multi_scope` method is completely broken. Any call to multi-scope search will crash with `ModuleNotFoundError: No module named 'memanto.memanto'` before any results are returned.

## Reproduction

```python
# minimal_repro.py
"""
Reproduction script for memanto search_multi_scope import bug.

Prerequisites:
    pip install memanto

Expected behavior:
    search_multi_scope should work (or fail with a network/auth error,
    not an import error).

Actual behavior:
    ModuleNotFoundError: No module named 'memanto.memanto'
"""
from memanto.app.services.memory_read_service import MemoryReadService

# We don't need a real Moorcheh client to trigger the bug —
# the import error happens before any network call.
class FakeClient:
    similarity_search = None

service = MemoryReadService(FakeClient())

try:
    result = service.search_multi_scope(
        query="test",
        scopes=[
            {"scope_type": "user", "scope_id": "user1"},
            {"scope_type": "agent", "scope_id": "agent1"},
        ],
    )
    print("Result:", result)
except ModuleNotFoundError as e:
    print(f"BUG CONFIRMED: {e}")
    # Output: BUG CONFIRMED: No module named 'memanto.memanto'
except Exception as e:
    # If we get a different error (e.g. AttributeError for FakeClient),
    # the import bug is still present but masked
    if "memanto.memanto" in str(e):
        print(f"BUG CONFIRMED: {e}")
    else:
        print(f"Different error (import may be lazy): {type(e).__name__}: {e}")
```

## Root Cause

Line 178 of `memory_read_service.py`:

```python
# BROKEN — double 'memanto' prefix
from memanto.memanto.app.constants import ScopeType
```

The correct import (used elsewhere in the same file at lines 651 and 693) is:

```python
# CORRECT
from memanto.app.constants import ScopeType
```

This appears to be a copy-paste error. The same file uses the correct import path in two other places (`search_memories` at line 651 and `generate_answer` at line 693), confirming the correct path is `memanto.app.constants`.

## Fix

```diff
- from memanto.memanto.app.constants import ScopeType
+ from memanto.app.constants import ScopeType
```

## Impact

- Multi-scope search is a documented feature (the method has a full docstring)
- Any user calling `search_multi_scope` will hit this immediately
- The bug is deterministic — it fails 100% of the time, not a race condition
- No workaround exists without monkey-patching the import

## Additional Notes

The validation service is also commented out in `MemoryWriteService.store_memory()` (lines 57-62):

```python
# skip validation for speed
## Validate memory
# validation_result = self.validation_service.validate_memory(memory, context)
```

This means **all memory validation is disabled** — memories are stored without any integrity checks, contradiction detection, or poisoning prevention. The `ValidationPolicy` class exists in `core.py` but is never called. This is a significant security concern for production use.
