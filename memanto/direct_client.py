from pathlib import Path
from typing import List, Optional

from memanto.conflict_reports import (
    get_conflict_path,
    list_conflicts,
    resolve_conflict,
    get_latest_conflict,
)

class DirectClient:
    def __init__(self, backend: str):
        self.backend = backend

    def generate_conflict_report(self, agent_id: str, date: str) -> Path:
        """Generate a conflict report for a specific agent and date."""
        conflict_path = get_conflict_path(agent_id, date)
        # Generate conflict report logic here
        return conflict_path

    def list_conflicts(self) -> List[Path]:
        """List all conflict reports for the active backend."""
        return list_conflicts()

    def resolve_conflict(self, agent_id: str, date: str) -> None:
        """Mark a conflict as resolved."""
        resolve_conflict(agent_id, date)

    def get_latest_conflict(self, agent_id: str) -> Optional[Path]:
        """Get the latest conflict report for a specific agent."""
        return get_latest_conflict(agent_id)