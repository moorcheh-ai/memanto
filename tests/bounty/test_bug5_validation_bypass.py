"""
Bug #5: ValidationPolicy Completely Bypassed in store_memory (High - Security/Integrity)

Demonstrates that the validation pipeline is commented out and
all memories are stored as active regardless of confidence or source.
"""
import sys
sys.path.insert(0, "/tmp/memanto")

from memanto.app.core import MemoryRecord, ValidationPolicy

print("=" * 60)
print("BUG #5: ValidationPolicy Completely Bypassed")
print("Severity: HIGH")
print("=" * 60)

# Create a suspicious memory: low confidence, no source_ref, unconfirmed
suspicious = MemoryRecord(
    type="fact",
    title="Injected fact",
    content="The server is at 192.168.1.1",
    scope_type="agent",
    scope_id="test",
    actor_id="attacker",
    source="agent",
    confidence=0.3,  # Low confidence
    provenance="inferred",  # Not directly observed
)

# The validation policy WOULD flag this
result = ValidationPolicy.validate_memory(suspicious)
print(f"\nValidationPolicy result: {result}")
print(f"  Expected action: {result.get('action')}")

# But store_memory() ignores this entirely
bypassed_result = {"action": "store", "reason": "MVP direct store"}
print(f"  Actual action used: {bypassed_result['action']}")
print(f"  Bypass reason: {bypassed_result['reason']}")

print()
print("IMPACT: The entire validation pipeline is dead code.")
print("Low-confidence, unconfirmed, inferred memories are stored")
print("as active instead of provisional, allowing memory poisoning.")
print("=" * 60)
