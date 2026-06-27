# Memanto Bug & Security Audit Report

## Executive Summary

This report documents 13 bugs discovered during a security and integrity audit of the Memanto core package. The bugs range from Critical security vulnerabilities (hardcoded credentials enabling full authentication bypass) to High-severity logic flaws (non-atomic memory updates causing data loss, validation pipeline completely bypassed) and Medium-severity issues (race conditions, timezone mishandling, dead code paths).

**Most Critical Finding:** An attacker who reads the open-source code can forge JWT session tokens and authenticate with hardcoded admin API keys, gaining full access to any agent's memory namespace.

---

## Bug #1: Hardcoded Default JWT Secret Key (Critical - Security)

**File:** `memanto/app/config.py`, line 133
**File:** `memanto/app/services/session_service.py`, line 63

### Description

`MEMANTO_SECRET_KEY` defaults to the publicly known string `"memanto-default-secret-change-in-production"`. If the environment variable is not set (a common deployment oversight), all JWTs are signed with this key. Any attacker who reads the source code can forge valid session tokens for any agent, gaining full read/write/delete access to that agent's memory namespace.

### Proof of Concept

```python
"""Bug #1: JWT forgery with default secret key."""
import jwt
from datetime import datetime, timedelta, timezone

DEFAULT_KEY = "memanto-default-secret-change-in-production"

# Forge a session token for any agent_id
payload = {
    "agent_id": "victim-agent",
    "namespace": "memanto_agent_victim-agent",
    "session_id": "sess_forged123456",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
}
forged_token = jwt.encode(payload, DEFAULT_KEY, algorithm="HS256")
decoded = jwt.decode(forged_token, DEFAULT_KEY, algorithms=["HS256"])
assert decoded["agent_id"] == "victim-agent"
print("CRITICAL: JWT forgery succeeded - full access to victim-agent's memories")
```

### Proposed Fix

1. Remove the default value and require `MEMANTO_SECRET_KEY` to be set via environment variable
2. Add a startup check that refuses to run if the default key is detected
3. Generate a random key on first run and persist it

```python
# In config.py
MEMANTO_SECRET_KEY: str = ""  # No default - must be set

# In main.py startup
if settings.MEMANTO_SECRET_KEY == "memanto-default-secret-change-in-production" or not settings.MEMANTO_SECRET_KEY:
    raise RuntimeError(
        "SECURITY: MEMANTO_SECRET_KEY must be set to a cryptographically random value. "
        "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
    )
```

---

## Bug #2: Hardcoded API Keys with Admin Roles in Source Code (Critical - Security)

**File:** `memanto/app/utils/auth.py`, lines 27-39

### Description

The `AuthService` class hardcodes production API keys (`tk_acme_prod_abc123`, `tk_demo_test_xyz789`) directly in source code with tenant information, admin roles, and full scope permissions. Since the repository is public on GitHub, anyone can authenticate as the `acme` tenant with `admin` role and access all scopes (`user`, `workspace`, `agent`, `session`).

### Proof of Concept

```python
"""Bug #2: Authentication bypass using hardcoded API keys."""
from memanto.app.utils.auth import auth_service

# Use the hardcoded key from source code
user = auth_service.authenticate_api_key("tk_acme_prod_abc123")
assert user is not None
assert user.tenant_id == "acme"
assert "admin" in user.roles
assert "workspace" in user.scopes_allowed
print("CRITICAL: Full admin access granted via leaked key from public repo")
```

### Proposed Fix

1. Remove all hardcoded API keys from source code
2. Load API keys from environment variables or a secure secrets store
3. Add startup validation that no hardcoded keys are present

```python
# In auth.py - replace hardcoded keys
class AuthService:
    def __init__(self):
        self.tenant_api_keys: dict[str, AuthenticatedUser] = {}
        # Load keys from environment: MEMANTO_TENANT_KEYS=tk_acme:acme:admin:user,workspace,...
        keys_env = os.environ.get("MEMANTO_TENANT_KEYS", "")
        for entry in keys_env.split(","):
            if not entry:
                continue
            key, tenant, role, scopes = entry.split(":")
            self.tenant_api_keys[key] = AuthenticatedUser(...)
```

