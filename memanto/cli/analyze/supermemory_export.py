"""
Export all Supermemory account data to JSON (documents, chunks, memories,
connections).

Used by ``memanto migrate supermemory``. Pure ``httpx`` — no Supermemory
SDK dependency, so users don't have to install ``supermemory`` and we
don't break when the SDK changes its surface.

Endpoints (Supermemory REST API — https://docs.supermemory.ai):
    POST /v3/documents/list                     list documents (paginated)
    GET  /v3/documents/{id}                     document detail (tags, etc.)
    GET  /v3/documents/{id}/chunks              RAG chunks for a document
    GET  /v3/connections/list                   list connections
    POST /v4/memories/list                      list memory entries by container tag

Auth: ``Authorization: Bearer <api_key>``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

API_BASE = "https://api.supermemory.ai"
DOC_PAGE_SIZE = 200
MEMORY_PAGE_SIZE = 200
REQUEST_TIMEOUT_S = 120.0

REDUNDANT_DOC_KEYS = frozenset(
    {
        "connectionId",
        "containerTags",
        "createdAt",
        "customId",
        "updatedAt",
        "ogImage",
        "taskType",
        "dreamingStatus",
        "content",
        "url",
    }
)


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def api_request(
    api_key: str,
    method: str,
    path: str,
    body: dict | None = None,
) -> Any:
    """Single-shot HTTP helper used by every Supermemory call below."""
    url = f"{API_BASE}{path}"
    with httpx.Client(timeout=REQUEST_TIMEOUT_S) as http:
        if method == "GET":
            resp = http.get(url, headers=_headers(api_key))
        elif method == "POST":
            resp = http.post(url, headers=_headers(api_key), json=body or {})
        else:
            raise ValueError(method)
    if resp.status_code >= 400:
        raise RuntimeError(f"{path} -> {resp.status_code}: {resp.text[:500]}")
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


def tags_from_obj(obj: dict[str, Any]) -> list[str]:
    raw = obj.get("container_tags") or obj.get("containerTags") or []
    return [str(t) for t in raw if t]


def paginate_documents(
    api_key: str,
    *,
    include_content: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_docs: list[dict[str, Any]] = []
    page = 1
    pagination_meta: dict[str, Any] = {}

    while True:
        data = api_request(
            api_key,
            "POST",
            "/v3/documents/list",
            {
                "limit": DOC_PAGE_SIZE,
                "page": page,
                "includeContent": include_content,
                "sort": "createdAt",
                "order": "desc",
            },
        )
        batch = data.get("memories") or data.get("documents") or []
        if not batch:
            break
        all_docs.extend(batch)

        pagination = data.get("pagination") or {}
        pagination_meta = pagination
        total_pages = int(
            pagination.get("total_pages") or pagination.get("totalPages") or 1
        )
        if page >= total_pages:
            break
        page += 1

    return all_docs, pagination_meta


def enrich_documents(
    api_key: str,
    documents: list[dict[str, Any]],
    *,
    include_content: bool,
    fetch_chunks: bool,
    on_progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for i, doc in enumerate(documents, 1):
        doc_id = doc.get("id")
        if not doc_id:
            enriched.append(doc)
            continue

        if on_progress:
            on_progress(f"Enriching document {i}/{len(documents)} ({doc_id[:12]}...)")

        entry = dict(doc)

        try:
            detail = api_request(api_key, "GET", f"/v3/documents/{doc_id}")
            if isinstance(detail, dict):
                entry["detail"] = detail
                entry["container_tags"] = tags_from_obj(detail) or tags_from_obj(entry)
        except Exception as exc:
            entry["detail_error"] = str(exc)

        if fetch_chunks:
            try:
                chunk_data = api_request(
                    api_key, "GET", f"/v3/documents/{doc_id}/chunks"
                )
                raw_chunks = chunk_data.get("chunks") or []
                entry["chunks"] = dedupe_by_id(raw_chunks)
                entry["chunk_total"] = len(entry["chunks"])
            except Exception as exc:
                entry["chunks_error"] = str(exc)
                entry["chunks"] = []
                entry["chunk_total"] = 0

        enriched.append(finalize_document(entry, include_content=include_content))

    return enriched


def discover_container_tags(
    documents: list[dict[str, Any]],
    connections: list[dict[str, Any]],
) -> list[str]:
    tags: set[str] = set()
    for doc in documents:
        for tag in tags_from_obj(doc):
            tags.add(tag)
        detail = doc.get("detail")
        if isinstance(detail, dict):
            for tag in tags_from_obj(detail):
                tags.add(tag)
    for conn in connections:
        for tag in tags_from_obj(conn):
            tags.add(tag)
    return sorted(tags)


def paginate_memories_for_tag(api_key: str, tag: str) -> list[dict[str, Any]]:
    all_entries: list[dict[str, Any]] = []
    page = 1

    while True:
        data = api_request(
            api_key,
            "POST",
            "/v4/memories/list",
            {
                "containerTags": [tag],
                "limit": MEMORY_PAGE_SIZE,
                "page": page,
                "sort": "createdAt",
                "order": "desc",
            },
        )
        batch = (
            data.get("memoryEntries")
            or data.get("memory_entries")
            or data.get("memories")
            or []
        )
        if not batch:
            break
        all_entries.extend(batch)

        pagination = data.get("pagination") or {}
        total_pages = int(
            pagination.get("totalPages") or pagination.get("total_pages") or 1
        )
        if page >= total_pages:
            break
        page += 1

    return all_entries


def finalize_document(
    entry: dict[str, Any],
    *,
    include_content: bool,
) -> dict[str, Any]:
    out = dict(entry)
    has_chunks = bool(out.get("chunks"))

    for key in REDUNDANT_DOC_KEYS:
        out.pop(key, None)

    detail = out.get("detail")
    if isinstance(detail, dict):
        detail = dict(detail)
        embedded = detail.pop("memories", None) or []
        if embedded:
            out["memory_ids"] = [m["id"] for m in dedupe_by_id(embedded) if m.get("id")]
        if has_chunks and not include_content:
            detail.pop("content", None)
        for key in REDUNDANT_DOC_KEYS:
            detail.pop(key, None)
        out["detail"] = detail

    if include_content and isinstance(out.get("detail"), dict):
        out["content"] = out["detail"].get("content")

    return out


def collect_memories_deduped(
    api_key: str,
    container_tags: list[str],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    seen_ids: set[str] = set()
    all_memories: list[dict[str, Any]] = []
    by_tag: dict[str, list[dict[str, Any]]] = {}

    for tag in container_tags:
        tag_entries: list[dict[str, Any]] = []
        for entry in paginate_memories_for_tag(api_key, tag):
            memory_id = entry.get("id")
            if memory_id and memory_id in seen_ids:
                continue
            if memory_id:
                seen_ids.add(memory_id)
            row = dict(entry)
            row["container_tag"] = tag
            tag_entries.append(row)
            all_memories.append(row)
        by_tag[tag] = tag_entries

    return all_memories, by_tag


def fetch_connections(api_key: str) -> list[dict[str, Any]]:
    try:
        resp = api_request(api_key, "GET", "/v3/connections/list")
    except Exception:
        return []
    if isinstance(resp, list):
        return [c for c in resp if isinstance(c, dict)]
    if isinstance(resp, dict):
        for key in ("connections", "results", "data"):
            batch = resp.get(key)
            if isinstance(batch, list):
                return [c for c in batch if isinstance(c, dict)]
    return []


def run_supermemory_export(
    api_key: str,
    dest_dir: Path,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """
    Export full Supermemory account data and write JSON into *dest_dir*.

    Always fetches: all documents (with detail), RAG chunks, memory entries per
    container tag, and connections.

    Returns the written file path and the full export dict.
    """
    if on_progress:
        on_progress("Listing documents...")
    documents, doc_pagination = paginate_documents(api_key, include_content=False)

    if on_progress:
        on_progress(f"Enriching {len(documents)} documents...")
    documents = enrich_documents(
        api_key,
        documents,
        include_content=False,
        fetch_chunks=True,
        on_progress=on_progress,
    )
    total_chunks = sum(int(d.get("chunk_total") or 0) for d in documents)

    if on_progress:
        on_progress("Fetching connections...")
    connections = fetch_connections(api_key)

    container_tags = discover_container_tags(documents, connections)

    all_memories: list[dict[str, Any]] = []
    memories_by_tag: dict[str, list[dict[str, Any]]] = {}
    if container_tags:
        if on_progress:
            on_progress("Fetching memory entries...")
        all_memories, memories_by_tag = collect_memories_deduped(
            api_key, container_tags
        )

    memory_count = len(all_memories)
    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "api_base": API_BASE,
        "summary": {
            "document_count": len(documents),
            "chunk_count": total_chunks,
            "connection_count": len(connections),
            "container_tag_count": len(container_tags),
            "memory_entry_count": memory_count,
            "container_tags": container_tags,
        },
        "documents": documents,
        "documents_pagination": doc_pagination,
        "connections": dedupe_by_id(connections),
        "memories": all_memories,
        "memories_by_container_tag": memories_by_tag,
        "notes": {
            "deduplication": "Each memory/chunk/connection id appears once. "
            "Documents keep memory_ids only (not full memory objects).",
            "chunks": "Each document includes chunks[] from GET /v3/documents/{id}/chunks",
            "content": "Full document text is in chunks[] per document.",
            "tags": "Tags taken from GET /v3/documents/{id} detail (list often omits dashboard defaults).",
        },
    }

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / "supermemory_export.json"

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False, default=str)

    return out_path, export
