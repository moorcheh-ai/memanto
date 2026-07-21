import pytest
from memanto.models.memory_record import MemoryStatus
from memanto.services.okf_import import map_okf

def test_import_preserves_status():
    okf_data = {
        "x_memanto": {
            "status": "superseded",
            # ... other fields ...
        }
    }
    memory = map_okf(okf_data)
    assert memory.status == MemoryStatus.SUPERSEDED

def test_import_falls_back_to_active():
    okf_data = {
        "x_memanto": {
            "status": "invalid_status",
            # ... other fields ...
        }
    }
    memory = map_okf(okf_data)
    assert memory.status == MemoryStatus.ACTIVE