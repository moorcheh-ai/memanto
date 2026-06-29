"""
MEMANTO Web UI Router

Serves the Web UI static files and provides UI-specific API endpoints.
"""

import ipaddress
import os
import signal
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from memanto.app.clients.backend import Backend
from memanto.app.config import settings
from memanto.cli.client.direct_client import DirectClient
from memanto.cli.config.manager import ConfigManager
from memanto.cli.connect.agent_registry import AGENT_REGISTRY, list_agents
from memanto.cli.connect.engine import install_agent, remove_agent

router = APIRouter()

# Shared ConfigManager instance (reads from ~/.memanto/)
_config_manager = ConfigManager()

# Path to the static directory
STATIC_DIR = Path(__file__).parent.parent / "static"


def _is_loopback(host: str | None) -> bool:
    """Return True if *host* is any loopback address (IPv4, IPv6, or IPv4-mapped IPv6)."""
    if host is None:
        return False
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_loopback:
            return True
        # ::ffff:127.0.0.1 – IPv4-mapped IPv6 – is_loopback returns False
        ipv4_mapped = getattr(addr, "ipv4_mapped", None)
        return ipv4_mapped is not None and ipv4_mapped.is_loopback
    except ValueError:
        return False


async def _require_local(request: Request) -> None:
    """Reject requests that do not originate from the loopback interface.

    UI management endpoints (shutdown, browse, config update, API key update)
    are designed for local desktop use only.  Allowing them from arbitrary
    network addresses would let any reachable host kill the server, enumerate
    the filesystem, or replace API credentials without authentication.
    """
    client_host = request.client.host if request.client else None
    if not _is_loopback(client_host):
        raise HTTPException(
            status_code=403,
            detail=(
                "UI management endpoints are only accessible from localhost. "
                f"Request origin: {client_host}"
            ),
        )



