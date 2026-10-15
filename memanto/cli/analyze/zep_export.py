"""
Export Zep Cloud knowledge-graph facts (user graph edges) to JSON.

Used by ``memanto migrate zep``. Pure ``httpx`` — no ``zep-cloud`` SDK
dependency.

Endpoints (Zep Cloud REST API v2 — https://help.getzep.com/sdk-reference):
    GET  /api/v2/users-ordered?pageNumber=&pageSize=   list users (paginated)
    POST /api/v2/graph/edge/user/{user_id}             list a user's edges

Edge listing paginates with the opaque ``Zep-Next-Cursor`` response header.
Older deployments that don't send it fall back to the (deprecated)
``uuid_cursor`` body field, which takes the uuid of the last edge seen.

Auth: ``Authorization: Api-Key <api_key>``.

The export is a raw, lossless dump: invalidated facts are kept here and
dropped by the mapper, so the export file stays a faithful record of the
source account.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

API_BASE = "https://api.getzep.com"
USER_PAGE_SIZE = 100
EDGE_PAGE_SIZE = 200
REQUEST_TIMEOUT_S = 60.0
# Safety valves so a server that keeps handing back a cursor can't loop forever.
MAX_USER_PAGES = 1000
MAX_EDGE_PAGES = 5000


def _client(api_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        timeout=REQUEST_TIMEOUT_S,
        headers={
            "Authorization": f"Api-Key {api_key}",
            "Content-Type": "application/json",
        },
    )


def _check(resp: httpx.Response, path: str) -> None:
    if resp.status_code >= 400:
        raise RuntimeError(f"{path} -> {resp.status_code}: {resp.text[:500]}")


def list_all_users(client: httpx.Client) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    page = 1
    while True:
        path = "/api/v2/users-ordered"
        resp = client.get(path, params={"pageNumber": page, "pageSize": USER_PAGE_SIZE})
        _check(resp, path)
        data = resp.json() if resp.content else {}
        batch = data.get("users") or []
        users.extend(batch)

        total = data.get("total_count")
        if len(batch) < USER_PAGE_SIZE or (total is not None and len(users) >= total):
            break
        if page >= MAX_USER_PAGES:
            raise RuntimeError(
                f"Zep user pagination exceeded {MAX_USER_PAGES} pages; "
                "export would be incomplete."
            )
        page += 1
    return users


def list_user_edges(client: httpx.Client, user_id: str) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    body: dict[str, Any] = {"limit": EDGE_PAGE_SIZE}
    seen_cursors: set[str] = set()
    path = f"/api/v2/graph/edge/user/{quote(user_id, safe='')}"

    for _ in range(MAX_EDGE_PAGES):
        resp = client.post(path, json=body)
        _check(resp, path)
        batch = resp.json() if resp.content else []
        if not isinstance(batch, list) or not batch:
            return edges
        edges.extend(batch)

        header_cursor = resp.headers.get("Zep-Next-Cursor")
        if header_cursor:
            cursor = header_cursor
            body = {"limit": EDGE_PAGE_SIZE, "cursor": cursor}
        elif len(batch) >= EDGE_PAGE_SIZE and batch[-1].get("uuid"):
            cursor = str(batch[-1]["uuid"])
            body = {"limit": EDGE_PAGE_SIZE, "uuid_cursor": cursor}
        else:
            return edges

        if cursor in seen_cursors:
            return edges
        seen_cursors.add(cursor)

    raise RuntimeError(
        f"Zep edge pagination exceeded {MAX_EDGE_PAGES} pages for user "
        f"'{user_id}'; export would be incomplete."
    )


def run_zep_export(
    api_key: str,
    dest_dir: Path,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Pull every user's graph edges and write ``zep_export.json``."""
    all_edges: list[dict[str, Any]] = []
    edge_counts: dict[str, int] = {}

    with _client(api_key) as client:
        if on_progress:
            on_progress("Listing Zep users...")
        users = list_all_users(client)
        if on_progress:
            on_progress(f"Found {len(users)} users")

        for i, user in enumerate(users, 1):
            user_id = user.get("user_id")
            if not user_id:
                continue
            if on_progress:
                on_progress(f"Fetching facts [{i}/{len(users)}] {user_id}")
            edges = list_user_edges(client, str(user_id))
            # Edges don't carry their owner; stamp it so the mapper can tag
            # each memory with the user it belongs to.
            for edge in edges:
                edge["export_user_id"] = user_id
            all_edges.extend(edges)
            edge_counts[str(user_id)] = len(edges)

    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "api_base": API_BASE,
        "summary": {
            "user_count": len(users),
            "edge_count": len(all_edges),
            "edges_by_user": edge_counts,
        },
        "users": users,
        "memories": all_edges,
    }

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / "zep_export.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False, default=str)

    return out_path, export
