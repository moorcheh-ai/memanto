"""
Regression test for write-time contradiction resolution on the update path.

`update_memory` (PATCH /{agent_id}/memories/{memory_id}) bypassed the
`MemoryValidationService.validate_memory` call that the sibling `store_memory`
and `batch_store_memories` paths enforce. Result: a caller could change a
memory's content/title/type via PATCH to directly contradict an existing
*active* same-type/same-title memory, leaving two active contradictory
memories — exactly the "fails to resolve contradictions" failure mode the
bounty's in-scope list names.

This test pins the contract: `update_memory` MUST route through
`validate_memory` so that a contradicting PATCH supersedes the prior active
record instead of silently overwriting in place.

See also:
  - memory_write_service.py:430  (the MVP-stub that skipped validation)
  - memory_write_service.py:96   (store_memory — the correct pattern)
  - PR #1611                     (added validate_memory to store/batch but
                                  left update_memory's MVP-stub in place)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from memanto.app.services.memory_write_service import MemoryWriteService
from memanto.app.services.memory_validation_service import MemoryValidationService


# The memory record `update_memory` retrieves via MemoryReadService.get_memory
# before applying updates. Fields mirror the real wire format.
_EXISTING_TARGET = {
    "id": "mem_target",
    "text": "[FACT] Ship date\n\nv1 ships July 1",
    "title": "Ship date",
    "content": "v1 ships July 1",
    "memory_type": "fact",
    "type": "fact",
    "scope_type": "agent",
    "scope_id": "agent-1",
    "actor_id": "agent-1",
    "source": "user",
    "confidence": 0.9,
    "status": "active",
    "agent_id": "agent-1",
    "created_at": "2026-06-10T00:00:00Z",
    "updated_at": "2026-06-10T00:00:00Z",
    "metadata": {
        "id": "mem_target",
        "type": "fact",
        "title": "Ship date",
        "agent_id": "agent-1",
        "actor_id": "agent-1",
        "source": "user",
        "confidence": 0.9,
        "status": "active",
    },
}


def _build_service() -> tuple[MemoryWriteService, MagicMock]:
    """Wire a MemoryWriteService with a spy on its validation_service.

    The moorcheh client is a MagicMock — we don't need a real backend because
    the test only asserts that validate_memory is invoked and its result is
    surfaced in the response. The upload call's return value is stubbed.
    """
    fake_client = MagicMock()
    fake_client.documents.upload.return_value = {"status": "uploaded"}

    service = MemoryWriteService(moorcheh_client=fake_client)

    # Replace validate_memory with a spy.
    service.validation_service = MagicMock(spec=MemoryValidationService)
    service.validation_service.validate_memory.return_value = {
        "action": "supersede",
        "reason": "contradiction resolved: superseded mem_old_active",
        "superseded_ids": ["mem_old_active"],
    }
    return service, service.validation_service


def test_update_memory_invokes_validate_memory():
    """update_memory MUST call validate_memory on the updated record.

    This is the contract that store_memory and batch_store_memories enforce,
    and that update_memory skipped via the hardcoded MVP-stub (line 430 of
    memory_write_service.py as of commit c4e3401). Without this call, a
    PATCH can introduce contradictions without supersession — the exact
    "fails to resolve contradictions" failure the bounty names.
    """
    service, validation_spy = _build_service()

    with patch(
        "memanto.app.services.memory_read_service.MemoryReadService.get_memory",
        return_value=_EXISTING_TARGET,
    ):
        service.update_memory(
            memory_id="mem_target",
            namespace="memanto_agent_agent-1",
            updates={"content": "v1 ships August 1"},  # contradicts July 1
            context={"actor_id": "agent-1"},
        )

    assert validation_spy.validate_memory.called, (
        "update_memory must route the updated record through "
        "MemoryValidationService.validate_memory so that contradictions "
        "with existing active memories are detected and resolved. "
        "Currently it skips this (hardcoded MVP-stub), allowing two "
        "active contradictory same-title memories to coexist."
    )


def test_update_memory_surfaces_superseded_ids():
    """When validate_memory resolves a contradiction, the response must
    carry `superseded_ids` so the caller knows what was superseded —
    mirroring store_memory's behavior at memory_write_service.py:121-122.
    """
    service, _ = _build_service()

    with patch(
        "memanto.app.services.memory_read_service.MemoryReadService.get_memory",
        return_value=_EXISTING_TARGET,
    ):
        result = service.update_memory(
            memory_id="mem_target",
            namespace="memanto_agent_agent-1",
            updates={"content": "v1 ships August 1"},
            context={"actor_id": "agent-1"},
        )

    assert "superseded_ids" in result, (
        "update_memory response must include `superseded_ids` when "
        "validate_memory resolved a contradiction, matching store_memory's "
        "contract. Without it, callers (UI, conflict dashboard, audit log) "
        "cannot see what was superseded on update."
    )
    assert result["superseded_ids"] == ["mem_old_active"]


def test_update_memory_reports_validation_action():
    """The response `validation` field must reflect the real validate_memory
    action (e.g. 'supersede') rather than the hardcoded 'store' stub.
    """
    service, _ = _build_service()

    with patch(
        "memanto.app.services.memory_read_service.MemoryReadService.get_memory",
        return_value=_EXISTING_TARGET,
    ):
        result = service.update_memory(
            memory_id="mem_target",
            namespace="memanto_agent_agent-1",
            updates={"content": "v1 ships August 1"},
            context={"actor_id": "agent-1"},
        )

    assert result["validation"] == "supersede", (
        "When validate_memory returns action='supersede', the response's "
        "`validation` field must reflect that (not the hardcoded 'store'). "
        "Audit logs and conflict dashboards read this field."
    )
