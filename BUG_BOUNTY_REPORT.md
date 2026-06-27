# 🐛 Memanto Bug Bounty Report — Logic Flaws, Memory Integrity & Contradiction Handling

**Analyst:** Bug Bounty Subagent  
**Date:** 2026-06-27  
**Scope:** Core services (`memory_write_service`, `memory_read_service`, `memory_parsing_service`, `conversation_memory_extraction_service`, `agent_service`, `session_service`, `namespace_service`, `temporal_helpers`, `core.py`, models)

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 3 |
| High | 7 |
| Medium | 5 |
| **Total** | **15** |

---

## BUG-01: Non-Atomic `update_memory` Causes Permanent Data Loss on Failure

**File:** `memanto/app/services/memory_write_service.py`, lines 146–210  
**Severity:** 🔴 Critical

### Description

`update_memory()` uses a **delete-then-recreate** pattern:

```python
# Step 3: Delete old version
delete_result = self.client.documents.delete(
    namespace_name=namespace, ids=[memory_id]
)

# Step 4: Upload new version
document = cast(Document, updated_memory.to_moorcheh_document())
upload_result = self.client.documents.upload(
    namespace_name=namespace, documents=[document]
)
```

If Step 4 fails (network error, Moorcheh outage, malformed document, timeout), the old memory has **already been deleted** in Step 3. There is no rollback. The memory is **permanently lost** with no recovery path.

### Reproduction

```python
from unittest.mock import MagicMock, patch
from memanto.app.core import MemoryRecord
from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.services.memory_read_service import MemoryReadService

client = MagicMock()
# Setup: get_memory returns existing memory
read_svc = MemoryReadService(client)
client.documents.get.return_value = {"items": [{"id": "mem_001", "text": "[FACT] Test", "metadata": {"type": "fact", "scope_type": "agent", "scope_id": "a1", "confidence": 0.9, "status": "active", "created_at": "2026-01-01T00:00:00Z"}}]}

# Delete succeeds
client.documents.delete.return_value = {"actual_deletions": 1}
# Upload fails
client.documents.upload.side_effect = Exception("Network timeout")

write_svc = MemoryWriteService(client)
try:
    write_svc.update_memory("mem_001", "memanto_agent_a1", {"content": "updated"})
except Exception as e:
    print(f"Error: {e}")
    # Memory is now DELETED with no replacement — DATA LOSS
```

### Suggested Fix

Upload the new version **first**, then delete the old version. Or use a temporary ID:

```python
# Step 1: Upload new version with temp ID
temp_id = f"{memory_id}_v_new"
updated_memory.id = temp_id
client.documents.upload(namespace_name=namespace, documents=[new_document])

# Step 2: Delete old version
client.documents.delete(namespace_name=namespace, ids=[memory_id])

# Step 3: Re-upload with canonical ID
updated_memory.id = memory_id
client.documents.upload(namespace_name=namespace, documents=[final_document])
client.documents.delete(namespace_name=namespace, ids=[temp_id])
```

---

## BUG-02: `update_memory` Erases Provenance, Validation History, and Trust Fields

**File:** `memanto/app/services/memory_write_service.py`, lines 166–190  
**Severity:** 🔴 Critical

### Description

When reconstructing the `MemoryRecord` during `update_memory()`, the following fields are **NOT carried over** from the original memory and silently reset to defaults:

| Field | Original Value | After Update (default) |
|-------|---------------|----------------------|
| `provenance` | `"validated"` | `"explicit_statement"` |
| `validation_count` | `5` | `0` |
| `contradiction_detected` | `True` | `False` |
| `validated_at` | `2026-06-01T...` | `None` |
| `superseded_by` | `"mem_009"` | `None` |
| `supersedes` | `"mem_003"` | `None` |

The `MemoryRecord` constructor in `update_memory` omits these fields entirely:

