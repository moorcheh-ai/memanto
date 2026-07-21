import pytest
from datetime import datetime
from memanto.mappers.supermemory import SupermemoryMapper
from memanto.models import Memory

@pytest.fixture
def mapper():
    return SupermemoryMapper()

def test_legacy_tag_mapping(mapper):
    # Test with legacy container_tag format
    memory_data = {
        "id": "mem1",
        "content": "Test memory",
        "container_tag": "project-a",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    mapped = mapper.map_memory(memory_data)
    assert isinstance(mapped, Memory)
    assert mapped.container_tags == ["project-a"]

def test_current_tags_mapping(mapper):
    # Test with current container_tags array format
    memory_data = {
        "id": "mem1",
        "content": "Test memory",
        "container_tags": ["project-a", "project-b"],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    mapped = mapper.map_memory(memory_data)
    assert isinstance(mapped, Memory)
    assert set(mapped.container_tags) == {"project-a", "project-b"}

def test_mixed_tag_formats_mapping(mapper):
    # Test with both formats
    memory_data = {
        "id": "mem1",
        "content": "Test memory",
        "container_tags": ["project-a"],
        "container_tag": "project-b",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    mapped = mapper.map_memory(memory_data)
    assert isinstance(mapped, Memory)
    assert set(mapped.container_tags) == {"project-a", "project-b"}