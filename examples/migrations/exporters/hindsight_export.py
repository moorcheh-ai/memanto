"""
Export Hindsight memory bank to JSON.

Endpoints (Hindsight Cloud REST API):
    GET /v1/default/banks                                    list all banks
    GET /v1/default/banks/{bank_id}/memories/list?limit=&offset=

Auth: ``authorization: <api_key>`` header (no Bearer prefix).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

try:
    from .zep_export import _write_export_json
except ImportError:
    from zep_export import _write_export_json  # type: ignore[no-redef]

DEFAULT_BASE_URL = "https://api.hindsight.vectorize.io"
PAGE_SIZE = 100
REQUEST_TIMEOUT_S = 60.0


def _client(api_key: str, base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=REQUEST_TIMEOUT_S,
        headers={
            "authorization": api_key,
            "content-type": "application/json",
        },
    )


def _get_json(client: httpx.Client, path: str, params: dict[str, Any] | None = None) -> Any:
    resp = client.get(path, params=params or {})
    if resp.status_code >= 400:
        raise RuntimeError(f"GET {path} -> {resp.status_code}: {resp.text[:500]}")
    return resp.json() if resp.content else {}


def list_all_banks(client: httpx.Client) -> list[dict[str, Any]]:
    data = _get_json(client, "/v1/default/banks")
    return data.get("banks") or []


def list_bank_memories(client: httpx.Client, bank_id: str) -> list[dict[str, Any]]:
    memories: list[dict[str, Any]] = []
    offset = 0
    MAX_PAGES = 500
    pages = 0
    while True:
        data = _get_json(
            client,
            f"/v1/default/banks/{bank_id}/memories/list",
            params={"limit": PAGE_SIZE, "offset": offset},
        )
        batch = data.get("items") or []
        memories.extend(batch)
        total = data.get("total")
        pages += 1
        if len(batch) < PAGE_SIZE or (total is not None and len(memories) >= total):
            break
        if pages >= MAX_PAGES:
            raise RuntimeError(
                f"Pagination cap ({MAX_PAGES} pages) reached for bank '{bank_id}'. "
                "Export may be incomplete."
            )
        offset += PAGE_SIZE
    return memories


def run_hindsight_export(
    api_key: str,
    dest_dir: Path,
    *,
    base_url: str = DEFAULT_BASE_URL,
    bank_id: str | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    with _client(api_key, base_url) as client:
        if bank_id:
            banks = [{"bank_id": bank_id}]
        else:
            if on_progress:
                on_progress("Listing Hindsight banks...")
            banks = list_all_banks(client)
            if on_progress:
                on_progress(f"Found {len(banks)} banks")

        all_memories: list[dict[str, Any]] = []
        memories_by_bank: dict[str, list[dict[str, Any]]] = {}

        for i, bank in enumerate(banks, 1):
            bid = bank.get("bank_id") or bank.get("id")
            if not bid:
                continue
            if on_progress:
                on_progress(f"Fetching memories [{i}/{len(banks)}] {bid}")
            memories = list_bank_memories(client, bid)
            memories_by_bank[bid] = memories
            all_memories.extend(memories)
            if on_progress:
                on_progress(f"  {bid}: {len(memories)} memories")

    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "api_base": base_url,
        "summary": {
            "bank_count": len(banks),
            "memory_count": len(all_memories),
        },
        "banks": banks,
        "memories": all_memories,
        "memory_ids_by_bank": {
            bid: [m.get("id") for m in mems if m.get("id")]
            for bid, mems in memories_by_bank.items()
        },
    }

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = _write_export_json(export, dest_dir, "hindsight_export.json")
    return out_path, export