```python
updated_memory = MemoryRecord(
    id=memory_id,
    type=updates.get("type", metadata.get("type", "fact")),
    title=updates.get("title", ...),
    content=updates.get("content", ...),
    scope_type=metadata.get("scope_type", "agent"),
    scope_id=metadata.get("scope_id", "unknown"),
    actor_id=updates.get("actor_id", metadata.get("actor_id", "unknown")),
    source=updates.get("source", metadata.get("source", "system")),
    confidence=updates.get("confidence", metadata.get("confidence", 0.8)),
    status=updates.get("status", metadata.get("status", "active")),
    tags=updates.get("tags", metadata.get("tags", [])),
    # ⚠️ MISSING: provenance, validation_count, contradiction_detected,
    #    validated_at, superseded_by, supersedes
)
```

This means **any edit to a memory silently destroys its trust history**. A memory that was validated 10 times and had `contradiction_detected=True` becomes a clean, unvalidated, non-contradicted memory after a trivial title edit.

### Reproduction

```python
# Store a memory, validate it multiple times, flag a contradiction
memory = MemoryRecord(
    type="fact", title="DB Choice", content="We use PostgreSQL",
    scope_type="agent", scope_id="a1", actor_id="a1", source="user",
    provenance="validated", validation_count=5,
    contradiction_detected=True,
    validated_at=datetime(2026, 6, 1)
)
write_svc.store_memory(memory)

# Now edit just the title
write_svc.update_memory(memory.id, "memanto_agent_a1", {"title": "Database Choice"})

# Read it back — provenance is "explicit_statement", validation_count=0,
# contradiction_detected=False, validated_at=None
result = read_svc.get_memory(memory.id, "memanto_agent_a1")
# Trust history is GONE
```

### Suggested Fix

```python
updated_memory = MemoryRecord(
    # ... existing fields ...
    provenance=metadata.get("provenance", "explicit_statement"),
    validation_count=metadata.get("validation_count", 0),
    contradiction_detected=metadata.get("contradiction_detected", False),
    validated_at=metadata.get("validated_at"),
    superseded_by=metadata.get("superseded_by"),
    supersedes=metadata.get("supersedes"),
)
```

---

## BUG-03: `search_as_of` Suffers Temporal Amnesia — Cannot See Memories That Have Since Expired

**File:** `memanto/app/services/memory_read_service.py`, lines 226–270 (`search_as_of`)  
and lines 397–413 (`_fetch_all_memories`)  
**Severity:** 🔴 Critical

### Description

`search_as_of` is documented as *"What was true at this point in time?"* It should return memories that were alive at the `as_of_date`. However:

1. `_fetch_all_memories()` calls `_filter_expired_memories()` which uses `datetime.now(timezone.utc)` to filter out **currently expired** memories.
2. Then `search_as_of` checks if memories were expired **at `as_of_date`**.

The problem: A memory that was **alive at `as_of_date`** but has **since expired** is already filtered out by `_filter_expired_memories()` inside `_fetch_all_memories()`. The as-of check never gets to see it.

```python
def _fetch_all_memories(self, ...):
    ...
    return self._filter_expired_memories(memories)  # ← removes currently-expired

def search_as_of(self, as_of_date, ...):
    all_memories = self._fetch_all_memories(...)  # ← already filtered!
    for memory in all_memories:
        expires_at = memory.get("expires_at")
        if expires_at:
            expires_dt = parse_iso_timestamp(expires_at)
            if expires_dt <= as_of_dt:
                continue  # ← This check never runs for already-filtered memories
```

### Impact

Point-in-time queries return **incomplete history**. An agent asking "what did I know on June 1st?" will not see memories that were valid on June 1st but expired by today. This defeats the entire purpose of temporal recall.

### Reproduction

