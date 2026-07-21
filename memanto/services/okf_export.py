from typing import Dict, Any
from memanto.models.memory_record import MemoryRecord
from memanto.services.okf_export import OkfExportService

class OkfExportService:
    def _build_extension(self, memory: MemoryRecord) -> Dict[str, Any]:
        """Build the x_memanto extension block for OKF export."""
        extension = {
            "status": memory.status.value if memory.status else "active",
            # ... other existing fields ...
        }
        return extension