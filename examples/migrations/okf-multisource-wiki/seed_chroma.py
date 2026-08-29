"""Populate a real Chroma collection with lived-in agent memories.

Chroma is how many RAG / DIY agents trap long-term memory as opaque vectors.
This seeder is an actual PersistentClient run — not hand-written JSON pretending
to be a migration source.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings


class DeterministicHashEmbedding(EmbeddingFunction[Documents]):
    """Offline, deterministic embeddings so the demo needs no model download."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def name() -> str:
        return "deterministic_hash"

    def get_config(self) -> dict[str, str]:
        return {"type": "deterministic_hash", "dims": "32"}

    def __call__(self, input: Documents) -> Embeddings:
        vectors: Embeddings = []
        for text in input:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            # Expand to 32 dims in [-1, 1].
            base = [((b / 255.0) * 2.0) - 1.0 for b in digest]
            vectors.append(base)
        return vectors


# Six "weeks" of a coding-assistant agent. Includes a preference correction and
# a resolved contradiction so consolidation has something real to reconcile.
_SESSIONS: list[dict[str, Any]] = [
    {
        "session": "week-1-onboarding",
        "day_offset": 0,
        "memories": [
            {
                "id": "chroma-name",
                "type": "fact",
                "text": "User's name is Priya Shah.",
                "categories": ["personal_details"],
            },
            {
                "id": "chroma-lang",
                "type": "preference",
                "text": "Priya prefers TypeScript over Python for production services.",
                "categories": ["personal_preferences"],
            },
            {
                "id": "chroma-editor",
                "type": "preference",
                "text": "Primary editor is Cursor with vim keybindings enabled.",
                "categories": ["personal_preferences"],
            },
        ],
    },
    {
        "session": "week-2-stack",
        "day_offset": 7,
        "memories": [
            {
                "id": "chroma-db",
                "type": "fact",
                "text": "Primary database is PostgreSQL 16 on port 5432.",
                "categories": ["professional_info"],
            },
            {
                "id": "chroma-deploy",
                "type": "instruction",
                "text": "Never deploy on Fridays without an explicit go-ahead from Priya.",
                "categories": ["instructions"],
            },
            {
                "id": "chroma-tests",
                "type": "commitment",
                "text": "Every PR must include pytest coverage for new modules.",
                "categories": ["tasks"],
            },
        ],
    },
    {
        "session": "week-3-correction",
        "day_offset": 14,
        "memories": [
            {
                "id": "chroma-lang-correction",
                "type": "preference",
                "text": (
                    "Correction: Priya now prefers Python (FastAPI) for internal "
                    "services; TypeScript stays only for the frontend."
                ),
                "categories": ["personal_preferences"],
                "provenance": "corrected",
                "supersedes": "chroma-lang",
            },
            {
                "id": "chroma-timezone",
                "type": "fact",
                "text": "Priya works in Asia/Kolkata (UTC+5:30).",
                "categories": ["personal_details"],
            },
        ],
    },
    {
        "session": "week-4-incident",
        "day_offset": 21,
        "memories": [
            {
                "id": "chroma-incident",
                "type": "event",
                "text": (
                    "Incident INC-441 resolved: pgbouncer pool exhaustion after "
                    "a migration spike. Root cause was max_client_conn=100."
                ),
                "categories": ["events"],
            },
            {
                "id": "chroma-decision-pool",
                "type": "decision",
                "text": "Decision: raise pgbouncer max_client_conn to 400 permanently.",
                "categories": ["decisions"],
            },
        ],
    },
    {
        "session": "week-5-team",
        "day_offset": 28,
        "memories": [
            {
                "id": "chroma-rel",
                "type": "relationship",
                "text": "On-call buddy is Marcus Chen (Slack @marcus).",
                "categories": ["relationships"],
            },
            {
                "id": "chroma-goal",
                "type": "goal",
                "text": "Goal: cut p95 API latency under 120ms before Q4 review.",
                "categories": ["goals_and_plans"],
            },
        ],
    },
    {
        "session": "week-6-style",
        "day_offset": 35,
        "memories": [
            {
                "id": "chroma-style",
                "type": "preference",
                "text": (
                    "Response style: concise bullets first, then optional detail. "
                    "No emojis in commit messages."
                ),
                "categories": ["personal_preferences"],
            },
            {
                "id": "chroma-secret-policy",
                "type": "instruction",
                "text": "Never commit .env files; use Doppler for secrets.",
                "categories": ["instructions"],
            },
        ],
    },
]


def seed_chroma(data_dir: Path, *, force: bool = False) -> dict[str, Any]:
    """Run a real Chroma PersistentClient and return a provenance report."""
    data_dir = data_dir.resolve()
    if force and data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(data_dir))
    collection = client.get_or_create_collection(
        name="agent_long_term_memory",
        embedding_function=DeterministicHashEmbedding(),
        metadata={"source": "okf-multisource-wiki", "kind": "agent_memory"},
    )

    # Clear existing ids on re-seed without deleting the client path mid-run.
    existing = collection.get()
    if existing and existing.get("ids"):
        collection.delete(ids=existing["ids"])

    base = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for block in _SESSIONS:
        when = base + timedelta(days=int(block["day_offset"]))
        for mem in block["memories"]:
            ids.append(mem["id"])
            documents.append(mem["text"])
            meta: dict[str, Any] = {
                "memory_type": mem["type"],
                "session": block["session"],
                "categories": ",".join(mem["categories"]),
                "created_at": when.isoformat().replace("+00:00", "Z"),
                "provenance": mem.get("provenance", "explicit_statement"),
            }
            if mem.get("supersedes"):
                meta["supersedes"] = mem["supersedes"]
            metadatas.append(meta)

    collection.add(ids=ids, documents=documents, metadatas=metadatas)

    report = {
        "backend": "chromadb.PersistentClient",
        "path": str(data_dir),
        "collection": "agent_long_term_memory",
        "count": collection.count(),
        "ids": ids,
        "sessions": [b["session"] for b in _SESSIONS],
    }
    (data_dir / "seed_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    root = Path(__file__).resolve().parent / "data" / "chroma"
    print(json.dumps(seed_chroma(root, force=True), indent=2))