```python
from datetime import datetime, timezone, timedelta
from memanto.app.core import MemoryRecord

# Store a memory with 1-hour TTL
memory = MemoryRecord(
    type="fact", title="Server Status", content="Deploy succeeded",
    scope_type="agent", scope_id="a1", actor_id="a1", source="system",
)
memory.set_ttl(3600)  # Expires in 1 hour
write_svc.store_memory(memory)

# Wait for it to expire (or mock datetime)
# Now query "what was true 30 minutes ago?" (when memory was still alive)
result = read_svc.search_as_of(
    as_of_date=(datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
    agent_id="a1"
)
# result["results"] is EMPTY — the expired memory is gone from the store
# The agent has amnesia about the deploy that it knew about 30 minutes ago
```

### Suggested Fix

`search_as_of` should bypass the current-expiry filter and apply its own temporal logic:

```python
def search_as_of(self, ...):
    # Fetch WITHOUT TTL filtering
    all_memories = self._fetch_all_memories_raw(namespaces, type=type, tags=tags)
    # Then apply the as-of temporal filter (which checks expiry at as_of_date)
    ...
```

---

## BUG-04: No Contradiction Detection at Write Time — Contradictory Facts Coexist Silently

**File:** `memanto/app/services/memory_write_service.py`, lines 48–52  
**Severity:** 🟠 High

### Description

The README claims "No writeback — contradictions silently coexist" as Gap #5 that Memanto solves. However, `store_memory()` **explicitly skips all validation**:

```python
# skip validation for speed
## Validate memory
# validation_result = self.validation_service.validate_memory(memory, context)
validation_result = {"action": "store", "reason": "MVP direct store"}
```

There is no real-time contradiction check. Two diametrically opposed facts can be stored without any warning:

- "User's favorite language is Python" (confidence=0.9)
- "User's favorite language is Rust" (confidence=0.9)

Both are stored successfully and both appear in search results. The `contradiction_detected` field is never set during storage. The only contradiction detection mechanism is the **daily batch analysis** (`generate_conflict_report`), which:
1. Requires manual or scheduled invocation
2. Uses an LLM (imperfect, may miss contradictions)
3. Only runs against session MD files, not the live memory store

### Reproduction

```python
# Store contradictory facts
m1 = MemoryRecord(type="fact", title="DB", content="We use PostgreSQL",
    scope_type="agent", scope_id="a1", actor_id="a1", source="user", confidence=0.9)
m2 = MemoryRecord(type="fact", title="DB", content="We migrated to MongoDB",
    scope_type="agent", scope_id="a1", actor_id="a1", source="user", confidence=0.9)

write_svc.store_memory(m1)
write_svc.store_memory(m2)  # No warning, no contradiction flag

# Both coexist silently in search results
result = read_svc.search_memories("database", scope_type="agent", scope_id="a1")
# len(result["results"]) == 2, both active, no contradiction_detected=True
```

### Suggested Fix

Implement a semantic similarity check at write time. Before storing, search for similar content in the same namespace. If a high-similarity match is found with contradictory content, either:
- Flag both memories with `contradiction_detected=True`
- Mark the newer one as `provisional` pending resolution
- At minimum, log a warning

---

## BUG-05: `compute_confidence()` Crashes on Timezone-Aware `created_at`

**File:** `memanto/app/core.py`, line 172  
**Severity:** 🟠 High

### Description

```python
def compute_confidence(self) -> float:
    ...
    if self.type in ["preference", "observation"]:
        age_days = (datetime.utcnow() - self.created_at).days  # ← CRASH
```

`datetime.utcnow()` returns a **timezone-naive** datetime. But `created_at` can be **timezone-aware** after `update_memory()` parses it:

```python
# In update_memory():
updated_memory.created_at = datetime.fromisoformat(
    raw_created.replace("Z", "+00:00")
)
# → Produces aware datetime (e.g., datetime(2026, 1, 1, tzinfo=timezone.utc))
```

When `compute_confidence()` subtracts an aware datetime from a naive one, Python raises:

```
TypeError: can't subtract offset-naive and offset-aware datetimes
```

This crashes any code path that calls `compute_confidence()` or `trust_score()` on a memory that was updated via `update_memory()`.

