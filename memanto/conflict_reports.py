import os
from pathlib import Path
from typing import List, Optional

from memanto.config import get_data_dir

def get_conflicts_dir() -> Path:
    """Get the directory where conflict reports are stored, scoped to the active backend."""
    data_dir = get_data_dir()
    conflicts_dir = data_dir / "conflicts"
    conflicts_dir.mkdir(parents=True, exist_ok=True)
    return conflicts_dir

def list_conflicts() -> List[Path]:
    """List all conflict reports in the active backend's conflict directory."""
    conflicts_dir = get_conflicts_dir()
    return list(conflicts_dir.glob("*.json"))

def get_conflict_path(agent_id: str, date: str) -> Path:
    """Get the path to a conflict report for a specific agent and date."""
    conflicts_dir = get_conflicts_dir()
    return conflicts_dir / f"{agent_id}_{date}.json"

def resolve_conflict(agent_id: str, date: str) -> None:
    """Mark a conflict as resolved by renaming the report file."""
    conflict_path = get_conflict_path(agent_id, date)
    resolved_path = conflict_path.with_suffix(".resolved.json")
    conflict_path.rename(resolved_path)

def get_latest_conflict(agent_id: str) -> Optional[Path]:
    """Get the latest conflict report for a specific agent."""
    conflicts_dir = get_conflicts_dir()
    conflict_files = sorted(conflicts_dir.glob(f"{agent_id}_*.json"), reverse=True)
    return conflict_files[0] if conflict_files else None