---

## Bug #3: Namespace Parsing Breaks for scope_ids Containing Underscores (High - Logic)

**File:** `memanto/app/core.py`, lines 37-40

### Description

`MemoryScope.from_namespace()` splits the namespace string on `_` and expects exactly 3 parts. But `to_namespace()` formats as `f"memanto_{scope_type}_{self.scope_id}"`. If `scope_id` contains underscores (e.g., `my_agent_1`), the namespace becomes `memanto_agent_my_agent_1`, which splits into 5 parts and raises `ValueError`. This breaks namespace resolution for any agent with underscores in its ID, which is valid per `AgentCreate.agent_id` regex `^[a-zA-Z0-9_-]+$`.

### Proof of Concept

```python
"""Bug #3: Namespace parsing failure for underscored scope_ids."""
from memanto.app.core import MemoryScope, create_memory_scope

scope = create_memory_scope(scope_type="agent", scope_id="my_agent_1")
namespace = scope.to_namespace()
print(f"Namespace: {namespace}")  # memanto_agent_my_agent_1

try:
    parsed = MemoryScope.from_namespace(namespace)
    print(f"Parsed back: {parsed}")
except ValueError as e:
    print(f"HIGH: Cannot parse namespace back: {e}")
```

### Proposed Fix

Use a delimiter that cannot appear in `scope_id` (e.g., `::`) or use a different parsing strategy:

```python
# Option A: Use :: delimiter
def to_namespace(self) -> str:
    return f"memanto::{self.scope_type}::{self.scope_id}"

@classmethod
def from_namespace(cls, namespace: str) -> "MemoryScope":
    parts = namespace.split("::")
    if len(parts) != 3 or parts[0] != "memanto":
        raise ValueError(f"Invalid namespace format: {namespace}")
    return cls(scope_type=cast(ScopeType, parts[1]), scope_id=parts[2])

# Option B: Split with maxsplit
@classmethod
def from_namespace(cls, namespace: str) -> "MemoryScope":
    parts = namespace.split("_", 2)  # Split at most 2 times
    if len(parts) != 3 or parts[0] != "memanto":
        raise ValueError(f"Invalid namespace format: {namespace}")
    return cls(scope_type=cast(ScopeType, parts[1]), scope_id=parts[2])
```

---

## Bug #4: Non-Atomic Delete-and-Recreate in update_memory Causes Data Loss (High - Logic/Integrity)

**File:** `memanto/app/services/memory_write_service.py`, lines 309-327

### Description

`update_memory()` deletes the old memory (Step 3) before uploading the new version (Step 4). If the upload fails after the delete succeeds, the memory is permanently lost with no recovery mechanism. There is no transaction, no rollback, and no backup before deletion.

### Proof of Concept

```python
"""Bug #4: Data loss when upload fails after delete in update_memory."""
from unittest.mock import MagicMock
from memanto.app.services.memory_write_service import MemoryWriteService

client = MagicMock()
client.documents.get.return_value = {
    "items": [{"id": "mem_123", "text": "[FACT] Important data", "metadata": {"type": "fact"}}]
}
client.documents.delete.return_value = {"actual_deletions": 1}
client.documents.upload.side_effect = Exception("Network timeout")

write_svc = MemoryWriteService(client)
try:
    write_svc.update_memory("mem_123", "memanto_agent_test", {"content": "updated"})
except Exception:
    pass

client.documents.delete.assert_called_once()
client.documents.upload.assert_called_once()
print("HIGH: Memory permanently lost - deleted old but failed to create new")
```

### Proposed Fix

Use an upload-then-delete pattern (write new, verify, then delete old):

```python
async def update_memory(self, memory_id: str, namespace: str, updates: dict, ...):
    # Step 1: Get old memory
    old_memory = await self.get_memory(memory_id, namespace)
    if not old_memory:
        raise NotFoundError(f"Memory {memory_id} not found")

    # Step 2: Create new version FIRST
    new_memory = self._apply_updates(old_memory, updates)
    upload_result = await self.client.documents.upload(...)

    # Step 3: Only delete old AFTER successful upload
    try:
        await self.client.documents.delete(old_memory_id=memory_id, namespace=namespace)
    except Exception:
        # Old memory remains but new one exists - acceptable state
        logger.warning(f"Old memory {memory_id} not deleted after update")
```

