from typing import Dict, Any
from memanto.models.memory_record import MemoryRecord, MemoryStatus
from memanto.services.okf_import import map_okf

def map_okf(okf_data: Dict[str, Any]) -> MemoryRecord:
    """Map OKF data to a MemoryRecord, preserving lifecycle status."""
    status_value = okf_data.get("x_memanto", {}).get("status", "active")
    try:
        status = MemoryStatus(status_value)
    except ValueError:
        status = MemoryStatus.ACTIVE

    memory = MemoryRecord(
        # ... other fields ...
        status=status,
    )
    return memory