### Reproduction

```python
from datetime import datetime, timezone
from memanto.app.core import MemoryRecord

m = MemoryRecord(
    type="preference", title="Test", content="prefers dark mode",
    scope_type="agent", scope_id="a1", actor_id="a1", source="user",
)
# Simulate what update_memory does:
m.created_at = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
m.compute_confidence()  # TypeError: can't subtract offset-naive and offset-aware datetimes
```

### Suggested Fix

Use timezone-aware UTC consistently throughout the codebase:

```python
# In core.py
from memanto.app.utils.temporal_helpers import utc_now

def compute_confidence(self) -> float:
    ...
    age_days = (utc_now() - self.created_at).days
```

Or normalize `created_at` to naive when parsing:
```python
updated_memory.created_at = datetime.fromisoformat(
    raw_created.replace("Z", "+00:00")
).replace(tzinfo=None)
```

---

## BUG-06: `_fetch_all_memories` Does Not Filter by Status — Superseded Memories Leak Into Results

**File:** `memanto/app/services/memory_read_service.py`, lines 397–430  
**Severity:** 🟠 High

### Description

`_fetch_all_memories()` filters by `type` and `tags` but **never filters by `status`**:

```python
def _fetch_all_memories(self, namespaces, type=None, tags=None):
    ...
    for item in items:
        ...
        if type and formatted.get("type") not in type:
            continue
        if tags:
            ...
        memories.append(formatted)
    return self._filter_expired_memories(memories)
```

This method feeds `search_as_of`, `search_changed_since`, and `search_recent`. Superseded memories (status="superseded") appear alongside active memories in all these queries.

### Impact

- `search_recent` returns old, superseded memories as if they were current
- `search_as_of` returns superseded memories that should have been excluded  
- Agents see stale, replaced information as if it's still valid

### Reproduction

```python
# Store memory, then supersede it
m1 = MemoryRecord(type="fact", title="Version", content="Running v1.0",
    scope_type="agent", scope_id="a1", actor_id="a1", source="system")
write_svc.store_memory(m1)

m1.mark_superseded("mem_new_version")
# Now search recent — m1 still appears even though it's superseded
result = read_svc.search_recent(agent_id="a1")
# Superseded memory is in results!
```

### Suggested Fix

```python
# In _fetch_all_memories, add status filtering:
if formatted.get("status") == "superseded":
    continue
```

---

## BUG-07: Namespace Isolation Failure — `search_memories` Without Scope Searches ALL Agents

**File:** `memanto/app/services/memory_read_service.py`, `_get_search_namespaces()`  
**Severity:** 🟠 High

### Description

```python
def _get_search_namespaces(self, scope_type=None, scope_id=None):
    if scope_type and scope_id:
        scope = create_memory_scope(scope_type, scope_id)
        return [scope.to_namespace()]
    else:
        # Search all namespaces
        return self.namespace_service.list_namespaces()
```

If a caller omits `scope_type`/`scope_id` (or passes `None`), the search fans out to **every agent's namespace** in the system. While the REST API routes always pass the scope, any direct service caller (SDK, CLI, internal service) can trigger cross-agent data leakage.

### Reproduction

```python
# Agent A stores private info
m = MemoryRecord(type="fact", title="SSN", content="123-45-6789",
    scope_type="agent", scope_id="agentA", actor_id="agentA", source="user")
write_svc.store_memory(m)

# Agent B searches without scope — gets Agent A's memories!
result = read_svc.search_memories("social security")
# Returns Agent A's private memory
```

### Suggested Fix

Make scope parameters required, or fail closed:

```python
def _get_search_namespaces(self, scope_type=None, scope_id=None):
    if not scope_type or not scope_id:
        raise ValueError("scope_type and scope_id are required for security isolation")
    ...
```

---

## BUG-08: `MemoryScope.from_namespace()` Fails on Scope IDs Containing Underscores