def _build_ui_direct_client() -> DirectClient | None:
    """Build a ``DirectClient`` for UI routes with the active session restored.

    On on-prem we pass an ``"on-prem"`` placeholder — the underlying
    ``OnPremClient`` ignores it and talks to the local stack. On cloud we
    require a real Memanto API key; returns ``None`` when one isn't
    configured so callers can choose their own error shape (HTTP 400 vs
    graceful empty payload).
    """
    if _config_manager.get_backend() == Backend.ON_PREM:
        api_key: str = "on-prem"
    else:
        cfg_key = _config_manager.get_api_key()
        if not cfg_key:
            return None
        api_key = cfg_key
    client = DirectClient(api_key)
    active_agent_id, token = _config_manager.get_active_session()
    if token:
        client.session_token = token
    if active_agent_id:
        client.agent_id = active_agent_id
    return client


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
    backend = _config_manager.get_backend().value
    onprem_cfg = _config_manager.get_onprem_config()

    return {
        "api_key_configured": bool(api_key),
        "api_key_preview": f"........{api_key[-6:]}"
        if api_key and len(api_key) > 6
        else ("***" if api_key else None),
        "backend": backend,
        "on_prem": {
            "url": onprem_cfg.get("url", "http://localhost:8080"),
            "embedding_provider": onprem_cfg.get("embedding_provider", ""),
            "embedding_model": onprem_cfg.get("embedding_model", ""),
            "llm_provider": onprem_cfg.get("llm_provider", ""),
            "llm_model": onprem_cfg.get("llm_model", ""),
        },
        "data_dir": str(_config_manager.get_data_dir()),
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
async def update_ui_config(updates: dict, _: None = Depends(_require_local)):
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
        # On-prem: the Answer panel is provider/model/api_key only — temperature
        # etc. are cloud-only knobs. Persist into state.json (provider/model)
        # and ~/.moorcheh/config.json (full block) without touching the shared
        # cloud yaml's ``answer.*`` namespace.
        if _config_manager.get_backend() == Backend.ON_PREM:
            _update_onprem_answer(ans)
        else:
            _config_manager.set_answer_config(
                model=ans.get("model"),
                temperature=float(ans["temperature"]) if "temperature" in ans else None,
                answer_limit=int(ans["answer_limit"])
                if "answer_limit" in ans
                else None,
                threshold=float(ans["threshold"]) if "threshold" in ans else None,
                kiosk_mode=bool(ans["kiosk_mode"]) if "kiosk_mode" in ans else None,
            )

    if "recall" in updates and isinstance(updates["recall"], dict):
        rec = updates["recall"]
        _config_manager.set_recall_config(
            limit=int(rec["limit"]) if "limit" in rec else None,
            min_similarity=float(rec["min_similarity"])
            if "min_similarity" in rec and rec["min_similarity"] is not None
            else None,
        )

    return {"status": "updated", "updated_keys": list(updates.keys())}


_ONPREM_LLM_PROVIDERS = {"ollama", "openai", "cohere"}


def _update_onprem_answer(ans: dict) -> None:
    """Persist on-prem LLM config: state.json (provider/model) + ``~/.moorcheh/config.json``.

    Does NOT restart the server — the ``/api/ui/onprem/restart`` endpoint owns
    that. Provider/model are required; ``api_key`` is optional for paid
    providers (falls back to whatever is currently in
    ``~/.moorcheh/config.json``) and ignored for ollama.
    """
    from memanto.cli.commands.core import _recover_moorcheh_api_key

    state = _config_manager.get_onprem_state()
    embedding_provider = state.get("embedding_provider")
    embedding_model = state.get("embedding_model")
    if not embedding_provider or not embedding_model:
        raise HTTPException(
            status_code=400,
            detail="On-prem not onboarded — run `memanto config backend on-prem` first.",
        )

    # Provider may be omitted (model-only change); reuse the currently
    # configured provider in that case.
    provider = (ans.get("provider") or state.get("llm_provider") or "").strip().lower()
    model = (ans.get("model") or "").strip()
    api_key = (ans.get("api_key") or "").strip()

    if not provider or not model:
        raise HTTPException(status_code=400, detail="Provider and model are required.")
    if provider not in _ONPREM_LLM_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported on-prem LLM provider: {provider}. "
            f"Allowed: {', '.join(sorted(_ONPREM_LLM_PROVIDERS))}.",
        )

    if provider == "ollama":
        api_key = ""
    elif not api_key:
        # User left the field blank: keep whatever key is already in
        # ~/.moorcheh/config.json (typical case: changing model only).
        api_key = _recover_moorcheh_api_key("llm", provider)
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail=f"{provider} requires an API key — none provided and "
                "none found in ~/.moorcheh/config.json. Enter one and save again.",
            )

    embedding_key = _recover_moorcheh_api_key("embedding", embedding_provider)
    try:
        from moorcheh.user_config import (  # type: ignore[import-not-found]
            EmbeddingConfig,
            LlmConfig,
            default_base_url,
            save_runtime_config,
        )

        save_runtime_config(
            EmbeddingConfig(
                provider=embedding_provider,
                model=embedding_model,
                api_key=embedding_key or None,
                base_url=default_base_url(embedding_provider),
            ),
            LlmConfig(
                provider=provider,
                model=model,
                api_key=api_key or None,
                base_url=default_base_url(provider),
            ),
        )
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"moorcheh-client not installed: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to persist LLM config: {e}"
        )

    _config_manager.set_onprem_state(llm_provider=provider, llm_model=model)


