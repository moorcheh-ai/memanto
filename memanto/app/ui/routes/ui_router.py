"""
MEMANTO Web UI Router

Serves the Web UI static files and provides UI-specific API endpoints.
"""

import os
import signal
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from memanto.app.config import settings
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.config.manager import ConfigManager

router = APIRouter()

# Shared ConfigManager instance (reads from ~/.memanto/)
_config_manager = ConfigManager()

# Path to the static directory
STATIC_DIR = Path(__file__).parent.parent / "static"


@router.get("/api/ui/config")
async def get_ui_config():
    """
    Get current MEMANTO configuration for the Web UI.

    Returns non-sensitive configuration: API key status (masked),
    server URL, active agent, session settings, CLI settings.
    """
    api_key = _config_manager.get_api_key()
    server_cfg = _config_manager.get_server_config()
    session_cfg = _config_manager.get_session_config()
    cli_cfg = _config_manager.get_cli_config()
    answer_cfg = _config_manager.get_answer_config()
    recall_cfg = _config_manager.get_recall_config()
    schedule_time = _config_manager.get_schedule_time()
    active_agent_id, active_session_token = _config_manager.get_active_session()

    return {
        "api_key_configured": bool(api_key),
        "api_key_preview": f"........{api_key[-6:]}"
        if api_key and len(api_key) > 6
        else ("***" if api_key else None),
        "api_key": api_key,
        "server": {
            "url": server_cfg.get("url", "localhost"),
            "port": server_cfg.get("port", 8000),
            "auto_start": server_cfg.get("auto_start", False),
        },
        "session": session_cfg,
        "cli": cli_cfg,
        "answer": answer_cfg,
        "recall": recall_cfg,
        "schedule_time": schedule_time,
        "active_agent_id": active_agent_id,
        "session_token": active_session_token,
        "has_active_session": bool(active_session_token),
        "ui_mode": settings.MEMANTO_UI_MODE,
    }


@router.patch("/api/ui/config")
async def update_ui_config(updates: dict):
    """
    Update non-sensitive MEMANTO configuration from the Web UI.

    Accepts: schedule_time, session settings, CLI settings, answer settings, recall settings.
    Does NOT allow updating API key or active session through this endpoint.
    """
    allowed_keys = {"schedule_time", "session", "cli", "server", "answer", "recall"}
    rejected = set(updates.keys()) - allowed_keys
    if rejected:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update keys: {', '.join(rejected)}. Allowed: {', '.join(allowed_keys)}",
        )

    if "schedule_time" in updates:
        _config_manager.set_schedule_time(updates["schedule_time"])

    if "session" in updates and isinstance(updates["session"], dict):
        data = _config_manager.load_yaml()
        if "session" not in data:
            data["session"] = {}
        data["session"].update(updates["session"])
        _config_manager.save_yaml(data)

    if "cli" in updates and isinstance(updates["cli"], dict):
        data = _config_manager.load_yaml()
        if "cli" not in data:
            data["cli"] = {}
        data["cli"].update(updates["cli"])
        _config_manager.save_yaml(data)

    if "server" in updates and isinstance(updates["server"], dict):
        data = _config_manager.load_yaml()
        if "server" not in data:
            data["server"] = {}
        data["server"].update(updates["server"])
        _config_manager.save_yaml(data)

    if "answer" in updates and isinstance(updates["answer"], dict):
        ans = updates["answer"]
        _config_manager.set_answer_config(
            model=ans.get("model"),
            temperature=float(ans["temperature"]) if "temperature" in ans else None,
            answer_limit=int(ans["answer_limit"]) if "answer_limit" in ans else None,
            threshold=float(ans["threshold"]) if "threshold" in ans else None,
        )

    if "recall" in updates and isinstance(updates["recall"], dict):
        rec = updates["recall"]
        _config_manager.set_recall_config(
            limit=int(rec["limit"]) if "limit" in rec else None
        )

    return {"status": "updated", "updated_keys": list(updates.keys())}


