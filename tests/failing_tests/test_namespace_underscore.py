"""
Failing test: MemoryScope.from_namespace() fails on scope IDs containing underscores.

This test demonstrates BUG-H4: namespace.split("_") breaks when scope_id
contains underscores (which are valid per the validation regex).

Expected: should parse correctly
Actual: raises ValueError
"""
import pytest
from memanto.app.core import MemoryScope, create_memory_scope


def test_from_namespace_with_underscore_scope_id():
    # scope_id with underscores is valid per AgentCreate regex: ^[a-zA-Z0-9_-]+$
    scope = create_memory_scope("agent", "my_agent_123")
    namespace = scope.to_namespace()  # "memanto_agent_my_agent_123"

    # This should round-trip correctly
    parsed = MemoryScope.from_namespace(namespace)

    assert parsed.scope_type == "agent"
    assert parsed.scope_id == "my_agent_123"