@router.post("/api/ui/onprem/restart")
async def restart_onprem_backend(_: None = Depends(_require_local)):
    """Bounce the on-prem moorcheh stack so it re-reads ``~/.moorcheh/config.json``.

    ``moorcheh down`` + ``moorcheh up`` (with embedding flags recovered from
    state.json / config.json). Blocks for up to ~6 minutes total (5min for
    ``up``, 60s for ``/health``).
    """
    import subprocess

    import httpx as _httpx

    if _config_manager.get_backend() != Backend.ON_PREM:
        raise HTTPException(status_code=400, detail="Active backend is not on-prem.")

    from memanto.cli.commands.core import _recover_moorcheh_api_key

    state = _config_manager.get_onprem_state()
    embedding_provider = state.get("embedding_provider")
    embedding_model = state.get("embedding_model")
    if not embedding_provider or not embedding_model:
        raise HTTPException(
            status_code=400,
            detail="On-prem not onboarded — run `memanto config backend on-prem` first.",
        )
    embedding_key = _recover_moorcheh_api_key("embedding", embedding_provider)

    # `moorcheh down` is best-effort: if the stack isn't running, that's fine —
    # we still want to try `up` after.
    try:
        subprocess.run(
            ["moorcheh", "down"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="`moorcheh` CLI not found on PATH.")
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=500, detail="`moorcheh down` timed out after 60s."
        )

    up_args = [
        "moorcheh",
        "up",
        "--embedding-provider",
        embedding_provider,
        "--embedding-model",
        embedding_model,
    ]
    if embedding_key:
        up_args.extend(["--embedding-api-key", embedding_key])
    try:
        subprocess.run(up_args, check=True, timeout=300)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"`moorcheh up` failed: {e}")
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=500, detail="`moorcheh up` timed out after 5 minutes."
        )

    health_url = (state.get("url") or "http://localhost:8080").rstrip("/") + "/health"
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            resp = _httpx.get(health_url, timeout=2.0)
            if resp.status_code == 200:
                return {"status": "ok", "message": "Server restarted"}
        except Exception:
            pass
        time.sleep(1.0)
    raise HTTPException(
        status_code=500,
        detail=f"Server did not become healthy at {health_url} within 60s.",
    )


@router.put("/api/ui/api-key")
async def update_api_key(body: dict, _: None = Depends(_require_local)):
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
        client = _build_ui_direct_client()
        if client is None:
            return {"conflicts": [], "count": 0, "message": "No API key configured"}
        conflicts = client.list_conflicts(agent_id=agent_id, date=date)
        return {
            "conflicts": conflicts,
            "count": len(conflicts),
            "agent_id": agent_id,
            "date": date,
        }
    except Exception as e:
        return {"conflicts": [], "count": 0, "error": str(e)}


@router.get("/api/ui/conflict-scans")
async def list_conflict_scans(agent_id: str | None = None):
    """
    Return, per day, when the conflict scan last ran for an agent.

    The scan time is the mtime of the per-day conflicts JSON, which is
    (re)written on every scan and every resolution. The UI uses this to flag
    days whose memories were stored after the last scan (possibly unreviewed).
    """
    import json
    import re
    from datetime import datetime as dt

    if not agent_id:
        aid, _ = _config_manager.get_active_session()
        if not aid:
            return {"scans": {}, "agent_id": None}
        agent_id = aid

    conflicts_dir = Path.home() / ".memanto" / "conflicts"
    scans: dict[str, dict] = {}
    if conflicts_dir.exists():
        suffix = "_conflicts.json"
        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for path in conflicts_dir.glob(f"{agent_id}_*{suffix}"):
            # The date is the 10 chars before the fixed suffix — robust to
            # underscores inside agent_id.
            date = path.name[: -len(suffix)][-10:]
            if not date_re.match(date):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    conflicts = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(conflicts, list):
                conflicts = []
            # astimezone() stamps the local offset so the browser compares it
            # as an absolute instant against memory created_at (no TZ skew).
            scanned_at = dt.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
            scans[date] = {
                "scanned_at": scanned_at,
                "conflict_count": len(conflicts),
                "unresolved_count": sum(
                    1 for c in conflicts if not c.get("resolved", False)
                ),
            }
    return {"scans": scans, "agent_id": agent_id}


