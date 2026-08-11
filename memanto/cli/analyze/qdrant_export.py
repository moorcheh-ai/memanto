"""
Qdrant collection -> provider-style export.

Dumps every point (payload + vector metadata) from a Qdrant collection into
the ``{"memories": [...]}`` export shape consumed by
``memanto migrate --file``. Works against any reachable Qdrant instance —
Docker (:6333), Qdrant Cloud, or Qdrant's embedded in-memory mode (used by
the seed script for a fully local, reproducible run).

Supported payload conventions (heuristic, order matters):

1. ``text`` / ``content`` / ``memory``  — the memory text itself
2. ``page_content``                     — LangChain-style Qdrant payloads
3. nested ``metadata`` dict             — timestamps, tags, source, type

Anything that does not map onto the Memanto schema (vector ids, dense/sparse
vectors, scores, hashes, scope ids) is preserved in the payload dict and
surfaces in the ``[Supporting data]`` footer via ``map_qdrant``.

Usage::

    python -m memanto.cli.analyze.qdrant_export \\
        --url http://localhost:6333 --collection memories \\
        --out export.json
    python -m memanto.cli.analyze.qdrant_export \\
        --in-memory --collection memories --out export.json

The ``--in-memory`` flag is for the seed/demo path: it attaches to the
already-seeded embedded instance instead of a server. Requires
``qdrant-client`` (pip install qdrant-client).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Text keys, in priority order. The first non-empty hit wins.
_TEXT_KEYS = ("text", "content", "memory", "page_content", "description")
_METADATA_KEYS = ("metadata", "meta", "attrs")
_DT_KEYS = ("created_at", "createdAt", "timestamp", "ts", "updated_at")
_TAG_KEYS = ("tags", "labels", "categories")
_TYPE_KEYS = ("memory_type", "type", "category", "kind")


def _as_utc_iso(value: Any) -> str | None:
    """Best-effort ISO-8601 (UTC) from the payload's timestamp fields."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Qdrant stores ms-since-epoch in metadata; seconds are also common.
        try:
            if value > 1e12:
                return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value)
    try:
        parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return s


def _first(keys: tuple[str, ...], d: dict[str, Any]) -> Any:
    for k in keys:
        if d.get(k) not in (None, "", [], {}):
            return d[k]
    return None


def _flatten_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge a nested metadata dict into the top level (without clobbering)."""
    flat = dict(payload)
    for k in _METADATA_KEYS:
        meta = payload.get(k)
        if isinstance(meta, dict):
            for mk, mv in meta.items():
                if mk not in flat or flat[mk] in (None, ""):
                    flat[mk] = mv
    return flat


def point_to_memory(point: Any, collection: str) -> dict[str, Any] | None:
    """Convert one Qdrant point to a provider-style memory record."""
    payload = dict(point.payload or {})
    if not payload:
        return None
    flat = _flatten_metadata(payload)

    text = str(_first(_TEXT_KEYS, flat) or "").strip()
    if not text:
        # No text key at all — if the payload is a bare dict of attributes,
        # render the key/value pairs as the memory body so nothing is lost.
        pairs = [f"{k}: {v}" for k, v in flat.items() if not isinstance(v, (dict, list))]
        if not pairs:
            return None
        text = "\n".join(pairs)

    tags = _first(_TAG_KEYS, flat)
    if isinstance(tags, str):
        tags = [tags]
    tags = [str(t) for t in (tags or []) if str(t).strip()][:12]

    mem_type = _first(_TYPE_KEYS, flat)
    mem_type = str(mem_type).strip() if mem_type not in (None, "") else None

    created_at = _as_utc_iso(_first(_DT_KEYS, flat))
    source = str(flat.get("source") or "qdrant")

    return {
        "id": str(point.id),
        "content": text,
        "memory": text,
        "type": mem_type,
        "tags": tags,
        "created_at": created_at,
        "source": source,
        # Everything else rides along for the mapper's supporting-data footer.
        "payload": {k: v for k, v in flat.items() if k not in _TEXT_KEYS},
        "collection": collection,
        "has_vector": bool(point.vector),
    }


def dump_collection(client: Any, collection: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Scroll an entire collection (or up to ``limit`` points) into memory dicts."""
    memories: list[dict[str, Any]] = []
    offset: Any = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,  # dense vectors are noise for memory text
        )
        for p in points:
            mem = point_to_memory(p, collection)
            if mem:
                memories.append(mem)
                if limit and len(memories) >= limit:
                    return memories
        if next_offset is None:
            break
        offset = next_offset
    return memories


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:6333", help="Qdrant server URL")
    parser.add_argument("--api-key", default=None, help="Qdrant Cloud API key")
    parser.add_argument("--in-memory", action="store_true", help="Attach to embedded in-memory instance (seed path)")
    parser.add_argument("--collection", required=True, help="Collection name to dump")
    parser.add_argument("--out", required=True, help="Output export JSON path")
    parser.add_argument("--limit", type=int, default=None, help="Cap on points dumped")
    args = parser.parse_args(argv)

    try:
        from qdrant_client import QdrantClient
    except ImportError:
        print("qdrant-client is required: pip install qdrant-client", file=sys.stderr)
        return 2

    client = QdrantClient(":memory:") if args.in_memory else QdrantClient(
        url=args.url, api_key=args.api_key
    )
    if args.in_memory:
        # The seed script stores its client handle here so the dump shares it.
        from qdrant_client import QdrantClient as _QC
        from qdrant_client.local.qdrant_local import QdrantLocal

        _SHARED = getattr(sys.modules.get("__main__"), "_QD_SHARED", None)
        if _SHARED is not None and isinstance(_SHARED, QdrantLocal):
            client._client = _SHARED  # reuse the seeded in-memory store

    try:
        collections = [c.name for c in client.get_collections().collections]
    except Exception as exc:  # pragma: no cover - network path
        print(f"Failed to reach Qdrant at {args.url}: {exc}", file=sys.stderr)
        return 1
    if args.collection not in collections:
        print(f"Collection '{args.collection}' not found. Available: {collections}", file=sys.stderr)
        return 1

    memories = dump_collection(client, args.collection, limit=args.limit)
    out = {
        "provider": "qdrant",
        "collection": args.collection,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "memories": memories,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(memories)} memories from '{args.collection}' -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
