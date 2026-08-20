"""Security regression tests for authoritative conflict-reference binding."""

from __future__ import annotations

import copy

import pytest

from memanto.app.utils.conflict_binding import (
    bind_conflict_references,
    extract_recent_memory_ids,
    validate_conflict_reference_binding,
)

_NAMESPACE = "memanto_agent_agent-1"
_OTHER_NAMESPACE = "memanto_agent_agent-2"


class _Documents:
    """Namespace-aware fake document API used by binding tests."""

    def __init__(self, stores: dict[str, dict[str, dict]], *, fail_reads: bool = False):
        """Initialize per-namespace document stores and optional read failure mode."""
        self.stores = stores
        self.fail_reads = fail_reads

    def get(self, *, namespace_name: str, ids: list[str]):
        """Return documents only from the requested namespace."""
        if self.fail_reads:
            raise RuntimeError("simulated backend read failure")
        item = self.stores.get(namespace_name, {}).get(ids[0])
        return {"items": [copy.deepcopy(item)] if item else []}


class _Client:
    """Minimal namespace-aware fake Moorcheh client."""

    def __init__(self, stores: dict[str, dict[str, dict]], *, fail_reads: bool = False):
        """Expose the fake documents endpoint expected by MemoryReadService."""
        self.documents = _Documents(stores, fail_reads=fail_reads)


def _doc(memory_id: str, title: str, content: str, *, agent_id: str = "agent-1") -> dict:
    """Build one fake stored memory document."""
    return {
        "id": memory_id,
        "text": f"[FACT] {title}\n\n{content}",
        "memory_type": "fact",
        "agent_id": agent_id,
        "actor_id": agent_id,
        "source": "user",
        "confidence": 0.9,
        "status": "active",
        "provenance": "explicit_statement",
        "created_at": "2026-08-20T10:00:00+00:00",
        "updated_at": "2026-08-20T10:00:00+00:00",
    }


def _client_with(*docs: dict) -> _Client:
    """Build a client whose supplied memories exist in the primary test namespace."""
    return _Client({_NAMESPACE: {doc["id"]: doc for doc in docs}})


def test_extract_recent_memory_ids_from_session_markdown():
    """Extract only memory IDs that are actually present in session markdown."""
    text = """
### [2026-08-20 10:00:00] [FACT] One
- **Memory ID**: `new-1`
- **Content**:
> hello

### [2026-08-20 10:01:00] [FACT] Two
- **Memory ID**: `new-2`
"""
    assert extract_recent_memory_ids(text) == {"new-1", "new-2"}


def test_binding_replaces_spoofed_llm_content_with_authoritative_memory():
    """Replace model-authored display text with authoritative stored content."""
    client = _client_with(
        _doc("old-1", "Real old", "Authoritative old content"),
        _doc("new-1", "Real new", "Authoritative new content"),
    )
    conflicts = [
        {
            "old_memory_id": "old-1",
            "old_content": "harmless fake display",
            "new_memory_id": "new-1",
            "new_content": "another fake display",
        }
    ]

    bound = bind_conflict_references(
        conflicts,
        client=client,
        namespace=_NAMESPACE,
        recent_memory_ids={"new-1"},
    )

    assert bound[0]["old_content"] == "Authoritative old content"
    assert bound[0]["new_content"] == "Authoritative new content"
    assert bound[0]["_reference_binding"]["status"] == "bound"
    validate_conflict_reference_binding(bound[0], client=client, namespace=_NAMESPACE)


def test_binding_blocks_model_selected_new_id_not_in_recent_session():
    """Block a model-selected new memory that was not part of the analyzed session."""
    client = _client_with(
        _doc("old-1", "Old", "old"),
        _doc("unrelated-9", "Unrelated", "do not delete"),
    )
    [conflict] = bind_conflict_references(
        [
            {
                "old_memory_id": "old-1",
                "new_memory_id": "unrelated-9",
                "old_content": "fake",
                "new_content": "fake",
            }
        ],
        client=client,
        namespace=_NAMESPACE,
        recent_memory_ids={"new-1"},
    )

    assert conflict["_reference_binding"] == {
        "status": "blocked",
        "reason": "new_memory_not_in_recent_session",
    }
    with pytest.raises(ValueError, match="not server-verified"):
        validate_conflict_reference_binding(conflict, client=client, namespace=_NAMESPACE)


