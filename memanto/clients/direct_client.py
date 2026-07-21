import os
from pathlib import Path
from typing import Optional

from memanto.config import get_data_dir
from memanto.services.okf_export_service import OkfExportService

class DirectClient:
    def __init__(self, agent_id: str, exports_dir: Optional[str] = None):
        self.agent_id = agent_id
        self.exports_dir = exports_dir or os.path.join(get_data_dir(), "exports")
        self.okf_export_service = OkfExportService(exports_dir)

    def sync_okf_to_project(self) -> bool:
        """Sync OKF data from the backend-specific cache to the project."""
        cache_path = os.path.join(self.exports_dir, f"{self.agent_id}_okf")
        if os.path.exists(cache_path):
            with open(cache_path, "r") as f:
                okf_data = f.read()
            # Process OKF data and sync to project
            return True
        return False