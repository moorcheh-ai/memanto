# Bug Report — Memanto Memory Management System

## Bug #1: Disabled Repetition Check Allows Duplicate Memories

**File:** `memanto/app/legacy/memory_validation_service.py:29`
**Severity:** High
**Category:** Memory Integrity

**Description:**
The repetition check is hardcoded to 0, bypassing the actual duplicate detection logic.

```python
# Line 27-29
# if not context.get("repetition_count"):
#     context["repetition_count"] = self._check_repetition(memory)
context["repetition_count"] = 0
```

The `_check_repetition()` method exists (lines 44-64) and uses similarity search to find duplicates, but it's never called. This means:
- Duplicate memories can be stored without detection
- The repetition threshold validation never triggers
- Memory inconsistency due to lack of deduplication

**Impact:** Users can store the same memory multiple times, leading to redundant context and potential confusion in AI agent behavior.

---

## Bug #2: Namespace Parsing Fails with Underscores in scope_id

**File:** `memanto/app/core.py:37-40`
**Severity:** High
**Category:** Data Corruption

**Description:**
The `from_namespace()` method splits by `_` and expects exactly 3 parts, but `scope_id` can contain underscores.

```python
def from_namespace(cls, namespace: str) -> "MemoryScope":
    parts = namespace.split("_")
    if len(parts) != 3 or parts[0] != "memanto":
        raise ValueError(f"Invalid MEMANTO namespace format: {namespace}")
    return cls(scope_type=cast(ScopeType, parts[1]), scope_id=parts[2])
```

**Example:**
- `to_namespace()` with scope_type="user" and scope_id="user_123" → `memanto_user_user_123`
- `from_namespace("memanto_user_user_123")` → splits to `["memanto", "user", "user", "123"]` → 4 parts → ValueError

**Impact:** Memory scopes with underscores in IDs cannot be round-tripped. This breaks any code that parses namespaces back to scopes.

---

## Bug #3: Validation Completely Skipped in Memory Storage

**File:** `memanto/app/services/memory_write_service.py:57-63, 151-160`
**Severity:** Critical
**Category:** Memory Integrity

**Description:**
The validation service is completely bypassed with a hardcoded result:

```python
# skip validation for speed
validation_result = {"action": "store", "reason": "MVP direct store"}
```

This appears in both `store_memory()` and `batch_store_memories()`. The actual validation service is never called, meaning:
- No quality checks on stored memories
- No duplicate detection
- No contradiction handling
- No confidence adjustment

**Impact:** The entire validation pipeline is non-functional. Low-quality, duplicate, or contradictory memories can be stored without any checks.

---

## Bug #4: Hardcoded Default Secret Key

**File:** `memanto/app/config.py:133`
**Severity:** Critical
**Category:** Security

**Description:**
The default secret key is hardcoded and predictable:

```python
MEMANTO_SECRET_KEY: str = "memanto-default-secret-change-in-production"
```

If users don't change this value (which is common in development/testing), sessions can be forged.

**Impact:** Attackers can forge session tokens, impersonate users, and access their memories.

---

## Bug #5: CORS Wildcard Allows Any Origin

**File:** `memanto/app/config.py:130`
**Severity:** High
**Category:** Security

**Description:**
The default CORS configuration allows any origin:

```python
ALLOWED_ORIGINS: list[str] = ["*"]
```

**Impact:** Any website can make requests to the Memanto API, potentially exfiltrating user memories through CSRF attacks.

---

## Bug #6: Config Exception Swallowing

**File:** `memanto/app/config.py:60-61`
**Severity:** Medium
**Category:** Reliability

**Description:**
Configuration loading errors are silently swallowed:

```python
except Exception:
    pass
```

This means:
- YAML parsing errors are hidden
- Invalid configuration values are silently ignored
- Debugging configuration issues is extremely difficult

**Impact:** Users may have misconfigured systems without any indication of the problem.