**File:** `memanto/app/core.py`, `MemoryScope.from_namespace()`  
**Severity:** 🟠 High

### Description

```python
@classmethod
def from_namespace(cls, namespace: str) -> "MemoryScope":
    parts = namespace.split("_")
    if len(parts) != 3 or parts[0] != "memanto":
        raise ValueError(f"Invalid MEMANTO namespace format: {namespace}")
    return cls(scope_type=parts[1], scope_id=parts[2])
```

The `split("_")` breaks if `scope_id` contains underscores. Example:

- Namespace: `memanto_agent_my_agent`  
- `split("_")` → `["memanto", "agent", "my", "agent"]` (4 parts)
- Raises `ValueError: Invalid MEMANTO namespace format`

Meanwhile, `validate_namespace_format()` allows underscores in scope IDs:
```python
pattern = r"^memanto_(user|workspace|agent|session)_[a-zA-Z0-9_-]+$"
```

And `AgentCreate` allows underscores: `pattern=r"^[a-zA-Z0-9_-]+$"`

### Reproduction

```python
from memanto.app.core import create_memory_scope, MemoryScope

scope = create_memory_scope("agent", "my_agent_123")
ns = scope.to_namespace()  # "memanto_agent_my_agent_123"
# Now try to parse it back:
MemoryScope.from_namespace(ns)  # ValueError!
```

### Suggested Fix

Use `split("_", 2)` to limit splitting:

```python
parts = namespace.split("_", 2)
if len(parts) != 3 or parts[0] != "memanto":
    raise ValueError(...)
return cls(scope_type=parts[1], scope_id=parts[2])
```

---

## BUG-09: Confidence Metadata Filter Never Matches — Stored as Float, Filtered as String Label

**File:** `memanto/app/services/memory_read_service.py`, `_build_filtered_query()`  
**Severity:** 🟠 High

### Description

The confidence filter builds Moorcheh metadata syntax using categorical labels:

```python
if min_confidence is not None:
    if min_confidence >= 0.8:
        filter_parts.append("#confidence:high")
    elif min_confidence >= 0.5:
        filter_parts.append("#confidence:medium")
```

But `to_moorcheh_document()` stores confidence as a **float**:

```python
"confidence": self.confidence,  # e.g., 0.85
```

The filter `#confidence:high` will **never match** any document because the actual field value is `0.85`, not the string `"high"`. This means the confidence filter silently fails — all memories are returned regardless of confidence threshold when using the enhanced query path.

### Reproduction

```python
# Store memories with different confidence levels
m1 = MemoryRecord(type="fact", title="A", content="Low confidence fact",
    scope_type="agent", scope_id="a1", actor_id="a1", source="user", confidence=0.3)
m2 = MemoryRecord(type="fact", title="B", content="High confidence fact",
    scope_type="agent", scope_id="a1", actor_id="a1", source="user", confidence=0.95)
write_svc.store_memory(m1)
write_svc.store_memory(m2)

# Search with min_confidence=0.8 — should only return m2
result = read_svc.search_memories("fact", scope_type="agent", scope_id="a1", min_confidence=0.8)
# BUG: Both m1 and m2 are returned because #confidence:high never matches
```

### Suggested Fix

Store confidence as a categorical field alongside the float, or use numeric range filters:

```python
# Option A: Add a categorical field in to_moorcheh_document
if self.confidence >= 0.8:
    document["confidence_level"] = "high"
elif self.confidence >= 0.5:
    document["confidence_level"] = "medium"
else:
    document["confidence_level"] = "low"
```

---

## BUG-10: `get_field()` Helper Uses Python `or` Semantics — Falsies (0.0, 0, False) Are Mishandled

**File:** `memanto/app/services/memory_read_service.py`, `_format_memory_item()`  
**Severity:** 🟠 High

### Description

```python
def get_field(field_name, flat_field_name=None):
    flat_name = flat_field_name or field_name
    return metadata.get(field_name) or item.get(flat_name)
```