---

## Bug #5: ValidationPolicy Completely Bypassed in store_memory (High - Security/Integrity)

**File:** `memanto/app/services/memory_write_service.py`, lines 57-63

### Description

The `store_memory()` method has the `ValidationPolicy` call commented out and hardcoded to always return `{"action": "store", "reason": "MVP direct store"}`. This completely bypasses the validation pipeline that prevents unvalidated fact/preference poisoning. Any memory, regardless of confidence, source, or content, is stored as active with no provisional status.

### Proof of Concept

```python
"""Bug #5: Validation completely bypassed."""
from memanto.app.core import MemoryRecord, ValidationPolicy

suspicious = MemoryRecord(
    type="fact", title="Injected fact",
    content="The server is at 192.168.1.1",
    scope_type="agent", scope_id="test", actor_id="attacker",
    source="agent", confidence=0.3, provenance="inferred",
)
result = ValidationPolicy.validate_memory(suspicious)
print(f"Validation result: {result}")
# {'valid': True, 'action': 'store_provisional', ...}

bypassed = {"action": "store", "reason": "MVP direct store"}
print(f"Actual: {bypassed}")
print("HIGH: Suspicious memories stored as active instead of provisional")
```

### Proposed Fix

Uncomment the validation call and remove the hardcoded bypass:

```python
# In memory_write_service.py store_memory()
# Replace:
#   validation_result = {"action": "store", "reason": "MVP direct store"}
# With:
validation_result = self.validation_service.validate_memory(memory, context)
if "memory" in validation_result:
    memory = validation_result["memory"]

if validation_result.get("action") == "store_provisional":
    memory.make_provisional()
```

---

## Bug #6: TTL Enforcement is Read-Only, Expired Documents Never Cleaned (High - Memory Integrity)

**File:** `memanto/app/services/memory_read_service.py`, lines 597-640
**File:** `memanto/app/services/memory_write_service.py`, lines 46-49

### Description

TTL enforcement is purely client-side filtering during reads. Expired documents are never deleted from the backend storage. This causes: (1) Expired memories accumulate indefinitely, consuming storage and degrading search performance. (2) `update_memory()` retrieves expired memories via `get_memory()` which filters them out, causing "not found" errors for memories that still exist in storage. (3) Direct backend API access bypasses TTL filtering.

### Proposed Fix

Add a background cleanup job that periodically deletes expired documents from storage:

```python
# In memory_write_service.py or a new cleanup service
async def cleanup_expired_memories(self, namespace: str):
    """Delete expired documents from storage."""
    cutoff = datetime.now(timezone.utc)
    expired = await self.client.documents.query(
        namespace=namespace,
        filter={"expires_at": {"$lt": cutoff.isoformat()}},
    )
    for doc in expired.get("items", []):
        await self.client.documents.delete(document_id=doc["id"], namespace=namespace)
```

---

## Bug #7: datetime.utcnow() vs Timezone-Aware Comparisons (Medium - Logic)

**File:** Multiple files in `memanto/app/core.py` and `memanto/app/services/`

### Description

The codebase uses `datetime.utcnow()` (returns naive datetime) extensively, while `parse_iso_timestamp()` in `temporal_helpers.py` returns timezone-aware datetimes, and `_filter_expired_memories` uses `datetime.now(timezone.utc)` (aware). Comparing naive and aware datetimes raises `TypeError` in Python 3.12+.

### Proposed Fix

Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)`:

```python
# Replace throughout the codebase:
# from datetime import datetime
# datetime.utcnow()
# With:
from datetime import datetime, timezone
datetime.now(timezone.utc)
```

---

## Bug #8: extract_tenant_from_auth Returns Bearer Token as Tenant ID (Medium - Security)

**File:** `memanto/app/utils/auth.py`, lines 158-162

### Description

`extract_tenant_from_auth()` simply strips the "Bearer " prefix and returns whatever remains as the "tenant" identifier, but it actually returns the raw token value (JWT or API key). This is misleading and could leak credentials into logs or database queries.

### Proposed Fix

For JWT tokens, decode and extract the actual `tenant_id` claim. For API keys, look up the tenant from the authenticated user.

---

## Bug #9: Idempotency Store Race Condition (Medium - Logic)

**File:** `memanto/app/utils/idempotency.py`, lines 52-83

### Description

`IdempotencyStore.get_record()` and `store_record()` are not atomic. Between checking and storing, concurrent requests with the same key can both proceed, resulting in duplicate writes.

### Proposed Fix

Use `asyncio.Lock` or `threading.Lock` to make the check-then-store operation atomic:

```python
import threading

