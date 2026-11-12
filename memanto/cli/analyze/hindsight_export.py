"""
Export Hindsight memory banks to JSON.

Used by ``memanto migrate hindsight``. Pure ``httpx`` — no
``hindsight-client`` SDK dependency.

Endpoints (Hindsight HTTP API — https://hindsight.vectorize.io/api-reference):
    GET /v1/default/banks?limit=&offset=                        list banks
    GET /v1/default/banks/{bank_id}/memories/list?limit=&offset= list memory units

Works against Hindsight Cloud (the default base URL) and self-hosted servers
(``base_url``). Auth: ``Authorization: Bearer <api_key>``.

The listing endpoint omits memory units a user has invalidated, so the
export holds only valid units; the mapper still skips any invalidated unit it
is given.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

DEFAULT_BASE_URL = "https://api.hindsight.vectorize.io"
PAGE_SIZE = 100
REQUEST_TIMEOUT_S = 60.0
# Safety valve so a server that ignores offset can't loop forever.
MAX_PAGES = 5000


def normalize_base_url(base_url: str | None) -> str:
    """Normalize a Hindsight base URL (Hindsight Cloud or self-hosted).

    A bare host gets ``https://``, except local servers, which a default
    self-hosted install serves over plain ``http://``.
    """
    text = (base_url or "").strip().rstrip("/")
    if not text:
        return DEFAULT_BASE_URL
    if not text.startswith(("http://", "https://")):
        local = text.startswith(("localhost", "127.0.0.1", "[::1]"))
        text = f"{'http' if local else 'https'}://{text}"
    return text


def _client(api_key: str, base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        timeout=REQUEST_TIMEOUT_S,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )


def _paginate(client: httpx.Client, path: str, items_key: str) -> list[dict[str, Any]]:
    """Walk a ``limit``/``offset`` listing until a short page or ``total``."""
    items: list[dict[str, Any]] = []
    for page in range(MAX_PAGES):
        resp = client.get(path, params={"limit": PAGE_SIZE, "offset": page * PAGE_SIZE})
        if resp.status_code >= 400:
            raise RuntimeError(f"{path} -> {resp.status_code}: {resp.text[:500]}")
        data = resp.json() if resp.content else {}
        batch = data.get(items_key) or []
        items.extend(batch)

        total = data.get("total")
        if len(batch) < PAGE_SIZE or (total is not None and len(items) >= total):
            return items
    raise RuntimeError(
        f"Hindsight pagination exceeded {MAX_PAGES} pages for {path}; "
        "export would be incomplete."
    )


def list_all_banks(client: httpx.Client) -> list[dict[str, Any]]:
    return _paginate(client, "/v1/default/banks", "banks")


def list_bank_memories(client: httpx.Client, bank_id: str) -> list[dict[str, Any]]:
    return _paginate(
        client, f"/v1/default/banks/{quote(bank_id, safe='')}/memories/list", "items"
    )


def run_hindsight_export(
    api_key: str,
    dest_dir: Path,
    *,
    base_url: str | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Pull every bank's memory units and write ``hindsight_export.json``."""
    api_base = normalize_base_url(base_url)
    all_memories: list[dict[str, Any]] = []
    memory_counts: dict[str, int] = {}

    with _client(api_key, api_base) as client:
        if on_progress:
            on_progress(f"Listing Hindsight banks at {api_base}...")
        banks = list_all_banks(client)
        if on_progress:
            on_progress(f"Found {len(banks)} banks")

        for i, bank in enumerate(banks, 1):
            bank_id = bank.get("bank_id")
            if not bank_id:
                continue
            if on_progress:
                on_progress(f"Fetching memories [{i}/{len(banks)}] {bank_id}")
            memories = list_bank_memories(client, str(bank_id))
            # List rows don't carry their bank; stamp it so the mapper can tag
            # each memory with the bank it came from.
            for memory in memories:
                memory["export_bank_id"] = bank_id
            all_memories.extend(memories)
            memory_counts[str(bank_id)] = len(memories)

    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "api_base": api_base,
        "summary": {
            "bank_count": len(banks),
            "memory_count": len(all_memories),
            "memories_by_bank": memory_counts,
        },
        "banks": banks,
        "memories": all_memories,
    }

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / "hindsight_export.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False, default=str)

    return out_path, export
