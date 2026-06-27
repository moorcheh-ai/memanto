"""
Tests for bug fixes in Memanto core
"""
import pytest
from memanto.app.core import MemoryScope, MemoryRecord, ValidationPolicy


class TestNamespaceParsing:
    """Test BUG 3 fix: namespace parsing with underscores in scope_id"""

    def test_simple_scope_id(self):
        """Test simple scope_id without underscores"""
        scope = MemoryScope.from_namespace("memanto_user_abc123")
        assert scope.scope_type == "user"
        assert scope.scope_id == "abc123"

    def test_scope_id_with_underscores(self):
        """Test scope_id containing underscores - this was broken before fix"""
        scope = MemoryScope.from_namespace("memanto_user_u_acme_prod")
        assert scope.scope_type == "user"
        assert scope.scope_id == "u_acme_prod"

    def test_session_with_underscores(self):
        """Test session scope with underscores"""
        scope = MemoryScope.from_namespace("memanto_session_sess_2025_01_01")
        assert scope.scope_type == "session"
        assert scope.scope_id == "sess_2025_01_01"

    def test_agent_with_underscores(self):
        """Test agent scope with underscores"""
        scope = MemoryScope.from_namespace("memanto_agent_my_dev_agent")
        assert scope.scope_type == "agent"
        assert scope.scope_id == "my_dev_agent"

    def test_invalid_namespace_format(self):
        """Test invalid namespace raises ValueError"""
        with pytest.raises(ValueError, match="Invalid MEMANTO namespace format"):
            MemoryScope.from_namespace("invalid_namespace")

    def test_invalid_prefix(self):
        """Test namespace with wrong prefix raises ValueError"""
        with pytest.raises(ValueError, match="Invalid MEMANTO namespace format"):
            MemoryScope.from_namespace("wrong_user_abc123")


class TestValidationPolicy:
    """Test BUG 1 fix: validation pipeline is active"""

    def test_validation_policy_exists(self):
        """Test ValidationPolicy class exists and is not dead code"""
        assert hasattr(ValidationPolicy, "validate_memory")
        assert hasattr(ValidationPolicy, "make_provisional")

    def test_validate_fact_without_confirmation(self):
        """Test fact memory without user confirmation goes to provisional"""
        memory = MemoryRecord(
            type="fact",
            title="Test fact",
            content="Test content",
            scope_type="user",
            scope_id="test_user",
            actor_id="test_actor",
            source="user",
            confidence=0.7,
        )
        result = ValidationPolicy.validate_memory(memory, {})
        assert result["action"] == "store_provisional"

    def test_validate_fact_with_confirmation(self):
        """Test fact memory with user confirmation is stored"""
        memory = MemoryRecord(
            type="fact",
            title="Test fact",
            content="Test content",
            scope_type="user",
            scope_id="test_user",
            actor_id="test_actor",
            source="user",
            confidence=0.7,
        )
        result = ValidationPolicy.validate_memory(memory, {"user_confirmed": True})
        assert result["action"] == "store"

    def test_validate_tool_grounded_memory(self):
        """Test tool-grounded memory is stored"""
        memory = MemoryRecord(
            type="fact",
            title="Test fact",
            content="Test content",
            scope_type="user",
            scope_id="test_user",
            actor_id="test_actor",
            source="tool",
            source_ref="api_call_123",
            confidence=0.8,
        )
        result = ValidationPolicy.validate_memory(memory, {})
        assert result["action"] == "store"

    def test_make_provisional(self):
        """Test make_provisional sets correct status and TTL"""
        memory = MemoryRecord(
            type="fact",
            title="Test fact",
            content="Test content",
            scope_type="user",
            scope_id="test_user",
            actor_id="test_actor",
            source="user",
            confidence=0.9,
        )
        provisional = ValidationPolicy.make_provisional(memory)
        assert provisional.status == "provisional"
        assert provisional.confidence <= 0.5
        assert provisional.ttl_seconds == 3600
