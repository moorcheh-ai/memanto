from memanto.app.core import MemoryRecord
from memanto.app.services.memory_read_service import MemoryReadService


def _round_trip(content: str, tags: list[str]) -> dict:
    memory = MemoryRecord(
        type="preference",
        title="Travel preference",
        content=content,
        agent_id="agent-1",
        actor_id="user-1",
        source="user",
        tags=tags,
    )
    document = memory.to_moorcheh_document()
    return MemoryReadService(object())._format_memory_item(document)


def test_tagged_multi_paragraph_content_round_trips_without_generated_footer():
    original = "Prefers aisle seats.\n\nAvoids overnight flights."

    formatted = _round_trip(original, ["travel", "flights"])

    assert formatted["title"] == "Travel preference"
    assert formatted["content"] == original
    assert formatted["tags"] == ["travel", "flights"]


def test_user_authored_tags_paragraph_is_preserved():
    original = "Checklist for the trip:\n\nTags: travel, flights"

    formatted = _round_trip(original, ["travel", "flights"])

    assert formatted["content"] == original


def test_tags_like_content_is_untouched_without_metadata_tags():
    original = "Notes from the importer.\n\nTags: legacy, unverified"

    formatted = _round_trip(original, [])

    assert formatted["content"] == original
    assert formatted["tags"] == []


def test_multiline_title_keeps_type_prefix_out_of_formatted_title():
    memory = MemoryRecord(
        type="preference",
        title="Travel\npreference",
        content="Prefers aisle seats.",
        agent_id="agent-1",
        actor_id="user-1",
        source="user",
    )

    formatted = MemoryReadService(object())._format_memory_item(
        memory.to_moorcheh_document()
    )

    assert formatted["title"] == "Travel\npreference"
