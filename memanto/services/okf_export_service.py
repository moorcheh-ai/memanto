import os
from pathlib import Path
from typing import Optional

from memanto.config import get_data_dir

class OkfExportService:
    def __init__(self, exports_dir: Optional[str] = None):
        self.exports_dir = exports_dir or os.path.join(get_data_dir(), "exports")

    def export_okf(self, agent_id: str, okf_data: dict) -> str:
        """Export OKF data to the backend-specific exports directory."""
        os.makedirs(self.exports_dir, exist_ok=True)
        export_path = os.path.join(self.exports_dir, f"{agent_id}_okf")
        with open(export_path, "w") as f:
            f.write(str(okf_data))
        return export_path