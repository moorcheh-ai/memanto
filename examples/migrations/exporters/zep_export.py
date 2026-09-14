"""
Export Zep graph edges (facts) to JSON.

Endpoints (Zep Cloud REST API v2):
    GET  /api/v2/users-ordered?pageNumber=&pageSize=   list users
    POST /api/v2/graph/edge/user/{user_id}             list edges for one user

Auth: ``Authorization: Api-Key <api_key>``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

API_BASE = "https://api.getzep.com"
USER_PAGE_SIZE = 100
EDGE_PAGE_SIZE = 200
REQUEST_TIMEOUT_S = 60.0


def _client(api_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        timeout=REQUEST_TIMEOUT_S,
        headers={
            "Authorization": f"Api-Key {api_key}",
            "Content-Type": "application/json",
        },
    )


def _get_json(client: httpx.Client, path: str, params: dict[str, Any] | None = None) -> Any:
    resp = client.get(path, params=params or {})
    if resp.status_code >= 400:
        raise RuntimeError(f"GET {path} -> {resp.status_code}: {resp.text[:500]}")
    return resp.json() if resp.content else {}


def _post_json(client: httpx.Client, path: str, body: dict[str, Any]) -> Any:
    resp = client.post(path, json=body)
    if resp.status_code >= 400:
        raise RuntimeError(f"POST {path} -> {resp.status_code}: {resp.text[:500]}")
    return resp.json() if resp.content else []


def list_all_users(client: httpx.Client) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    page = 1
    MAX_PAGES = 1000
    while True:
        data = _get_json(
            client,
            "/api/v2/users-ordered",
            params={"pageNumber": page, "pageSize": USER_PAGE_SIZE},
        )
        total_count: int | None = data.get("total_count")
        batch = data.get("users") or []
        users.extend(batch)
        if len(batch) < USER_PAGE_SIZE:
            break
        if total_count is not None and len(users) >= total_count:
            break
        if page >= MAX_PAGES:
            raise RuntimeError(
                f"User pagination cap ({MAX_PAGES} pages) reached. Export may be incomplete."
            )
        page += 1
    return users


def list_user_edges(client: httpx.Client, user_id: str) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    MAX_PAGES = 5000
    page = 0
    while True:
        body: dict[str, Any] = {"limit": EDGE_PAGE_SIZE}
        if cursor:
            body["uuid_cursor"] = cursor
        batch = _post_json(client, f"/api/v2/graph/edge/user/{user_id}", body)
        if not isinstance(batch, list) or not batch:
            break
        edges.extend(batch)
        if len(batch) < EDGE_PAGE_SIZE:
            break
        new_cursor = batch[-1].get("uuid")
        if not new_cursor or new_cursor in seen_cursors:
            break
        seen_cursors.add(new_cursor)
        cursor = new_cursor
        page += 1
        if page >= MAX_PAGES:
            raise RuntimeError(
                f"Edge pagination cap ({MAX_PAGES} pages) reached for user '{user_id}'. "
                "Export may be incomplete."
            )
    return edges


def run_zep_export(
    api_key: str,
    dest_dir: Path,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    with _client(api_key) as client:
        if on_progress:
            on_progress("Listing Zep users...")
        users = list_all_users(client)
        if on_progress:
            on_progress(f"Found {len(users)} users")

        all_edges: list[dict[str, Any]] = []
        edges_by_user: dict[str, list[dict[str, Any]]] = {}

        for i, user in enumerate(users, 1):
            user_id = user.get("user_id") or user.get("uuid")
            if not user_id:
                continue
            if on_progress:
                on_progress(f"Fetching edges [{i}/{len(users)}] {user_id}")
            edges = list_user_edges(client, user_id)
            edges_by_user[user_id] = edges
            all_edges.extend(edges)
            if on_progress:
                on_progress(f"  {user_id}: {len(edges)} edges")

    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "api_base": API_BASE,
        "summary": {
            "user_count": len(users),
            "edge_count": len(all_edges),
        },
        "users": users,
        "memories": all_edges,
        "memories_by_user": edges_by_user,
    }

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = _write_export_json(export, dest_dir, "zep_export.json")
    return out_path, export


def _write_export_json(export: dict[str, Any], dest_dir: Path, filename: str) -> Path:
    import tempfile
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / filename
    fd, tmp_str = tempfile.mkstemp(dir=dest_dir, prefix=f".{filename}.", suffix=".tmp")
    tmp_path = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(export, f, indent=2, ensure_ascii=False, default=str)
        tmp_path.replace(out_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return out_path
