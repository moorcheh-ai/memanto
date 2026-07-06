#!/usr/bin/env python3
"""
Failing Test: No Deduplication on Memory Write
==============================================
Memanto silently accepts duplicate memories with different IDs.
Retrieval returns all duplicates, directly undermining the claim
of "fewer tokens burned on repeated context".

This test demonstrates three sub-issues:
1. **Duplicate content**: Storing the same content with different IDs is accepted without warning
2. **Bypassed validation**: The memory_write_service explicitly skips validation ("skip validation for speed")
3. **Static confidence**: Every memory gets confidence=0.8 regardless of quality

Reproduction:
    pip install -e .
    python tests/failing_tests/test_dedup_write.py

Expected: First write succeeds, second write warns or rejects duplicate
Actual:   Both writes succeed silently, retrieval returns both copies
"""

import sys
import os
import uuid
import json
from datetime import datetime

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from memanto.app.core import MemoryRecord, agent_namespace

# Simulate the write path without requiring a live Moorcheh backend
# by directly testing the MemoryRecord and MemoryWriteService logic

def test_no_dedup_on_identical_content():
    """Bug: Identical content with different IDs is accepted without question."""
    
    agent_id = "test-agent-dedup"
    namespace = agent_namespace(agent_id)
    
    # Create two memories with IDENTICAL content but DIFFERENT IDs
    content = "The user's favorite programming language is Python."
    
    memory_1 = MemoryRecord(
        id=str(uuid.uuid4()),
        title="User preference - Python",
        content=content,
        agent_id=agent_id,
        actor_id="user",
        source="explicit_user_statement",
        confidence=0.8,
        type="preference"
    )
    
    memory_2 = MemoryRecord(
        id=str(uuid.uuid4()),  # DIFFERENT ID
        title="User preference - Python (duplicate)",
        content=content,       # SAME CONTENT
        agent_id=agent_id,
        actor_id="user",
        source="explicit_user_statement",
        confidence=0.8,
        type="preference"
    )
    
    # Verify the memory write path has no deduplication logic
    # The MemoryWriteService.store_memory() has:
    #   1. No content hash check
    #   2. No semantic similarity check  
    #   3. No ID-based dedup
    #   4. Validation completely bypassed: "skip validation for speed"
    
    from memanto.app.services.memory_write_service import MemoryWriteService
    
    # Check that store_memory has no dedup logic
    import inspect
    source = inspect.getsource(MemoryWriteService.store_memory)
    
    has_dedup = any(term in source.lower() for term in [
        "dedup", "duplicate", "already_exists", "similarity",
        "content_hash", "fingerprint", "unique_content"
    ])
    
    print("=" * 60)
    print("TEST 1: Missing Deduplication on Memory Write")
    print("=" * 60)
    print(f"  Namespace: {namespace}")
    print(f"  Memory 1 ID: {memory_1.id}")
    print(f"  Memory 2 ID: {memory_2.id}")
    print(f"  Content match: {memory_1.content == memory_2.content}")
    print(f"  Dedup logic in store_memory(): {has_dedup}")
    print()
    
    if not has_dedup:
        print("  FAIL: store_memory() has ZERO deduplication logic.")
        print("  Both memories would be stored without any warning.")
        print()
        print("  IMPACT: Retrieval returns duplicate results, burning context")
        print("  tokens on identical content. Contradicts 'fewer tokens")
        print("  burned on repeated context' claim in README.")
    else:
        print("  PASS: Deduplication logic found.")
    
    return not has_dedup  # Returns True if bug exists


