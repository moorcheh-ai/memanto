import pytest
from pydantic import ValidationError

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_read_service import MemoryReadService


def build_memory(tags: list[str]) -> MemoryRecord:
    return MemoryRecord(
        title="Tag fidelity test",
        content="Tags must remain accurate.",
        agent_id="agent-1",
        actor_id="user-1",
        source="system",
        tags=tags,
    )


def test_tag_containing_comma_is_rejected_before_storage():
    with pytest.raises(
        ValidationError,
        match="tag values must not contain commas",
    ):
        build_memory(["customer,priority"])


def test_separate_tags_survive_round_trip():
    original = build_memory(["customer", "priority"])

    stored = original.to_moorcheh_document()

    restored = MemoryReadService(object())._format_memory_item(stored)

    assert restored["tags"] == original.tags