@router.get("/api/ui/daily-summary")
async def read_daily_summary(agent_id: str | None = None, date: str | None = None):
    """
    Return the existing daily summary for an agent/date if one was already
    generated. Does NOT trigger generation — that's the POST endpoint.

    Response: {exists, agent_id, date, path, content}
    """
    from datetime import datetime as dt

    from memanto.app.config import get_data_dir

    if not agent_id:
        aid, _ = _config_manager.get_active_session()
        if not aid:
            return {"exists": False, "message": "No active agent"}
        agent_id = aid
    if not date:
        date = dt.now().strftime("%Y-%m-%d")

    path = get_data_dir() / "summaries" / f"{agent_id}_{date}.md"
    if not path.exists():
        return {
            "exists": False,
            "agent_id": agent_id,
            "date": date,
            "path": str(path),
        }
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read summary: {e}")
    return {
        "exists": True,
        "agent_id": agent_id,
        "date": date,
        "path": str(path),
        "content": content,
    }


@router.post("/api/ui/daily-summary")
async def generate_daily_summary(body: dict | None = None):
    """
    Trigger an on-demand daily summary for the active agent.
    Expects (optional): {"agent_id": "...", "date": "YYYY-MM-DD",
                         "output_path": "..."}
    """
    from datetime import datetime as dt

    body = body or {}
    agent_id = body.get("agent_id")
    if not agent_id:
        aid, _ = _config_manager.get_active_session()
        if not aid:
            raise HTTPException(status_code=400, detail="No active agent")
        agent_id = aid
    date = body.get("date") or dt.now().strftime("%Y-%m-%d")
    output_path = body.get("output_path")

    client = _build_ui_direct_client()
    if client is None:
        raise HTTPException(status_code=400, detail="No API key configured")

    try:
        result = client.generate_daily_summary(
            agent_id=str(agent_id), date=str(date), output_path=output_path
        )
        return {"agent_id": agent_id, "date": date, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/ui/conflicts/generate")
async def generate_conflict_report(body: dict | None = None):
    """
    Trigger an on-demand conflict report for the active agent. This is the
    same work the scheduled task performs.
    Expects (optional): {"agent_id": "...", "date": "YYYY-MM-DD"}
    """
    from datetime import datetime as dt

    body = body or {}
    agent_id = body.get("agent_id")
    if not agent_id:
        aid, _ = _config_manager.get_active_session()
        if not aid:
            raise HTTPException(status_code=400, detail="No active agent")
        agent_id = aid
    date = body.get("date") or dt.now().strftime("%Y-%m-%d")

    client = _build_ui_direct_client()
    if client is None:
        raise HTTPException(status_code=400, detail="No API key configured")

    try:
        result = client.generate_conflict_report(agent_id=str(agent_id), date=str(date))
        return {"agent_id": agent_id, "date": date, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        client = _build_ui_direct_client()
        if client is None:
            raise HTTPException(status_code=400, detail="No API key configured")
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


@router.get("/api/ui/connections")
async def get_connections():
    """List all supported agents merged with the local connections registry.

    Returns the agent catalog from `agent_registry`, each enriched with what's
    been installed (per registry at `~/.memanto/connections.json`).
    """
    registry = _config_manager.load_connections()
    items: list[dict] = []
    for agent in list_agents():
        entry = registry.get(agent.name, {})
        raw_projects = entry.get("projects", []) if isinstance(entry, dict) else []
        projects = []
        for p in raw_projects:
            path_obj = Path(p)
            projects.append(
                {
                    "path": p,
                    "name": path_obj.name or p,
                    "exists": path_obj.exists() and path_obj.is_dir(),
                }
            )
        items.append(
            {
                "name": agent.name,
                "display_name": agent.display_name,
                "instruction_file": agent.instruction_file,
                "skill_local_template": (
                    f"{agent.skill_local_dir}/memanto"
                    if agent.skill_local_dir
                    else ".agents/skills/memanto"
                ),
                "skill_global_path": (
                    f"{agent.skill_global_dir}/memanto"
                    if agent.skill_global_dir
                    else "~/.agents/skills/memanto"
                ),
                "supports_hooks": agent.supports_hooks,
                "installed_global": bool(entry.get("installed_global"))
                if isinstance(entry, dict)
                else False,
                "projects": projects,
            }
        )
    return {"cwd": str(Path.cwd()), "connections": items}


@router.get("/api/ui/browse")
async def browse_path(
    path: str | None = None,
    _: None = Depends(_require_local),
):
    """List subdirectories of a given path (server-side folder picker).

    Defaults to the user's home directory when ``path`` is missing or invalid.
    Returns child directories only (alphabetical), plus a few quick-path
    shortcuts and the parent path so the UI can build a breadcrumb / up-nav.
    """
    home = Path.home()
    target = Path(path).expanduser() if path else home
    try:
        target = target.resolve()
    except (OSError, RuntimeError):
        target = home

    if not target.exists() or not target.is_dir():
        target = home

    children: list[dict] = []
    try:
        for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            try:
                if entry.is_dir():
                    children.append(
                        {"name": entry.name, "path": str(entry), "is_dir": True}
                    )
            except OSError:
                continue
    except PermissionError:
        children = []
    except OSError:
        children = []

    quick: list[dict] = []
    for label, p in [
        ("Home", home),
        ("Desktop", home / "Desktop"),
        ("Documents", home / "Documents"),
        ("CWD", Path.cwd()),
    ]:
        if p.exists() and p.is_dir():
            quick.append({"label": label, "path": str(p)})

    try:
        parent = str(target.parent) if target.parent != target else None
    except OSError:
        parent = None

    return {
        "path": str(target),
        "parent": parent,
        "exists": True,
        "is_dir": True,
        "children": children,
        "quick_paths": quick,
    }


@router.post("/api/ui/connections/install")
async def connections_install(body: dict, _: None = Depends(_require_local)):
    """Install MEMANTO integration for one or more agents at a given location.

    Body: {"agents": ["claude-code", ...], "project_dir": "/abs/path", "is_global": false}
    """
    agents = body.get("agents") or []
    if not isinstance(agents, list) or not agents:
        raise HTTPException(status_code=400, detail="`agents` must be a non-empty list")
    is_global = bool(body.get("is_global", False))
    project_dir = body.get("project_dir") or "."

    unknown = [a for a in agents if a not in AGENT_REGISTRY]
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"Unknown agent(s): {', '.join(unknown)}"
        )

    if not is_global:
        if not project_dir:
            raise HTTPException(
                status_code=400, detail="`project_dir` is required when not global"
            )
        path_obj = Path(project_dir).expanduser()
        if not path_obj.exists() or not path_obj.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"project_dir does not exist or is not a directory: {project_dir}",
            )
        project_dir = str(path_obj.resolve())

    results = [install_agent(name, project_dir, is_global) for name in agents]
    return {"results": results}


