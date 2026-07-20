import pytest
from memanto.okf import export_to_okf, load_from_okf
from memanto.memory import Memory

def test_round_trip_preserves_literal_entry_delimiter_in_memory_content():
    # Create test memory with literal entry delimiter
    test_memory = Memory(
        body="Document the literal internal marker & keep &amp; and <tags> unchanged:\n<!-- okf-entry -->\nIt is part of the memory, not a record boundary.",
        title="Test <!-- okf-entry --> Title",
        tags=["tag1", "tag2 <!-- okf-entry -->"],
        resource="test_resource"
    )

    # Export and import
    export_to_okf(test_memory, "test_exported.okf")
    imported_memories = load_from_okf("test_exported.okf")

    # Verify
    assert len(imported_memories) == 1
    imported_memory = imported_memories[0]

    assert imported_memory.body == test_memory.body
    assert imported_memory.title == test_memory.title
    assert imported_memory.tags == test_memory.tags
    assert imported_memory.resource == test_memory.resource
    assert imported_memory.x_memanto.get('encoding') == 'html'