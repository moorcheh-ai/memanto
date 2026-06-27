"""
Reproduction script for memanto search_multi_scope import bug.

Prerequisites:
    pip install memanto

Expected behavior:
    search_multi_scope should work (or fail with a network/auth error,
    not an import error).

Actual behavior:
    ModuleNotFoundError: No module named 'memanto.memanto'
"""
from memanto.app.services.memory_read_service import MemoryReadService

# We don't need a real Moorcheh client to trigger the bug —
# the import error happens before any network call.
class FakeClient:
    similarity_search = None

service = MemoryReadService(FakeClient())

try:
    result = service.search_multi_scope(
        query="test",
        scopes=[
            {"scope_type": "user", "scope_id": "user1"},
            {"scope_type": "agent", "scope_id": "agent1"},
        ],
    )
    print("Result:", result)
except ModuleNotFoundError as e:
    print(f"BUG CONFIRMED: {e}")
    # Output: BUG CONFIRMED: No module named 'memanto.memanto'
except Exception as e:
    # If we get a different error (e.g. AttributeError for FakeClient),
    # the import bug is still present but masked
    if "memanto.memanto" in str(e):
        print(f"BUG CONFIRMED: {e}")
    else:
        print(f"Different error (import may be lazy): {type(e).__name__}: {e}")
