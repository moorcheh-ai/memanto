from fastapi import FastAPI, HTTPException
from pathlib import Path
from typing import List, Optional

from memanto.conflict_reports import (
    get_conflict_path,
    list_conflicts,
    resolve_conflict,
    get_latest_conflict,
)

app = FastAPI()

@app.post("/conflicts/generate")
def generate_conflict_report(agent_id: str, date: str):
    """Generate a conflict report for a specific agent and date."""
    conflict_path = get_conflict_path(agent_id, date)
    # Generate conflict report logic here
    return {"message": "Conflict report generated", "path": str(conflict_path)}

@app.get("/conflicts/list")
def list_conflicts():
    """List all conflict reports for the active backend."""
    conflicts = list_conflicts()
    return {"conflicts": [str(conflict) for conflict in conflicts]}

@app.post("/conflicts/resolve")
def resolve_conflict(agent_id: str, date: str):
    """Mark a conflict as resolved."""
    resolve_conflict(agent_id, date)
    return {"message": f"Conflict resolved for agent {agent_id} on date {date}"}

@app.get("/conflicts/latest")
def get_latest_conflict(agent_id: str):
    """Get the latest conflict report for a specific agent."""
    latest_conflict = get_latest_conflict(agent_id)
    if latest_conflict:
        return {"latest_conflict": str(latest_conflict)}
    else:
        raise HTTPException(status_code=404, detail="No conflict reports found for the specified agent.")