Python's `or` operator returns the second operand whenever the first is **falsy**. This causes incorrect behavior for valid falsy values:

- `confidence = 0.0` → `metadata.get("confidence")` returns `0.0` (falsy) → falls through to `item.get("confidence")` which may return `None` or a stale flat value
- `validation_count = 0` → falls through, may pick up wrong value from flat structure  
- `contradiction_detected = False` → falls through

This silently corrupts memory metadata during read-back, especially for low-confidence memories or memories with zero validations.

### Reproduction

```python
# Store a memory with confidence=0.0 (valid per Pydantic Field)
m = MemoryRecord(type="fact", title="Uncertain", content="Maybe true",
    scope_type="agent", scope_id="a1", actor_id="a1", source="user", confidence=0.0)
write_svc.store_memory(m)

# Read it back
result = read_svc.get_memory(m.id, "memanto_agent_a1")
# result["confidence"] may be None instead of 0.0
```

### Suggested Fix

```python
def get_field(field_name, flat_field_name=None):
    flat_name = flat_field_name or field_name
    if field_name in metadata:
        return metadata[field_name]
    return item.get(flat_name)
```

---

## BUG-11: Batch Upload Reports Single Status for All Documents — Individual Failures Hidden

**File:** `memanto/app/services/memory_write_service.py`, `batch_store_memories()`  
**Severity:** 🟡 Medium

### Description

After batch upload:

```python
moorcheh_status = upload_result.get("status", "unknown")
for result in results:
    if result["status"] == "pending":
        result["status"] = moorcheh_status
```

All documents get the **same status** from the batch response. If Moorcheh partially accepts the batch (some succeed, some fail due to malformed content), every document is reported with the overall batch status. Individual failures are hidden.

### Suggested Fix

Check individual document results from the Moorcheh response and update each result independently.

---

## BUG-12: Hardcoded Default JWT Secret Key — Session Token Forgery

**File:** `memanto/app/services/session_service.py`, line 65  
**Severity:** 🟡 Medium (Security)

### Description

```python
resolved_secret_key = (
    secret_key
    or os.getenv("MEMANTO_SECRET_KEY")
    or "memanto-default-secret-change-in-production"
)
```

If `MEMANTO_SECRET_KEY` is not set (which is the default), the JWT signing key is a **publicly known string**. Anyone who knows this default can forge valid session tokens for any agent.

### Reproduction

```python
import jwt
forged = jwt.encode(
    {
        "agent_id": "victim_agent",
        "namespace": "memanto_agent_victim_agent",
        "session_id": "sess_fake",
        "started_at": "2026-06-27T00:00:00Z",
        "expires_at": "2099-12-31T00:00:00Z"
    },
    "memanto-default-secret-change-in-production",
    algorithm="HS256"
)
# This token is accepted by validate_session()
```

### Suggested Fix

Fail loudly on startup if no secret is configured, or generate a random per-installation secret:

```python
if not resolved_secret_key:
    raise RuntimeError(
        "MEMANTO_SECRET_KEY must be set. Run 'memanto config set-secret' to configure."
    )
```

---

## BUG-13: `_filter_expired_memories` Fails Open — Corrupted Timestamps Prevent Expiration

**File:** `memanto/app/services/memory_read_service.py`, lines 406–430  
**Severity:** 🟡 Medium

### Description

```python
try:
    if isinstance(expires_at, str):
        expires_dt = parse_iso_timestamp(expires_at)
        if expires_dt > now:
            filtered.append(result)
    else:
        filtered.append(result)
except (ValueError, AttributeError):
    # If we can't parse, keep the memory (fail open)
    filtered.append(result)
```

If `expires_at` is corrupted (bad format, wrong type, truncated), the memory **never expires**. This is a fail-open design that prioritizes availability over correctness. A corrupted TTL field causes potentially sensitive time-limited memories to persist indefinitely.

### Suggested Fix

