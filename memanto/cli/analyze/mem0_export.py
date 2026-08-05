"""
Export all Mem0 account data to JSON (entities and memories).

Used by ``memanto migrate mem0``. Pure ``httpx`` — no Mem0 SDK dependency,
so users don't have to install ``mem0ai`` and we don't break when the SDK
ships a new version.

Endpoints (Mem0 Platform REST API — https://docs.mem0.ai/api-reference):
    GET  /v1/entities/                                 list users/agents/apps/runs
    GET  /v1/memories/?<scope>&page=&page_size=        list memories scoped to one entity

Auth: ``Authorization: Token <api_key>`` (Mem0's convention — not Bearer).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

API_BASE = "https://api.mem0.ai"
DEFAULT_PAGE_SIZE = 200
REQUEST_TIMEOUT_S = 60.0

ENTITY_FILTER_KEYS = {
    "user": "user_id",
    "agent": "agent_id",
    "app": "app_id",
    "run": "run_id",
}


def _client(api_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        timeout=REQUEST_TIMEOUT_S,
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        },
    )


def _get_json(
    client: httpx.Client, path: str, params: dict[str, Any] | None = None
) -> Any:
    resp = client.get(path, params=params or {})
    if resp.status_code >= 400:
        raise RuntimeError(f"GET {path} -> {resp.status_code}: {resp.text[:500]}")
    return resp.json() if resp.content else {}


def dedupe_by_id(
    items: list[dict[str, Any]],
    *,
    id_key: str = "id",
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        item_id = item.get(id_key)
        if item_id:
            if item_id in seen:
                continue
            seen.add(item_id)
        unique.append(item)
    return unique


def normalize_entities(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [e for e in raw if isinstance(e, dict)]
    if isinstance(raw, dict):
        for key in ("results", "entities", "data"):
            batch = raw.get(key)
            if isinstance(batch, list):
                return [e for e in batch if isinstance(e, dict)]
    return []


def entity_to_filter(entity: dict[str, Any]) -> dict[str, str] | None:
    entity_type = str(entity.get("type") or "").lower()
    filter_key = ENTITY_FILTER_KEYS.get(entity_type)
    entity_id = entity.get("name") or entity.get("id")
    if filter_key and entity_id:
        return {filter_key: str(entity_id)}
    return None


def discover_entities(client: httpx.Client) -> list[dict[str, Any]]:
    """List every user, agent, app, and run that has memories in the account."""
    raw = _get_json(client, "/v1/entities/")
    entities = normalize_entities(raw)
    return dedupe_by_id(entities, id_key="id")


def build_export_scopes(
    client: httpx.Client,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Discover all entities via the API and build one memory-fetch scope per entity."""
    entities = discover_entities(client)
    scopes: list[dict[str, str]] = []
    for entity in entities:
        filt = entity_to_filter(entity)
        if filt:
            scopes.append(filt)
    return entities, scopes


def paginate_memories(
    client: httpx.Client,
    filters: dict[str, str],
    *,
    page_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_memories: list[dict[str, Any]] = []
    page = 1
    last_page: dict[str, Any] = {}

    while True:
        params = {**filters, "page": page, "page_size": page_size}
        response = _get_json(client, "/v1/memories/", params=params)
        last_page = response if isinstance(response, dict) else {}
        batch = last_page.get("results") or []
        if not batch:
            break
        all_memories.extend(batch)
        if not last_page.get("next"):
            break
        page += 1

    return all_memories, last_page


def collect_memories(
    client: httpx.Client,
    scopes: list[dict[str, str]],
    *,
    page_size: int,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    seen_ids: set[str] = set()
    all_memories: list[dict[str, Any]] = []
    by_scope: dict[str, list[dict[str, Any]]] = {}

    for i, filters in enumerate(scopes, 1):
        scope_label = ", ".join(f"{k}={v}" for k, v in filters.items())
        if on_progress:
            on_progress(f"Fetching memories [{i}/{len(scopes)}] {scope_label}")

        memories, pagination = paginate_memories(client, filters, page_size=page_size)
        if on_progress:
            total = pagination.get("count", "?")
            on_progress(f"  fetched {len(memories)} (total count: {total})")

        scope_rows: list[dict[str, Any]] = []
        for entry in memories:
            memory_id = entry.get("id")
            row = dict(entry)
            row["export_scope"] = filters

            if memory_id and memory_id in seen_ids:
                scope_rows.append(row)
                continue

            if memory_id:
                seen_ids.add(memory_id)

            scope_rows.append(row)
            all_memories.append(row)

        by_scope[scope_label] = scope_rows

    return dedupe_by_id(all_memories), by_scope


def run_mem0_export(
    api_key: str,
    dest_dir: Path,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """
    Export full Mem0 account data and write JSON into *dest_dir*.

    Lists every entity (users, agents, apps, runs) via ``GET /v1/entities/``,
    then fetches all memories for each one via paginated
    ``GET /v1/memories/?<scope>``.

    Returns the written file path and the full export dict.
    """
    page_size = max(1, min(page_size, 200))

    with _client(api_key) as client:
        if on_progress:
            on_progress("Listing all users, agents, apps, and runs...")
        entities, scopes = build_export_scopes(client)

        if on_progress:
            type_counts: dict[str, int] = {}
            for entity in entities:
                entity_type = str(entity.get("type") or "unknown").lower()
                type_counts[entity_type] = type_counts.get(entity_type, 0) + 1
            breakdown = ", ".join(
                f"{count} {name}{'s' if count != 1 else ''}"
                for name, count in sorted(type_counts.items())
            )
            on_progress(
                f"Found {len(entities)} entities ({breakdown or 'none'}) - "
                f"fetching memories for each"
            )

        all_memories: list[dict[str, Any]] = []
        memories_by_scope: dict[str, list[dict[str, Any]]] = {}
        if scopes:
            if on_progress:
                on_progress("Fetching memories (deduped by id)...")
            all_memories, memories_by_scope = collect_memories(
                client,
                scopes,
                page_size=page_size,
                on_progress=on_progress,
            )

    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "api_base": API_BASE,
        "summary": {
            "entity_count": len(entities),
            "scope_count": len(scopes),
            "memory_count": len(all_memories),
            "page_size": page_size,
        },
        "entities": entities,
        "memories": all_memories,
        "memories_by_scope": memories_by_scope,
        "notes": {
            "deduplication": "Each memory id appears once in memories[]. "
            "memories_by_scope may repeat the same id under different scopes.",
            "entities": "All users, agents, apps, and runs are listed via "
            "GET /v1/entities/ and exported automatically - no manual ID config.",
        },
    }

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / "mem0_export.json"

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False, default=str)

    return out_path, export
