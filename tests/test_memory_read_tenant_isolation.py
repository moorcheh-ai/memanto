"""Tenant isolation regression tests for the memory read service.

A memory read must always be scoped to a single agent namespace. These tests
guard against regressions that would let a caller with a missing/empty
``agent_id`` fan out across every namespace on the server account (or answer
from the first namespace it finds), which is a cross-tenant data leak.
"""

from unittest.mock import MagicMock

import pytest

from memanto.app.services.memory_read_service import MemoryReadService
from memanto.app.utils.errors import MemoryOperationError


def _client_with_namespaces(namespaces):
    client = MagicMock()
    client.namespaces.list.return_value = {
        "namespaces": [{"namespace_name": n} for n in namespaces]
    }
    return client


def test_get_search_namespaces_requires_agent_id():
    service = MemoryReadService(_client_with_namespaces(["memanto_agent_alice"]))

    with pytest.raises(MemoryOperationError, match="agent_id"):
        service._get_search_namespaces(None)

    with pytest.raises(MemoryOperationError, match="agent_id"):
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

    with pytest.raises(MemoryOperationError, match="agent_id"):
        service.search_memories(query="anything", agent_id=None, limit=10)


def test_generate_answer_refuses_first_namespace_fallback():
    service = MemoryReadService(
        _client_with_namespaces(["memanto_agent_alice", "memanto_agent_bob"])
    )

    with pytest.raises(MemoryOperationError, match="agent_id"):
        service.generate_answer(query="anything", agent_id=None)


def test_whitespace_only_agent_id_is_rejected():
    """Whitespace-only ids are invalid under the ``AgentCreate`` pattern.

    They pass a plain truthy check yet still produce a namespace string, so the
    service guards must reject them instead of treating them as a scoped read.
    """
    service = MemoryReadService(_client_with_namespaces(["memanto_agent_alice"]))

    for agent_id in ("   ", "\t", " \n "):
        with pytest.raises(MemoryOperationError, match="agent_id"):
            service._get_search_namespaces(agent_id)

        with pytest.raises(MemoryOperationError, match="agent_id"):
            service.search_memories(query="anything", agent_id=agent_id, limit=10)

        with pytest.raises(MemoryOperationError, match="agent_id"):
            service.generate_answer(query="anything", agent_id=agent_id)
