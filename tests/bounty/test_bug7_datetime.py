"""
Bug #7: datetime.utcnow() vs Timezone-Aware Comparisons (Medium - Logic)

Demonstrates that naive datetime from datetime.utcnow() cannot be
compared with timezone-aware datetime from datetime.now(timezone.utc)
in Python 3.12+, causing crashes in TTL filtering and confidence computation.
"""
import sys
sys.path.insert(0, "/tmp/memanto")

from datetime import datetime, timezone

print("=" * 60)
print("BUG #7: Naive vs Aware datetime Comparison Crash")
print("Severity: MEDIUM")
print("=" * 60)

naive_created = datetime.utcnow()  # no tzinfo
aware_now = datetime.now(timezone.utc)  # has tzinfo

print(f"\nnaive_created: {naive_created} (tzinfo={naive_created.tzinfo})")
print(f"aware_now: {aware_now} (tzinfo={aware_now.tzinfo})")

try:
    is_expired = aware_now > naive_created
    print(f"Comparison result: {is_expired}")
except TypeError as e:
    print(f"CRASH: {e}")
    print("\nThis error occurs in:")
    print("  - _filter_expired_memories (read_service.py)")
    print("  - compute_confidence (core.py)")
    print("  - TTL enforcement")

print()
print("IMPACT: In Python 3.12+, comparing naive and aware datetimes raises TypeError.")
print("The codebase mixes datetime.utcnow() (naive) with datetime.now(timezone.utc)")
print("(aware), creating latent crash bugs in TTL and confidence computation.")
print("=" * 60)
