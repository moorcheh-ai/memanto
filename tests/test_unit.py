import pytest
from datetime import datetime
from memanto.core.memory_record import MemoryRecord
from memanto.core.memory_write_service import MemoryWriteService
from memanto.core.memory_storage import MemoryStorage

class TestMemoryWriteService:
    @pytest.fixture
    def mock_storage(self, mocker):
        storage = mocker.Mock(spec=MemoryStorage)
        return storage

    @pytest.fixture
    def write_service(self, mock_storage):
        return MemoryWriteService(mock_storage)

    def test_update_memory_preserves_existing_provenance(self, write_service, mock_storage):
        # Setup
        memory_id = "test_memory"
        existing_memory = MemoryRecord(
            id=memory_id,
            content="Original content",
            metadata={"key": "value"},
            provenance="validated",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        mock_storage.get_memory.return_value = existing_memory
        mock_storage.update_memory.return_value = True

        # Test partial update without provenance
        update_data = {"content": "Updated content"}
        result = write_service.update_memory(memory_id, update_data)

        # Verify
        assert result is not None
        assert result.provenance == "validated"  # Should preserve existing provenance
        assert result.content == "Updated content"  # Should update content
        assert result.metadata == {"key": "value"}  # Should preserve metadata

        # Test update with explicit provenance
        update_data_with_provenance = {
            "content": "Another update",
            "provenance": "corrected"
        }
        result_with_provenance = write_service.update_memory(memory_id, update_data_with_provenance)

        assert result_with_provenance is not None
        assert result_with_provenance.provenance == "corrected"  # Should use explicit provenance
        assert result_with_provenance.content == "Another update"