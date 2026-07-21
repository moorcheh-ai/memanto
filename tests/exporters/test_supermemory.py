import pytest
from datetime import datetime
from memanto.exporters.supermemory import SupermemoryExporter
from memanto.models import Memory

@pytest.fixture
def exporter():
    return SupermemoryExporter({})

def test_multiple_tags_preservation(exporter):
    # Create memories with the same ID but different tags
    memory1 = Memory(
        id="mem1",
        content="Test memory",
        container_tags=["project-a"],
        created_at=datetime.now(),
        updated_at=datetime.now()
    )

    memory2 = Memory(
        id="mem1",
        content="Test memory",
        container_tags=["project-b"],
        created_at=datetime.now(),
        updated_at=datetime.now()
    )

    # Export both memories
    exporter.export_memory(memory1)
    exporter.export_memory(memory2)

    # Finalize export
    result = exporter.finalize_export()

    # Verify canonical export contains both tags
    assert len(result["memories"]) == 1
    assert set(result["memories"][0]["container_tags"]) == {"project-a", "project-b"}

    # Verify per-tag buckets contain the memory
    assert "project-a" in result["memories_by_container_tag"]
    assert "project-b" in result["memories_by_container_tag"]

    # Verify each bucket has the memory with its singular tag
    for tag in ["project-a", "project-b"]:
        memories = result["memories_by_container_tag"][tag]
        assert len(memories) == 1
        assert memories[0]["id"] == "mem1"
        assert memories[0]["container_tag"] == tag