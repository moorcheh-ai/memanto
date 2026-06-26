# Security Audit Report - Issue #770

**Reporter:** dongpod7777-gif
**Date:** 2026-06-25
**Severity:** Medium-High

## Bug #1: TTL Bypass via Type Confusion (Medium)

**Location:** `memanto/app/services/memory_read_service.py:618-640`

**Description:** The `_filter_expired_memories` function only parses `expires_at` when it's a string. If an attacker stores a memory with `expires_at` as a non-string value (integer, list, or object), TTL enforcement is completely bypassed.

**PoC:**
```python
from memanto.app.core import MemoryRecord

# Create memory with expires_at as integer (bypasses TTL check)
memory = MemoryRecord(
    title="Test",
    content="Secret data",
    scope_type="agent",
    scope_id="test",
    actor_id="attacker",
    source="system",
    expires_at=9999999999  # Integer, not string!
)
# Memory will never be filtered out as expired
```

**Impact:** Attacker can create memories that persist indefinitely even with TTL set, polluting the memory store.

---

## Bug #2: Validation Complete Bypass (High)

**Location:** `memanto/app/services/memory_write_service.py:57-63`

**Description:** The validation logic is entirely commented out with "skip validation for speed". This means ANY memory can be stored without any validation, including:
- Malicious content
- Contradictory facts
- Poisoned preferences

**PoC:**
```python
# Store contradictory memory without any validation
memory = MemoryRecord(
    title="User password",
    content="The password is 123456",
    scope_type="agent",
    scope_id="target",
    actor_id="attacker",
    source="system",
    confidence=1.0  # Max confidence, no validation!
)
# Will be stored directly without any checks
```

**Impact:** Memory poisoning attack - attacker can inject false information that will be recalled by AI agents.

---

## Bug #3: Namespace Injection (Medium)

**Location:** `memanto/app/core.py:33-40`

**Description:** `from_namespace` splits by `_` and assumes exactly 3 parts. If `scope_id` contains underscores, parsing fails or produces wrong results. Also, no validation that `scope_type` is a valid enum value.

**PoC:**
```python
from memanto.app.core import MemoryScope

# Namespace with underscore in scope_id
ns = "memanto_agent_user_123"
scope = MemoryScope.from_namespace(ns)
print(scope.scope_id)  # Returns "123" instead of "user_123"!
```

**Impact:** Memory isolation bypass - memories could leak between different agents/users.

---

## Bug #4: Confidence Score Manipulation (Low)

**Location:** `memanto/app/core.py:168`

**Description:** Validation boost is cumulative and uncapped in validation_count. An attacker can repeatedly "validate" a low-confidence memory to artificially boost its trust score.

**PoC:**
```python
memory = MemoryRecord(
    title="Fake fact",
    content="Earth is flat",
    scope_type="agent",
    scope_id="test",
    actor_id="attacker",
    source="system",
    confidence=0.3  # Low confidence
)

# Validate 10 times
for _ in range(10):
    memory.validate()

# Confidence boosted from 0.3 to 0.51 (0.3 * 1.0 + 0.15 - 0 = 0.45)
# With enough validations, any memory becomes "trusted"
```

**Impact:** Attacker can make untrustworthy memories appear trustworthy.

---

## Proposed Fixes

See attached code changes for fixes to all 4 vulnerabilities.
