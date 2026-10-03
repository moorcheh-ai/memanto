"""Export a LangMem store to ``langmem_export.json``.

Just ``store.search`` over the namespace, one record per surviving memory,
keeping LangMem's native fields (namespace, key, value, created_at,
updated_at). This file is the hand-off point -- anyone with their own LangMem
store can produce the same shape (``store.search(namespace)`` -> item dicts)
and run the adapter against it directly, without the sample conversation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.store.base import BaseStore

from .conversation import USER_ID


def export_store(store: BaseStore, user_id: str = USER_ID) -> dict[str, Any]:
    """Return the LangMem store as a portable export dict."""
    namespace = ("memories", user_id)
    items = store.search(namespace)
    records: list[dict[str, Any]] = []
    for item in items:
        records.append(
            {
                "namespace": list(item.namespace),
                "key": item.key,
                "value": item.value,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
        )
    # Stable order (oldest first) so the export and bundle are reproducible.
    records.sort(key=lambda r: (r["created_at"] or "", r["key"]))
    return {
        "source": "langmem",
        "namespace": list(namespace),
        "user_id": user_id,
        "count": len(records),
        "memories": records,
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    # LangGraph may hand back either a datetime or an ISO string.
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def write_export(store: BaseStore, dest: Path, user_id: str = USER_ID) -> Path:
    export = export_store(store, user_id=user_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")
    return dest


def load_export(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