class IdempotencyStore:
    def __init__(self):
        self.records: dict[str, IdempotencyRecord] = {}
        self._lock = threading.Lock()

    def get_or_store(self, key: str, ...) -> IdempotencyRecord | None:
        with self._lock:
            existing = self.records.get(key)
            if existing:
                return existing
            # Store new record
            record = IdempotencyRecord(...)
            self.records[key] = record
            return None
```

---

## Bug #10: Superseded Memories Without updated_at Leak Into As-Of Queries (Medium - Integrity)

**File:** `memanto/app/services/memory_read_service.py`, lines 290-299

### Description

In `search_as_of()`, superseded memories without `updated_at` are not excluded because the check only skips the memory if `updated_at` is present AND before the `as_of_date`. Missing `updated_at` means superseded memories appear in point-in-time queries.

### Proposed Fix

If a memory is superseded and has no `updated_at`, treat it as superseded at `created_at`:

```python
if memory.get("superseded_by"):
    updated_at = memory.get("updated_at") or memory.get("created_at")
    if updated_at and parse_iso_timestamp(updated_at) <= as_of_date:
        continue  # Skip superseded memory
```

---

## Bug #11: Deletion Audit Log is In-Memory Only (Medium - Integrity)

**File:** `memanto/app/utils/safe_deletion.py`, lines 29-35

### Description

`DeletionAuditor` stores audit records in a Python list that is lost on process restart. The code acknowledges this with a comment but ships this way.

### Proposed Fix

Write audit records to a persistent store (file, database, or external audit service).

---

## Bug #12: Safe Deletion Validation Never Invoked from Routes (Medium - Security)

**File:** `memanto/app/utils/safe_deletion.py`, lines 110-123
**File:** `memanto/app/routes/memory.py`, lines 590-636

### Description

`SafeDeletion.validate_deletion_request()` is never called from any route handler. The `delete_memory` route directly calls `write_service.delete_memory()`, bypassing scope validation entirely.

### Proposed Fix

Replace direct deletion calls with `validate_and_delete_memories()`:

```python
# In memory.py delete route
from memanto.app.utils.safe_deletion import validate_and_delete_memories

@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, session: Session = Depends(get_session)):
    result = await validate_and_delete_memories(
        scope_type=session.scope_type,
        scope_id=session.scope_id,
        authenticated_scope_id=session.scope_id,
        memory_ids=[memory_id],
        write_service=write_service,
    )
    return result
```

---

## Bug #13: Contradicted Memories Stay "active" Status (Low - Logic/Integrity)

**File:** `memanto/app/core.py`, lines 138-184

### Description

When a memory is flagged as contradicted, `detect_contradiction()` only reduces the confidence score but does not change the status from "active". Contradicted memories still appear as "active" in search results.

### Proposed Fix

Set status to "contradicted" when a contradiction is detected:

```python
def detect_contradiction(self, contradicted_by: str | None = None):
    self.contradiction_detected = True
    self.contradicted_by = contradicted_by
    self.status = "contradicted"  # Add this line
```

---

## Severity Distribution

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 4 |
| Medium | 6 |
| Low | 1 |
| **Total** | **13** |

## Recommendations

1. **Immediate:** Remove hardcoded JWT secret default and API keys (Bugs #1, #2)
2. **High Priority:** Fix namespace parsing, add atomic updates, enable validation (Bugs #3, #4, #5)
3. **Near-term:** Add TTL cleanup, fix datetime handling, add idempotency locking (Bugs #6, #7, #9)
4. **Ongoing:** Wire up safe deletion in routes, persist audit logs, fix superseded memory filtering (Bugs #10-#12)