def test_binding_blocks_missing_old_memory_id_without_backend_read():
    """Fail closed immediately when the model omits the old memory ID."""
    client = _Client({_NAMESPACE: {}}, fail_reads=True)
    [conflict] = bind_conflict_references(
        [{"new_memory_id": "new-1"}],
        client=client,
        namespace=_NAMESPACE,
        recent_memory_ids={"new-1"},
    )
    assert conflict["_reference_binding"] == {
        "status": "blocked",
        "reason": "missing_old_memory_id",
    }


def test_binding_blocks_cross_namespace_memory_reference():
    """Reject an ID that exists only in another agent namespace."""
    stores = {
        _NAMESPACE: {"new-1": _doc("new-1", "New", "new")},
        _OTHER_NAMESPACE: {
            "old-foreign": _doc("old-foreign", "Foreign", "must remain isolated", agent_id="agent-2")
        },
    }
    client = _Client(stores)
    [conflict] = bind_conflict_references(
        [{"old_memory_id": "old-foreign", "new_memory_id": "new-1"}],
        client=client,
        namespace=_NAMESPACE,
        recent_memory_ids={"new-1"},
    )
    assert conflict["_reference_binding"] == {
        "status": "blocked",
        "reason": "old_memory_not_found_in_agent_namespace",
    }


def test_binding_backend_read_failure_blocks_instead_of_aborting_report():
    """Convert transient authoritative-read failures into a blocked conflict."""
    client = _Client({_NAMESPACE: {}}, fail_reads=True)
    [conflict] = bind_conflict_references(
        [{"old_memory_id": "old-1", "new_memory_id": "new-1"}],
        client=client,
        namespace=_NAMESPACE,
        recent_memory_ids={"new-1"},
    )
    assert conflict["_reference_binding"]["status"] == "blocked"
    assert conflict["_reference_binding"]["reason"] == "old_memory_not_found_in_agent_namespace"


def test_validation_detects_report_id_tampering():
    """Reject conflict IDs that were changed after server-side binding."""
    client = _client_with(
        _doc("old-1", "Old", "old"),
        _doc("new-1", "New", "new"),
        _doc("victim", "Victim", "must survive"),
    )
    [conflict] = bind_conflict_references(
        [{"old_memory_id": "old-1", "new_memory_id": "new-1"}],
        client=client,
        namespace=_NAMESPACE,
        recent_memory_ids={"new-1"},
    )
    conflict["old_memory_id"] = "victim"

    with pytest.raises(ValueError, match="changed after validation"):
        validate_conflict_reference_binding(conflict, client=client, namespace=_NAMESPACE)


def test_validation_detects_memory_changed_after_report_generation():
    """Reject an authoritative memory whose content changed after report generation."""
    stores = {
        _NAMESPACE: {
            "old-1": _doc("old-1", "Old", "old"),
            "new-1": _doc("new-1", "New", "new"),
        }
    }
    client = _Client(stores)
    [conflict] = bind_conflict_references(
        [{"old_memory_id": "old-1", "new_memory_id": "new-1"}],
        client=client,
        namespace=_NAMESPACE,
        recent_memory_ids={"new-1"},
    )
    stores[_NAMESPACE]["old-1"] = _doc("old-1", "Old", "mutated after report")

    with pytest.raises(ValueError, match="changed after report generation"):
        validate_conflict_reference_binding(conflict, client=client, namespace=_NAMESPACE)


def test_validation_fails_closed_after_referenced_memory_is_deleted():
    """Reject resolution when a previously bound memory disappears before mutation."""
    stores = {
        _NAMESPACE: {
            "old-1": _doc("old-1", "Old", "old"),
            "new-1": _doc("new-1", "New", "new"),
        }
    }
    client = _Client(stores)
    [conflict] = bind_conflict_references(
        [{"old_memory_id": "old-1", "new_memory_id": "new-1"}],
        client=client,
        namespace=_NAMESPACE,
        recent_memory_ids={"new-1"},
    )
    del stores[_NAMESPACE]["old-1"]

    with pytest.raises(ValueError, match="no longer exists"):
        validate_conflict_reference_binding(conflict, client=client, namespace=_NAMESPACE)
