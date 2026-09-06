"""Adapters that transform proprietary stores into Memanto-shaped memory dicts.

These adapters *feed* ``memanto migrate okf`` — they do not reimplement Memanto's
importer. Output is an OKF bundle written by ``okf_writer``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import chromadb
from seed_chroma import DeterministicHashEmbedding

# Map free-form source kinds onto Memanto's fixed vocabulary when possible.
_KIND_TO_TYPE: dict[str, str | None] = {
    "fact": "fact",
    "preference": "preference",
    "goal": "goal",
    "decision": "decision",
    "artifact": "artifact",
    "learning": "learning",
    "event": "event",
    "instruction": "instruction",
    "relationship": "relationship",
    "context": "context",
    "observation": "observation",
    "commitment": "commitment",
    "error": "error",
    "constraint": "instruction",  # closest Memanto slot
}


def _title(text: str) -> str:
    clean = " ".join(text.strip().split())
    return clean if len(clean) <= 80 else clean[:77].rstrip() + "..."


def load_chroma_memories(chroma_dir: Path) -> list[dict[str, Any]]:
    """Read every point from the seeded Chroma collection."""
    client = chromadb.PersistentClient(path=str(chroma_dir.resolve()))
    collection = client.get_collection(
        name="agent_long_term_memory",
        embedding_function=DeterministicHashEmbedding(),
    )
    raw = collection.get(include=["documents", "metadatas"])
    memories: list[dict[str, Any]] = []
    for idx, doc_id in enumerate(raw["ids"]):
        meta = (raw["metadatas"] or [{}])[idx] or {}
        text = (raw["documents"] or [""])[idx] or ""
        categories = [
            c.strip() for c in str(meta.get("categories", "")).split(",") if c.strip()
        ]
        mem_type = _KIND_TO_TYPE.get(str(meta.get("memory_type", "")).lower())
        memories.append(
            {
                "id": f"chroma:{doc_id}",
                "chroma_id": doc_id,
                "title": _title(text),
                "content": text,
                "description": _title(text),
                "type": mem_type,
                "tags": [
                    "source:chroma",
                    *categories,
                    f"session:{meta.get('session')}",
                ],
                "confidence": 0.86,
                "source": "chroma",
                "source_ref": f"chroma://agent_long_term_memory/{doc_id}",
                "provenance": meta.get("provenance", "imported"),
                "created_at": meta.get("created_at"),
                "session_id": meta.get("session"),
                "supersedes": meta.get("supersedes"),
                "sources": ["chroma"],
            }
        )
    return memories


def load_sqlite_memories(db_path: Path) -> list[dict[str, Any]]:
    """Read every row from the proprietary SQLite agent_memories table."""
    memories: list[dict[str, Any]] = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, kind, body, thread_id, confidence, created_at, meta_json "
            "FROM agent_memories ORDER BY created_at ASC"
        ).fetchall()
    for row in rows:
        meta = json.loads(row["meta_json"] or "{}")
        kind = str(row["kind"]).lower()
        text = row["body"]
        memories.append(
            {
                "id": f"sqlite:{row['id']}",
                "sqlite_id": row["id"],
                "title": _title(text),
                "content": text,
                "description": _title(text),
                "type": _KIND_TO_TYPE.get(kind),
                "tags": [
                    "source:sqlite",
                    f"thread:{row['thread_id']}",
                    f"topic:{meta.get('topic', 'general')}",
                ],
                "confidence": float(row["confidence"] or 0.8),
                "source": "sqlite-agent-store",
                "source_ref": f"sqlite://agent_memories/{row['id']}",
                "provenance": "imported",
                "created_at": row["created_at"],
                "session_id": row["thread_id"],
                "sources": ["sqlite"],
            }
        )
    return memories
