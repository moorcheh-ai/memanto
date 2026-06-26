"""
Unit tests for MemoryScope.from_namespace fix (underscore in scope_id)

Tests the fix for namespace parsing crash when scope_id contains underscores.
"""

import pytest

from memanto.app.core import MemoryScope


class TestNamespaceParsing:
    """Test cases for MemoryScope.from_namespace"""

    def test_scope_id_without_underscore(self):
        """Test 1: scope_id without underscore parses correctly"""
        ns = "memanto_agent_123"
        scope = MemoryScope.from_namespace(ns)
        assert scope.scope_type == "agent"
        assert scope.scope_id == "123"

    def test_scope_id_with_underscore(self):
        """Test 2: scope_id with underscore parses correctly (no crash)"""
        ns = "memanto_agent_my_agent_id"
        scope = MemoryScope.from_namespace(ns)
        assert scope.scope_type == "agent"
        assert scope.scope_id == "my_agent_id"

    def test_scope_id_with_multiple_underscores(self):
        """Test 2b: scope_id with multiple underscores parses correctly"""
        ns = "memanto_user_user_123_extra"
        scope = MemoryScope.from_namespace(ns)
        assert scope.scope_type == "user"
        assert scope.scope_id == "user_123_extra"

    def test_invalid_namespace_format(self):
        """Test 3: invalid namespace raises ValueError"""
        with pytest.raises(ValueError, match="Invalid MEMANTO namespace format"):
            MemoryScope.from_namespace("invalid_namespace")

    def test_invalid_scope_type(self):
        """Test 3b: invalid scope_type raises ValueError"""
        with pytest.raises(ValueError, match="Invalid MEMANTO namespace format"):
            MemoryScope.from_namespace("memanto_invalid_123")

    def test_session_scope(self):
        """Test: session scope type works"""
        ns = "memanto_session_abc-123"
        scope = MemoryScope.from_namespace(ns)
        assert scope.scope_type == "session"
        assert scope.scope_id == "abc-123"

    def test_workspace_scope_with_underscore(self):
        """Test: workspace scope with underscore in ID"""
        ns = "memanto_workspace_my_workspace_id"
        scope = MemoryScope.from_namespace(ns)
        assert scope.scope_type == "workspace"
        assert scope.scope_id == "my_workspace_id"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