At minimum, log the parse failure. Consider failing closed for memories with corrupted expiry timestamps.

---

## BUG-14: Session File Writes Are Not Atomic — Crash During Write Corrupts Session State

**File:** `memanto/app/services/session_service.py`, `_save_session()`  
**Severity:** 🟡 Medium

### Description

```python
def _save_session(self, session: Session) -> None:
    session_file = self.sessions_dir / f"{session.agent_id}.json"
    with open(session_file, "w") as f:
        json.dump(session.model_dump(mode="json"), f, indent=2)
```

Direct truncation-write. If the process crashes mid-write (OOM, SIGKILL, disk full), the session file is left **truncated or empty**. On next access, `json.load()` raises `JSONDecodeError`, and the session is permanently lost. Same issue applies to `_save_agent()` in `agent_service.py`.

### Suggested Fix

Atomic write pattern (temp file + rename):

```python
import tempfile, os
tmp_fd, tmp_path = tempfile.mkstemp(dir=self.sessions_dir, suffix=".tmp")
try:
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(session.model_dump(mode="json"), f, indent=2)
    os.replace(tmp_path, session_file)  # Atomic on POSIX
finally:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
```

---

## BUG-15: Conversation Extraction Silently Truncates — Memories Lost from Long Conversations

**File:** `memanto/app/services/conversation_memory_extraction_service.py`, `_conversation_text()`  
**Severity:** 🟡 Medium

### Description

```python
def _conversation_text(self, messages):
    lines = []
    total = 0
    for message in messages:
        line = f"{message['role'].strip()}: {message['content'].strip()}"
        total += len(line)
        if total > self.MAX_CONTENT_CHARS:  # 12,000
            break  # ← Silent truncation
        lines.append(line)
    return "\n".join(lines)
```

Conversations exceeding 12K characters are silently truncated. The LLM never sees messages past the truncation point. Important commitments, decisions, or facts in the truncated portion are **never extracted** as memories. The caller receives no indication that data was lost.

### Reproduction

```python
# Create a 200-message conversation where the last message contains a critical fact
messages = [{"role": "user", "content": "filler " * 100}] * 150
messages.append({"role": "user", "content": "My API key is sk-1234"})
# Extraction silently truncates well before the last message
candidates = svc.extract(namespace="ns", messages=messages)
# "API key" memory is never extracted — no error, no warning
```

### Suggested Fix

- Return a `truncated: True` flag in the result when truncation occurs
- Consider processing long conversations in overlapping chunks
- At minimum, log a warning

---

## Appendix: Minor Issues

| ID | File | Description | Severity |
|----|------|-------------|----------|
| M-01 | `idempotency.py` | In-memory idempotency store lost on restart — duplicate writes possible after server restart | Low |
| M-02 | `ids.py` | `generate_memory_id()` uses 12 hex chars (48 bits) — birthday collision at ~16M IDs | Low |
| M-03 | `agent_service.py:delete_agent()` | Deletes local JSON but leaves Moorcheh namespace and all memories orphaned | Low |
| M-04 | `memory_read_service.py:search_changed_since` | Cannot detect deleted memories — only created/updated are reported | Low |
| M-05 | `session_service.py` | No file locking on session summary MD files — concurrent appends can interleave | Low |

---

## Methodology

Every `.py` file in the core service and model layers was read line-by-line. Each logic branch, error path, and data transformation was analyzed for:

1. Data loss scenarios (non-atomic operations, missing rollback)
2. Silent metadata corruption (dropped fields during serialization/deserialization)
3. Temporal logic errors (timezone mismatches, incorrect filtering order)
4. Contradiction handling gaps (write-time checks disabled)
5. Namespace isolation boundaries
6. Python type coercion pitfalls (`or` semantics, naive vs aware datetimes)
7. Race conditions in concurrent file/API operations

Each bug was verified by tracing the code path from the entry point through all intermediate transformations to the final output, confirming the issue is reachable in normal operation.

---

*End of report.*
