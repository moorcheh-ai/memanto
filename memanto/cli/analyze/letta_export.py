"""
Export Letta agent archival memory to JSON.

Used by ``memanto migrate letta``. Pure ``httpx`` — no Letta SDK dependency,
so users don't have to install ``letta-client`` and we don't break when the
SDK changes its surface.

Endpoints (Letta Cloud REST API — https://docs.letta.com/api-reference):
    GET  /v1/agents/?limit=&after=                    list agents (cursor-paginated)
    GET  /v1/agents/{agent_id}/archival-memory?limit=&after=
                                                       list archival passages

Auth: ``Authorization: Bearer <api_key>``.

Lists every agent in the account and exports archival passages from each.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

API_BASE = "https://api.letta.com"
PASSAGE_PAGE_SIZE = 100
AGENT_PAGE_SIZE = 50
REQUEST_TIMEOUT_S = 60.0

# Fields that bloat the export and are not used by the mapper or savings
# metrics — stripped at export time to keep JSON files manageable.
_PASSAGE_DROP_KEYS = ("embedding", "embedding_config")


def _client(api_key: str) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE,
        timeout=REQUEST_TIMEOUT_S,
        headers={
            "Authorization": f"Bearer {api_key}",
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


def _normalize_list(raw: Any) -> list[dict[str, Any]]:
    """Letta endpoints sometimes return a bare list, sometimes wrapped."""
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for key in ("results", "data", "items", "passages", "agents"):
            batch = raw.get(key)
            if isinstance(batch, list):
                return [x for x in batch if isinstance(x, dict)]
    return []


def _strip_passage(passage: dict[str, Any]) -> dict[str, Any]:
    out = dict(passage)
    for key in _PASSAGE_DROP_KEYS:
        out.pop(key, None)
    return out


def dedupe_agents(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for agent in agents:
        agent_id = agent.get("id")
        if agent_id:
            if agent_id in seen:
                continue
            seen.add(agent_id)
        unique.append(agent)
    return unique


def list_all_agents(
    client: httpx.Client,
    *,
    page_size: int = AGENT_PAGE_SIZE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    start = time.perf_counter()
    all_items: list[dict[str, Any]] = []
    cursor: str | None = None
    pages = 0

    while True:
        params: dict[str, Any] = {"limit": page_size}
        if cursor:
            params["after"] = cursor
        batch = _normalize_list(_get_json(client, "/v1/agents/", params=params))
        pages += 1
        if not batch:
            break
        all_items.extend(batch)
        if len(batch) < page_size:
            break
        last_id = batch[-1].get("id")
        if not last_id or last_id == cursor:
            break
        cursor = last_id

    agents = dedupe_agents(all_items)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return agents, {
        "pages": pages,
        "count": len(agents),
        "elapsed_ms": round(elapsed_ms, 1),
    }


def list_all_passages(
    client: httpx.Client,
    agent_id: str,
    *,
    page_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    start = time.perf_counter()
    all_items: list[dict[str, Any]] = []
    cursor: str | None = None
    pages = 0

    while True:
        params: dict[str, Any] = {"limit": page_size}
        if cursor:
            params["after"] = cursor
        batch = _normalize_list(
            _get_json(client, f"/v1/agents/{agent_id}/archival-memory", params=params)
        )
        pages += 1
        if not batch:
            break
        all_items.extend(batch)
        if len(batch) < page_size:
            break
        last_id = batch[-1].get("id")
        if not last_id or last_id == cursor:
            break
        cursor = last_id

    elapsed_ms = (time.perf_counter() - start) * 1000
    return all_items, {
        "pages": pages,
        "count": len(all_items),
        "elapsed_ms": round(elapsed_ms, 1),
    }


def _tag_passages(
    passages: list[dict[str, Any]],
    *,
    agent_id: str,
    agent_name: str | None,
) -> list[dict[str, Any]]:
    tagged: list[dict[str, Any]] = []
    for passage in passages:
        row = _strip_passage(passage)
        row["export_agent_id"] = agent_id
        if agent_name:
            row["export_agent_name"] = agent_name
        tagged.append(row)
    return tagged


def run_letta_export(
    api_key: str,
    dest_dir: Path,
    *,
    page_size: int = PASSAGE_PAGE_SIZE,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """
    Export every Letta agent's archival memory and write JSON into *dest_dir*.

    Returns the written file path and the full export dict. The output shape
    matches what ``cli/migrate/mappers.map_letta`` and
    ``cli/analyze/letta_compare.compute_metrics`` already expect.
    """
    page_size = max(1, min(page_size, 200))

    with _client(api_key) as client:
        if on_progress:
            on_progress("Listing all Letta agents...")
        agents, agent_meta = list_all_agents(client)
        if on_progress:
            on_progress(
                f"Found {agent_meta['count']} agents "
                f"({agent_meta['pages']} pages, {agent_meta['elapsed_ms']}ms)"
            )

        if not agents:
            raise ValueError(
                "No Letta agents found in this account. Create one in Letta ADE first."
            )

        all_passages: list[dict[str, Any]] = []
        passages_by_agent: dict[str, list[dict[str, Any]]] = {}
        per_agent_meta: dict[str, dict[str, Any]] = {}
        total_pages = 0

        for i, agent in enumerate(agents, 1):
            agent_id = agent.get("id")
            if not agent_id:
                continue
            agent_name = agent.get("name")
            label = agent_name or agent_id

            if on_progress:
                on_progress(f"Fetching passages [{i}/{len(agents)}] {label}...")

            passages, passage_meta = list_all_passages(
                client,
                agent_id,
                page_size=page_size,
            )
            tagged = _tag_passages(passages, agent_id=agent_id, agent_name=agent_name)
            passages_by_agent[agent_id] = tagged
            all_passages.extend(tagged)
            per_agent_meta[agent_id] = passage_meta
            total_pages += passage_meta["pages"]

            if on_progress:
                on_progress(
                    f"  {label}: {passage_meta['count']} passages "
                    f"({passage_meta['pages']} pages)"
                )

    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "api_base": API_BASE,
        "export_mode": "all_agents",
        "summary": {
            "agent_count": len(agents),
            "passage_count": len(all_passages),
            "passage_page_size": page_size,
            "passage_pages": total_pages,
        },
        "agents": agents,
        "passages": all_passages,
        "passages_by_agent": passages_by_agent,
        "meta": {
            "agents": agent_meta,
            "passages_by_agent": per_agent_meta,
        },
        "notes": {
            "export": "All agents listed via GET /v1/agents/ and exported "
            "automatically - no manual agent id config required.",
        },
    }

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / "letta_export.json"

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False, default=str)

    return out_path, export