@router.post("/api/ui/connections/uninstall")
async def connections_uninstall(body: dict, _: None = Depends(_require_local)):
    """Remove MEMANTO integration for a single agent at a given location.

    Body: {"agent": "claude-code", "project_dir": "/abs/path", "is_global": false}

    Stale entries (project_dir gone) are handled registry-only.
    """
    agent_name = body.get("agent")
    if not agent_name or agent_name not in AGENT_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown agent: {agent_name}")
    is_global = bool(body.get("is_global", False))
    project_dir = body.get("project_dir")

    if not is_global:
        if not project_dir:
            raise HTTPException(
                status_code=400, detail="`project_dir` is required when not global"
            )
        path_obj = Path(project_dir).expanduser()
        if not path_obj.exists():
            # Stale registry entry — clean it up without touching disk.
            _config_manager.remove_connection(
                agent_name, str(path_obj), is_global=False
            )
            return {
                "result": {
                    "agent": agent_name,
                    "steps": ["Untracked stale entry (folder no longer exists)"],
                    "errors": [],
                }
            }
        project_dir = str(path_obj.resolve())

    result = remove_agent(agent_name, project_dir or ".", is_global)
    return {"result": result}


@router.post("/api/ui/shutdown")
async def shutdown_server(
    background_tasks: BackgroundTasks,
    _: None = Depends(_require_local),
):
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