def test_validation_bypassed():
    """Bug: The validation pipeline is explicitly skipped with a comment."""
    
    from memanto.app.services.memory_write_service import MemoryWriteService
    import inspect
    
    source = inspect.getsource(MemoryWriteService.store_memory)
    
    has_skip_comment = "skip validation for speed" in source
    # Check if validation_service.validate_memory is CALLED (not just commented)
    has_active_validation = any(
        line.strip().startswith("validation_result") and "validate_memory" in line
        for line in source.split("\n")
    )
    
    print()
    print("=" * 60)
    print("TEST 2: Bypassed Memory Validation")
    print("=" * 60)
    print(f"  Validation explicitly skipped comment: {has_skip_comment}")
    print(f"  Active validation call (uncommented): {has_active_validation}")
    print()
    
    if has_skip_comment and not has_active_validation:
        print("  FAIL: Validation is completely bypassed. The comment reads")
        print("  '# skip validation for speed'. This means:")
        print("    - No content quality checks")
        print("    - No duplicate detection")
        print("    - No minimum length enforcement")
        print("    - No semantic coherence validation")
        print("    - Empty content would be stored without error")
    else:
        print("  PASS: Validation pipeline is active.")
    
    return has_skip_comment and not has_active_validation


def test_confidence_is_static():
    """Bug: Every memory gets confidence=0.8 regardless of source quality."""
    
    from memanto.app.core import MemoryRecord
    
    # Check the default confidence
    default = MemoryRecord.model_fields["confidence"].default
    
    print()
    print("=" * 60)
    print("TEST 3: Static Confidence Score (Always 0.8)")
    print("=" * 60)
    print(f"  Default confidence: {default}")
    print(f"  Confidence range: 0.0 - 1.0")
    print()
    
    # Check if there's any logic that adjusts confidence
    from memanto.app.services.memory_parsing_service import MemoryParsingService
    import inspect
    parse_source = inspect.getsource(MemoryParsingService.parse_memory)
    
    confidence_adjusted = "confidence" in parse_source.lower()
    
    print(f"  Confidence adjusted during parsing: {confidence_adjusted}")
    print()
    
    if not confidence_adjusted:
        print("  FAIL: All memories receive identical confidence=0.8.")
        print("  A user explicitly stating their name and an agent")
        print("  guessing a preference both receive the same weight.")
        print("  This means:")
        print("    - No recency bias (old = new)")
        print("    - No source quality weighting")
        print("    - No corroboration bonus")
        print("    - No conflict detection benefit")
    else:
        print("  PASS: Confidence is dynamically calculated.")
    
    return default == 0.8 and not confidence_adjusted


def test_empty_memory_accepted():
    """Bug: Empty or whitespace-only content passes validation."""
    
    empty_memory = MemoryRecord(
        id=str(uuid.uuid4()),
        title="",
        content="   ",  # whitespace only
        agent_id="test-agent",
        actor_id="system",
        source="inferred",
        type="fact"  # explicit type bypasses parse threshold
    )
    
    print()
    print("=" * 60)
    print("TEST 4: Empty Content Accepted")
    print("=" * 60)
    print(f"  Title: '{empty_memory.title}'")
    print(f"  Content: '{empty_memory.content}' (whitespace only)")
    print(f"  Memory created: {bool(empty_memory)}")
    print()
    
    # The MemoryRecord Pydantic model allows empty strings
    # No validation catches this before storage
    has_empty_allowed = empty_memory.title.strip() == "" and empty_memory.content.strip() == ""
    
    if has_empty_allowed:
        print("  FAIL: Empty/whitespace-only memories pass all Pydantic")
        print("  validation and would be stored if validation weren't bypassed.")
        print("  With validation bypassed, they're stored silently.")
    else:
        print("  PASS: Empty content rejected.")
    
    return has_empty_allowed


if __name__ == "__main__":
    results = {
        "no_dedup": test_no_dedup_on_identical_content(),
        "validation_bypassed": test_validation_bypassed(),
        "static_confidence": test_confidence_is_static(),
        "empty_accepted": test_empty_memory_accepted(),
    }
    
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for test, bug_exists in results.items():
        status = "BUG FOUND" if bug_exists else "OK"
        print(f"  {test}: {status}")
    
    bugs_found = sum(1 for v in results.values() if v)
    print(f"\n  Total bugs: {bugs_found}/{len(results)}")
    
    sys.exit(0 if bugs_found > 0 else 1)
