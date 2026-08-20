from __future__ import annotations

import copy

import pytest

from memanto.app.utils.conflict_binding import (
    bind_conflict_references,
    extract_recent_memory_ids,
    validate_conflict_reference_binding,
)


class _Documents:
    def __init__(self, store: dict[str, dict]):
        self.store = store

    def get(self, *, namespace_name: str, ids: list[str]):
        item = self.store.get(ids[0])
        return {"items": [copy.deepcopy(item)] if item else []}


class _Client:
    def __init__(self, store: dict[str, dict]):
        self.documents = _Documents(store)


def _doc(memory_id: str, title: str, content: str) -> dict:
    return {
        "id": memory_id,
        "text": f"[FACT] {title}\n\n{content}",
        "memory_type": "fact",
        "agent_id": "agent-1",
        "actor_id": "agent-1",
        "source": "user",
        "confidence": 0.9,
        "status": "active",
        "provenance": "explicit_statement",
        "created_at": "2026-08-20T10:00:00+00:00",
        "updated_at": "2026-08-20T10:00:00+00:00",
    }


def test_extract_recent_memory_ids_from_session_markdown():
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
    client = _Client(
        {
            "old-1": _doc("old-1", "Real old", "Authoritative old content"),
            "new-1": _doc("new-1", "Real new", "Authoritative new content"),
        }
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
        namespace="memanto_agent_agent-1",
        recent_memory_ids={"new-1"},
    )

    assert bound[0]["old_content"] == "Authoritative old content"
    assert bound[0]["new_content"] == "Authoritative new content"
    assert bound[0]["_reference_binding"]["status"] == "bound"
    validate_conflict_reference_binding(
        bound[0], client=client, namespace="memanto_agent_agent-1"
    )


def test_binding_blocks_model_selected_new_id_not_in_recent_session():
    client = _Client(
        {
            "old-1": _doc("old-1", "Old", "old"),
            "unrelated-9": _doc("unrelated-9", "Unrelated", "do not delete"),
        }
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
        namespace="memanto_agent_agent-1",
        recent_memory_ids={"new-1"},
    )

    assert conflict["_reference_binding"] == {
        "status": "blocked",
        "reason": "new_memory_not_in_recent_session",
    }
    with pytest.raises(ValueError, match="not server-verified"):
        validate_conflict_reference_binding(
            conflict, client=client, namespace="memanto_agent_agent-1"
        )


def test_validation_detects_report_id_tampering():
    client = _Client(
        {
            "old-1": _doc("old-1", "Old", "old"),
            "new-1": _doc("new-1", "New", "new"),
            "victim": _doc("victim", "Victim", "must survive"),
        }
    )
    [conflict] = bind_conflict_references(
        [{"old_memory_id": "old-1", "new_memory_id": "new-1"}],
        client=client,
        namespace="memanto_agent_agent-1",
        recent_memory_ids={"new-1"},
    )
    conflict["old_memory_id"] = "victim"

    with pytest.raises(ValueError, match="changed after validation"):
        validate_conflict_reference_binding(
            conflict, client=client, namespace="memanto_agent_agent-1"
        )


def test_validation_detects_memory_changed_after_report_generation():
    store = {
        "old-1": _doc("old-1", "Old", "old"),
        "new-1": _doc("new-1", "New", "new"),
    }
    client = _Client(store)
    [conflict] = bind_conflict_references(
        [{"old_memory_id": "old-1", "new_memory_id": "new-1"}],
        client=client,
        namespace="memanto_agent_agent-1",
        recent_memory_ids={"new-1"},
    )
    store["old-1"] = _doc("old-1", "Old", "mutated after report")

    with pytest.raises(ValueError, match="changed after report generation"):
        validate_conflict_reference_binding(
            conflict, client=client, namespace="memanto_agent_agent-1"
        )