_MIGRATE_PROVIDERS = ("mem0", "letta", "supermemory")


def _migrate_compact_metrics(provider: str, metrics: dict) -> dict:
    """Strip the savings-metrics dict down to the few numbers the UI shows.

    Provider compare modules ship rich dicts with cost, latency, storage
    breakdowns. The UI only needs the headline numbers — pull them out
    uniformly so the JS doesn't need provider-specific code paths.
    """
    volume = metrics.get("volume", {}) or {}
    ingestion = metrics.get("ingestion_tax", {}) or {}
    storage = metrics.get("storage", {}) or {}
    latency = metrics.get("latency", {}) or {}

    cost_key = next(
        (
            k
            for k in (
                f"{provider}_extraction_cost_usd",
                "mem0_extraction_cost_usd",
                "letta_extraction_cost_usd",
                "supermemory_extraction_cost_usd",
            )
            if k in ingestion
        ),
        None,
    )
    read_ms_key = next(
        (
            k
            for k in (
                f"{provider}_read_ms",
                "mem0_read_ms",
                "letta_read_ms",
                "supermemory_read_ms",
            )
            if k in latency
        ),
        None,
    )

    return {
        "tokens_saved": ingestion.get("tokens_saved", 0),
        "extraction_cost_usd": ingestion.get(cost_key) if cost_key else 0.0,
        "storage_saved_human": storage.get("saved_human", "—"),
        "storage_compression_ratio": storage.get("compression_ratio", 0),
        "read_ms_source": latency.get(read_ms_key) if read_ms_key else 0,
        "read_ms_memanto": latency.get("memanto_read_ms", 0),
        "latency_speedup_x": latency.get("speedup_x", 0),
        "estimated_content_tokens": volume.get("estimated_content_tokens", 0),
    }


def _migrate_load_or_export(
    provider: str,
    file_path: str | None,
    api_key: str | None,
) -> tuple[str, dict]:
    """Either load a JSON export from disk or pull one live with the API key.

    Returns ``(source_label, export_dict)``. ``source_label`` is what the UI
    shows under "Source" — either the file path or "live export".
    """
    from memanto.cli.analyze.letta_export import run_letta_export
    from memanto.cli.analyze.mem0_export import run_mem0_export
    from memanto.cli.analyze.supermemory_export import run_supermemory_export
    from memanto.cli.migrate.runner import load_export

    if file_path:
        path = Path(file_path).expanduser()
        if not path.exists() or not path.is_file():
            raise HTTPException(
                status_code=400, detail=f"Export file not found: {file_path}"
            )
        return str(path), load_export(path)

    if not api_key or not api_key.strip():
        raise HTTPException(
            status_code=400,
            detail="Either `file` (server-side path) or `api_key` is required.",
        )

    exporters: dict[str, Any] = {
        "mem0": run_mem0_export,
        "letta": run_letta_export,
        "supermemory": run_supermemory_export,
    }
    exporter = exporters[provider]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = _config_manager.get_migrate_dir(provider) / stamp
    dest.mkdir(parents=True, exist_ok=True)
    try:
        export_path, export = exporter(api_key.strip(), dest)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"{provider} export failed: {e}")
    return str(export_path), export


def _migrate_get_metrics_fn(provider: str):
    if provider == "mem0":
        from memanto.cli.analyze.mem0_compare import compute_metrics

        return compute_metrics
    if provider == "letta":
        from memanto.cli.analyze.letta_compare import compute_metrics

        return compute_metrics
    from memanto.cli.analyze.supermemory_compare import compute_metrics

    return compute_metrics


