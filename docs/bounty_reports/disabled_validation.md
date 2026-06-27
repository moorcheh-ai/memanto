# Bug Report: Memory validation completely disabled — all memories stored without integrity checks

## Summary

The `MemoryWriteService` has all memory validation commented out in both `store_memory()` and `batch_store_memories()`. The `ValidationPolicy` class exists in `core.py` but is never called. This means **all memories are stored without any integrity checks, contradiction detection, or poisoning prevention**.

## Affected Files

- `memanto/app/services/memory_write_service.py` — lines 57-63 and 151-160
- `memanto/app/core.py` — `ValidationPolicy` class exists but is never invoked

## Severity

**High** — Memory integrity is a core security concern. Without validation:
- Contradictory memories can be stored without detection
- Memory poisoning attacks are possible (malicious content stored as "validated")
- The `compute_confidence()` and `trust_score()` methods in `MemoryRecord` are rendered meaningless because `validation_count` is always 0
- The `provenance` field never upgrades from "inferred" to "validated"

## Root Cause

Lines 57-63 of `memory_write_service.py`:
```python
# skip validation for speed
## Validate memory
# validation_result = self.validation_service.validate_memory(memory, context)
## Use validated memory if modified
# if "memory" in validation_result:
#     memory = validation_result["memory"]
validation_result = {"action": "store", "reason": "MVP direct store"}
```

The same pattern is repeated in `batch_store_memories()` at lines 151-160.

Additionally, in `memory_read_service.py` lines 851-884, the trust score computation is also commented out:
```python
# skip trust score computation reconstructs MemoryRecord and runs compute_confidence() + trust_score() per result. Skipped for speed.
```

This means `computed_confidence` and `trust_score` are never populated in search results, making it impossible for consumers to distinguish high-trust memories from low-trust ones.

## Reproduction

```python
from memanto.app.services.memory_write_service import MemoryWriteService

# Any memory is stored without validation, regardless of content
# The validation_service exists but is never called
# Contradictory memories can coexist without detection
```

## Impact

1. **Security**: Memory poisoning — an attacker can inject false memories that are stored with the same trust level as validated ones
2. **Integrity**: Contradictory memories coexist without detection — the `contradiction_detected` field is never set
3. **Trust**: `compute_confidence()` returns incorrect values because `validation_count` is always 0
4. **Retrieval quality**: Search results lack `computed_confidence` and `trust_score`, so consumers cannot filter by trust

## Proposed Fix

### Option A: Re-enable validation (recommended)
Uncomment the validation calls in both `store_memory()` and `batch_store_memories()`, and ensure `self.validation_service` is properly initialized.

### Option B: Make validation configurable
Add a `VALIDATION_ENABLED` setting (already exists in config as `AUTO_PARSE_ENABLED` pattern) that defaults to `True` in production and `False` only in development/benchmarking.

### Trust score computation
Re-enable the trust score computation in `_format_memory_item()` or move it to a lazy property that's only computed when accessed.