@router.put("/api/ui/api-key")
async def update_api_key(body: dict):
    """
    Update the Moorcheh API key from the Web UI.
    Expects: {"api_key": "new-key-value"}
    """
    new_key = body.get("api_key", "").strip()
    if not new_key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")
    _config_manager.set_api_key(new_key)
    preview = f"••••••••{new_key[-6:]}" if len(new_key) > 6 else "***"
    return {"status": "updated", "api_key_preview": preview}


@router.get("/api/ui/conflicts")
async def list_conflicts(agent_id: str | None = None, date: str | None = None):
    """
    List unresolved conflicts for an agent.
    Uses DirectClient.list_conflicts under the hood.
    """
    from datetime import datetime as dt

    if not agent_id:
        aid, _ = _config_manager.get_active_session()
        if not aid:
            return {"conflicts": [], "count": 0, "message": "No active agent"}
        agent_id = aid
    if not date:
        date = dt.now().strftime("%Y-%m-%d")

    try:
        api_key = _config_manager.get_api_key()
        if not api_key:
            return {"conflicts": [], "count": 0, "message": "No API key configured"}
        client = DirectClient(api_key)
        _, token = _config_manager.get_active_session()
        if token:
            client.session_token = token
        conflicts = client.list_conflicts(agent_id=agent_id, date=date)
        return {
            "conflicts": conflicts,
            "count": len(conflicts),
            "agent_id": agent_id,
            "date": date,
        }
    except Exception as e:
        return {"conflicts": [], "count": 0, "error": str(e)}


@router.post("/api/ui/conflicts/resolve")
async def resolve_conflict(body: dict):
    """
    Resolve a single conflict.
    Expects: {"agent_id": "...", "date": "...", "conflict_index": 0, "action": "keep_old"|"keep_new"|"keep_both"|"remove_both"|"manual", "manual_content": "..."}
    """
    agent_id = str(body.get("agent_id", ""))
    date = str(body.get("date", ""))
    conflict_index = body.get("conflict_index")
    action = str(body.get("action", ""))
    manual_content = body.get("manual_content")
    if manual_content is not None:
        manual_content = str(manual_content)
    manual_type = body.get("manual_type")
    if manual_type is not None:
        manual_type = str(manual_type)

    if not all([agent_id, date, action]) or conflict_index is None:
        raise HTTPException(
            status_code=400,
            detail="agent_id, date, conflict_index, and action are required",
        )

    try:
        api_key = _config_manager.get_api_key()
        if not api_key:
            raise HTTPException(status_code=400, detail="No API key configured")
        client = DirectClient(api_key)
        _, token = _config_manager.get_active_session()
        if token:
            client.session_token = token
        result = client.resolve_conflict(
            agent_id=agent_id,
            date=date,
            conflict_index=int(conflict_index),
            action=action,
            manual_content=manual_content,
            manual_type=manual_type,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/ui/shutdown")
async def shutdown_server(background_tasks: BackgroundTasks):
    """
    Gracefully shutdown the MEMANTO server.
    Called by the UI when the browser tab is closed.
    """
    if not settings.MEMANTO_UI_MODE:
        return {"status": "ignored", "reason": "Not in UI mode"}

    def kill_server():
        time.sleep(0.5)  # Allow the response to send before killing
        try:
            os.kill(os.getpid(), signal.SIGINT)
        except Exception:
            os._exit(0)

    background_tasks.add_task(kill_server)
    return {"status": "shutting down"}


def get_ui_router():
    """Return the router for inclusion in the main app."""
    return router


def mount_ui_static(app):
    """Mount the static files directory for serving the UI SPA."""
    if STATIC_DIR.exists():
        # Serve index.html for the /ui root
        @app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
        async def serve_ui():
            index_path = STATIC_DIR / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            raise HTTPException(status_code=404, detail="UI not found")

        # Mount static assets (CSS, JS, images) under /ui/static
        app.mount(
            "/ui/static", StaticFiles(directory=str(STATIC_DIR)), name="ui_static"
        )