@router.post("/api/ui/migrate/dry-run")
async def migrate_dry_run(body: dict, _: None = Depends(_require_local)):
    """Preview a migration without writing.

    Body: ``{provider, file?, api_key?}``. Returns the mapped row count,
    type breakdown, compact savings metrics, and a small sample of the
    mapped payloads so the UI can preview what would be imported.
    """
    from memanto.cli.migrate.runner import map_export, source_count

    provider = (body.get("provider") or "").strip().lower()
    if provider not in _MIGRATE_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"provider must be one of: {', '.join(_MIGRATE_PROVIDERS)}",
        )

    source_label, export = _migrate_load_or_export(
        provider, body.get("file"), body.get("api_key")
    )

    rows = map_export(provider, export)
    src_count = source_count(provider, export)

    type_counts: dict[str, int] = {}
    for row in rows:
        key = row.get("type") or "auto"
        type_counts[key] = type_counts.get(key, 0) + 1

    metrics_fn = _migrate_get_metrics_fn(provider)
    savings = _migrate_compact_metrics(provider, metrics_fn(export))

    sample = []
    for row in rows[:5]:
        created = row.get("created_at")
        sample.append(
            {
                "title": row.get("title"),
                "type": row.get("type") or "auto",
                "tags": row.get("tags") or [],
                "source_ref": row.get("source_ref"),
                "created_at": created.isoformat() if created else None,
            }
        )

    return {
        "provider": provider,
        "source_label": source_label,
        "source_count": src_count,
        "mapped_count": len(rows),
        "skipped": max(0, src_count - len(rows)),
        "type_counts": type_counts,
        "sample": sample,
        "savings": savings,
        "batch_count": (len(rows) + 99) // 100,
    }


@router.post("/api/ui/migrate/import")
async def migrate_import(body: dict, _: None = Depends(_require_local)):
    """Run an end-to-end migration.

    Body: ``{provider, file?, api_key?, agent_id?}``. Loads-or-exports,
    maps, chunks at 100/req, and writes via ``DirectClient.batch_remember``.
    Returns numeric summary only — no LLM narrative.
    """
    from memanto.cli.migrate.runner import run_migration

    provider = (body.get("provider") or "").strip().lower()
    if provider not in _MIGRATE_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"provider must be one of: {', '.join(_MIGRATE_PROVIDERS)}",
        )

    agent_id = body.get("agent_id") or _config_manager.get_active_session()[0]
    if not agent_id:
        raise HTTPException(
            status_code=400,
            detail="No --agent supplied and no active agent. Activate an agent first.",
        )

    client = _build_ui_direct_client()
    if client is None:
        raise HTTPException(status_code=400, detail="No Memanto API key configured.")

    source_label, export = _migrate_load_or_export(
        provider, body.get("file"), body.get("api_key")
    )

    started = time.perf_counter()
    try:
        summary, _rows = run_migration(
            provider=provider,
            export=export,
            client=client,
            agent_id=str(agent_id),
            dry_run=False,
            on_progress=None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    metrics_fn = _migrate_get_metrics_fn(provider)
    savings = _migrate_compact_metrics(provider, metrics_fn(export))

    return {
        "provider": provider,
        "agent_id": agent_id,
        "source_label": source_label,
        "summary": summary.as_dict(),
        "elapsed_ms": elapsed_ms,
        "savings": savings,
    }


def get_ui_router():
    """Return the router for inclusion in the main app."""
    return router


def mount_ui_static(app):
    """Mount the static files directory for serving the UI SPA."""
    if STATIC_DIR.exists():
        # Serve index.html for the /ui root. No-store so the browser always
        # picks up the latest UI without a hard refresh after upgrades.
        @app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
        async def serve_ui():
            index_path = STATIC_DIR / "index.html"
            if index_path.exists():
                return FileResponse(
                    index_path,
                    headers={
                        "Cache-Control": "no-store, no-cache, must-revalidate",
                        "Pragma": "no-cache",
                    },
                )
            raise HTTPException(status_code=404, detail="UI not found")

        # Mount static assets (CSS, JS, images) under /ui/static
        app.mount(
            "/ui/static", StaticFiles(directory=str(STATIC_DIR)), name="ui_static"
        )
