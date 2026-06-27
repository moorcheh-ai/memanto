"""
Bug #3: Namespace Parsing Breaks for scope_ids with Underscores (High - Logic)

Demonstrates that MemoryScope.from_namespace() crashes when scope_id
contains underscores, which are valid per the AgentCreate regex.
"""
import sys
sys.path.insert(0, "/tmp/memanto")

from memanto.app.core import MemoryScope, create_memory_scope

print("=" * 60)
print("BUG #3: Namespace Parsing Failure for Underscored scope_ids")
print("Severity: HIGH")
print("=" * 60)

# Test various scope_ids with underscores
test_ids = ["my_agent_1", "agent_v2_prod", "test_bot"]

for scope_id in test_ids:
    scope = create_memory_scope(scope_type="agent", scope_id=scope_id)
    namespace = scope.to_namespace()
    print(f"\nscope_id: {scope_id}")
    print(f"  namespace: {namespace}")

    try:
        parsed = MemoryScope.from_namespace(namespace)
        print(f"  parsed: OK ({parsed.scope_id})")
    except ValueError as e:
        print(f"  CRASH: {e}")
        print(f"  IMPACT: Agent '{scope_id}' cannot have its namespace resolved")

print()
print("IMPACT: Any agent with underscores in its ID has broken namespace resolution.")
print("The AgentCreate regex allows underscores (^[a-zA-Z0-9_-]+$), but")
print("from_namespace() cannot parse them back.")
print("=" * 60)
