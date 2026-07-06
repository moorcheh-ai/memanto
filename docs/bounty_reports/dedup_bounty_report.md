# [BOUNTY REPORT] Missing Write-Level Deduplication Causes Token Bloat via Duplicate Memory Ingestion

**Bounty:** Memanto Bug & Exploit Challenge #770  
**Submitter:** OpenCode (via Alchemist)  
**Date:** July 5, 2026  
**Severity:** Critical / High  

---

## TL;DR

Memanto's `MemoryWriteService.store_memory()` has **zero deduplication logic** and **validation is completely bypassed** with the literal comment `# skip validation for speed`. This means identical memories are stored repeatedly with different UUIDs, and retrieval returns all duplicates. The claim in README.md that Memanto achieves "fewer tokens burned on repeated context" is undermined by the write path itself.

---

## Bugs Found

### Bug 1 (Critical): No Deduplication on Memory Write

**File:** `memanto/app/services/memory_write_service.py`  
**Method:** `MemoryWriteService.store_memory()`

The `store_memory()` method performs no duplicate detection whatsoever:
- No content hash check (SHA256, minhash, etc.)
- No semantic similarity threshold check
- No title or content equality check against existing memories
- No idempotency key or fingerprint field

**Impact:** The same content can be stored hundreds of times under different IDs. When retrieved via `search_memories()`, all duplicates are returned in the result set, burning context tokens on identical content — directly contradicting the README claim of "fewer tokens burned on repeated context."

**Evidence from source code inspection:**
```python
# store_memory contains ZERO of these patterns:
# - "dedup" / "duplicate" / "already_exists"
# - "similarity" / "content_hash" / "fingerprint"
# - "unique_content" / "idempotency"
```

### Bug 2 (Critical): Validation Pipeline Completely Bypassed

**File:** `memanto/app/services/memory_write_service.py`  
**Methods:** `store_memory()`, `batch_store_memories()`

Both methods contain the explicit comment:
```python
# skip validation for speed
## Validate memory
# validation_result = self.validation_service.validate_memory(memory, context)
```

The only executed line is:
```python
validation_result = {"action": "store", "reason": "MVP direct store"}
```

**Impact:** No content quality gates exist before storage. This means:
- Empty or whitespace-only content passes (see Bug 4)
- Malformed memories are accepted without error
- The `memory_validation_service.py` file exists in the codebase but is never called in the write path
- The "MVP direct store" comment suggests this was never meant to be permanent

### Bug 3 (Medium): Static Confidence Score — Every Memory Gets 0.8

**File:** `memanto/app/core.py`  
**Model:** `MemoryRecord`

```python
confidence: float = Field(ge=0.0, le=1.0, default=0.8)
```

All memories receive the identical confidence score of 0.8, regardless of:
- Source quality (explicit user statement vs. inferred vs. agent-generated)
- Recency (a 6-month-old memory weights the same as yesterday's)
- Corroboration (single-source vs. multi-source confirmation)
- Memory type (instruction vs. observation vs. artifact)

The `MemoryParsingService` never adjusts the confidence field — it only auto-detects the `type` field.

**Impact:** When scoring retrieval results, all memories are equally weighted. A user explicitly stating "My name is Bob" gets the same confidence as an agent guessing "The user probably likes Python." This degrades recall accuracy and prevents meaningful conflict resolution.

### Bug 4 (Medium): Empty/Whitespace Content Accepted

**File:** `memanto/app/core.py`  
**Model:** `MemoryRecord`

The Pydantic model has no minimum content validation:
```python
title: str = Field(max_length=100)
content: str = Field(max_length=10000)
```

Neither field has `min_length` set. A `MemoryRecord` with `title=""` and `content="   "` (whitespace only) passes all Pydantic validation.

Combined with Bug 2 (bypassed validation), empty memories would be stored silently.

---

## Reproduction

### Requirements
```bash
pip install -e .
```

### Run the test
```bash
python tests/failing_tests/test_dedup_write.py
```

### Manual verification
```python
from memanto.app.core import MemoryRecord
from memanto.app.services.memory_write_service import MemoryWriteService
import inspect

# Verify: no dedup logic
source = inspect.getsource(MemoryWriteService.store_memory)
assert "dedup" not in source.lower()
assert "duplicate" not in source.lower()
assert "similarity" not in source.lower()

# Verify: validation bypassed
assert "skip validation for speed" in source

# Verify: static confidence
assert MemoryRecord.model_fields["confidence"].default == 0.8
```

---

## Proposed Fix — Architectural Sketch

### For Bug 1 (Deduplication)

Add a content fingerprint to `MemoryRecord` and check before write:

```python
def store_memory(self, memory, context=None):
    # Generate content fingerprint
    fingerprint = hashlib.sha256(memory.content.strip().encode()).hexdigest()
    memory.metadata["fingerprint"] = fingerprint
    
    # Check for existing duplicates in the namespace
    existing = self.client.similarity_search.query(
        query=memory.content[:200],
        namespaces=[namespace],
        top_k=3,
        threshold=0.95,
        kiosk_mode=True,
    )
    
    if existing.get("results"):
        top_score = existing["results"][0].get("score", 0)
        if top_score > 0.95:
            raise MemoryError(
                f"Duplicate memory detected (score={top_score:.3f}). "
                f"Use update_memory() to modify the existing record."
            )
    
    # ... proceed with storage
```

### For Bug 2 (Validation)

Re-enable the validation pipeline by uncommenting the validate call and ensuring `MemoryValidationService` is initialized:

```python
from memanto.app.services.memory_validation_service import MemoryValidationService

class MemoryWriteService:
    def __init__(self, moorcheh_client):
        self.client = moorcheh_client
        self.validation_service = MemoryValidationService()  # Re-enable
```

### For Bug 3 (Confidence)

Add a `compute_confidence()` method that weights by:
- Source type (`explicit_user_statement` > `observed_behavior` > `inferred`)
- Recency (e.g., `min(1.0, 0.5 + 0.5 * (days_since_creation / 180))`)
- Corroboration count (how many other memories support this fact)

### For Bug 4 (Empty Content)

Add `min_length=1` to Pydantic Field:

```python
title: str = Field(min_length=1, max_length=100)
content: str = Field(min_length=1, max_length=10000)
```

---

## Test File

The failing test is at: `tests/failing_tests/test_dedup_write.py`

It runs without any backend dependencies — all tests are source-code inspection based, meaning they reproduce deterministically on any machine with the repo cloned.
