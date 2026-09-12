"""Tenant isolation regression tests for the memory read service.

A memory read must always be scoped to a single agent namespace. These tests
guard against regressions that would let a caller with a missing/empty
``agent_id`` fan out across every namespace on the server account (or answer
from the first namespace it finds), which is a cross-tenant data leak.
"""

from unittest.mock import MagicMock

import pytest

from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.utils.errors import MemoryError


def _client_with_namespaces(namespaces):
    client = MagicMock()
    client.namespaces.list.return_value = {
        "namespaces": [{"namespace_name": n} for n in namespaces]
    }
    return client


def test_get_search_namespaces_requires_agent_id():
    service = MemoryReadService(_client_with_namespaces(["memanto_agent_alice"]))

    with pytest.raises(MemoryError, match="agent_id"):
        service._get_search_namespaces(None)

    with pytest.raises(MemoryError, match="agent_id"):
        service._get_search_namespaces("")


def test_get_search_namespaces_scopes_to_single_tenant():
    service = MemoryReadService(
        _client_with_namespaces(["memanto_agent_alice", "memanto_agent_bob"])
    )

    assert service._get_search_namespaces("alice") == ["memanto_agent_alice"]


def test_search_memories_refuses_cross_tenant_fanout():
    service = MemoryReadService(
        _client_with_namespaces(["memanto_agent_alice", "memanto_agent_bob"])
    )

    with pytest.raises(MemoryError, match="agent_id"):
        service.search_memories(query="anything", agent_id=None, limit=10)


def test_generate_answer_refuses_first_namespace_fallback():
    service = MemoryReadService(
        _client_with_namespaces(["memanto_agent_alice", "memanto_agent_bob"])
    )

    with pytest.raises(MemoryError, match="agent_id"):
        service.generate_answer(query="anything", agent_id=None)
