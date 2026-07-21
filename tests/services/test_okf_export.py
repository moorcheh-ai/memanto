import pytest
from memanto.models.memory_record import MemoryRecord, MemoryStatus
from memanto.services.okf_export import OkfExportService

def test_export_preserves_status():
    service = OkfExportService()
    memory = MemoryRecord(
        # ... other fields ...
        status=MemoryStatus.SUPERSEDED,
    )
    okf_data = service.export_memory(memory)
    assert okf_data["x_memanto"]["status"] == "superseded"

def test_export_falls_back_to_active():
    service = OkfExportService()
    memory = MemoryRecord(
        # ... other fields ...
        status=None,
    )
    okf_data = service.export_memory(memory)
    assert okf_data["x_memanto"]["status"] == "active"