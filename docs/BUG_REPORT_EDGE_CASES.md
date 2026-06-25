# Memanto Bug Report: Memory Retrieval Edge Cases

## Bug Category: Retrieval Quality & Accuracy

### Bug 1: Timeline Amnesia in Rapid Succession Events

**Description:**
When multiple events occur within a short time window (< 1 second apart), the memory retrieval system fails to maintain accurate temporal ordering, leading to timeline amnesia.

**Steps to Reproduce:**
1. Create multiple memory entries with timestamps < 1 second apart
2. Query for events "in order"
3. Observe incorrect temporal ordering

**Expected Behavior:**
Events should be retrieved in exact chronological order regardless of time delta.

**Actual Behavior:**
Events are sometimes retrieved in arbitrary order when timestamps are very close.

**Severity:** Medium

---

### Bug 2: Contradiction Resolution Failure with Negation

**Description:**
When a new memory directly contradicts a previous memory using negation (e.g., "User likes coffee" followed by "User does not like coffee"), the system fails to properly resolve the contradiction and may return both facts.

**Steps to Reproduce:**
1. Store: "User prefers dark mode"
2. Store: "User does not prefer dark mode"
3. Query: "What are the user preferences?"

**Expected Behavior:**
Only the most recent preference should be returned, or contradiction should be flagged.

**Actual Behavior:**
Both contradictory facts may be returned without resolution.

**Severity:** High

---

### Bug 3: Context Window Overflow Silent Truncation

**Description:**
When the context window is filled, older memories are silently truncated without any notification or graceful degradation strategy.

**Steps to Reproduce:**
1. Fill memory with entries exceeding context window
2. Query for oldest memories
3. No indication that memories were lost

**Expected Behavior:**
System should either: (a) warn about truncation, (b) implement LRU with importance weighting, or (c) compress older memories.

**Actual Behavior:**
Silent truncation with no user feedback.

**Severity:** High

---

### Bug 4: Unicode Handling in Memory Keys

**Description:**
Memory entries with unicode characters (emoji, non-Latin scripts) in key fields may cause retrieval failures.

**Steps to Reproduce:**
1. Store memory with key containing emoji: "User favorite: 🎮 gaming"
2. Query using the same emoji
3. Retrieval may fail or return incorrect results

**Expected Behavior:**
Unicode should be handled consistently.

**Actual Behavior:**
Inconsistent retrieval with unicode keys.

**Severity:** Low

---

## Proposed Fixes

1. **Timeline Amnesia:** Add microsecond precision to timestamps and implement stable sort
2. **Contradiction Resolution:** Implement explicit contradiction detection with recency-biased resolution
3. **Context Overflow:** Add memory importance scoring and implement graceful degradation with user notification
4. **Unicode Handling:** Normalize unicode strings before storage and retrieval

## Environment
- Python 3.11+
- memanto core package
- moorcheh.ai backend

## Additional Notes
These bugs were discovered through systematic testing of edge cases. Happy to provide test scripts if needed.
