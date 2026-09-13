#!/usr/bin/env python3
"""
Build a reproducible Hindsight transfer ZIP for the #1609 showcase.

The archive follows Hindsight schema v1 (manifest + documents/*.json +
observations.json). It simulates a lived-in coding-agent bank with evolving
preferences, a corrected stack choice, and consolidated observations — the
kind of memory that normally dies when you switch tools.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

NOW = datetime(2026, 7, 15, 14, 30, 0, tzinfo=timezone.utc)

DOCUMENTS = [
    {
        "id": "doc-onboarding-001",
        "original_text": "Team standup notes and stack decisions for Project Atlas.",
        "tags": ["project-atlas", "standup"],
        "created_at": "2026-06-01T09:00:00Z",
        "chunks": [
            {"chunk_index": 0, "chunk_text": "We chose Rust for the ingestion worker."},
            {"chunk_index": 1, "chunk_text": "Auth will use JWT, not session cookies."},
        ],
        "facts": [
            {
                "text": "Project Atlas ingestion worker is implemented in Rust.",
                "fact_type": "world",
                "context": "architecture decision",
                "mentioned_at": "2026-06-01T09:05:00Z",
                "tags": ["rust", "architecture"],
                "entities": ["Project Atlas"],
            },
            {
                "text": "User prefers PostgreSQL 16 over MySQL for new services.",
                "fact_type": "opinion",
                "context": "database preference",
                "mentioned_at": "2026-06-02T11:20:00Z",
                "tags": ["postgres", "preference"],
            },
            {
                "text": "Auth migrated to JWT — session cookies are deprecated.",
                "fact_type": "decision",
                "context": "security migration",
                "mentioned_at": "2026-06-10T16:45:00Z",
                "tags": ["auth", "jwt"],
                "causal_relations": [
                    {"relation_type": "supersedes", "target_fact_index": 0}
                ],
            },
        ],
    },
    {
        "id": "doc-incident-014",
        "original_text": "Postmortem: staging outage during cache rollout.",
        "tags": ["incident", "cache"],
        "created_at": "2026-07-01T18:00:00Z",
        "chunks": [
            {
                "chunk_index": 0,
                "chunk_text": "Redis TTL misconfiguration caused stale graph indexes.",
            }
        ],
        "facts": [
            {
                "text": "Staging outage on 2026-07-01 was caused by Redis TTL misconfiguration.",
                "fact_type": "experience",
                "context": "incident postmortem",
                "occurred_start": "2026-07-01T17:55:00Z",
                "tags": ["redis", "incident"],
            },
            {
                "text": "Always run memanto migrate --dry-run before cutting over agent memory providers.",
                "fact_type": "belief",
                "context": "operational lesson",
                "mentioned_at": "2026-07-02T10:00:00Z",
                "tags": ["migration", "runbook"],
            },
        ],
    },
]

OBSERVATIONS = [
    {
        "text": "The developer consistently chooses Rust for performance-critical services and PostgreSQL for durable state.",
        "tags": ["project-atlas", "stack"],
        "mentioned_at": "2026-07-10T08:00:00Z",
        "proof_count": 3,
        "sources": [
            {"document_id": "doc-onboarding-001", "fact_index": 0},
            {"document_id": "doc-onboarding-001", "fact_index": 1},
        ],
    }
]


def build_archive_bytes() -> bytes:
    fact_total = sum(len(doc["facts"]) for doc in DOCUMENTS)
    manifest = {
        "schema_version": 1,
        "source_bank_id": "project-atlas-agent",
        "exported_at": NOW.isoformat().replace("+00:00", "Z"),
        "document_count": len(DOCUMENTS),
        "fact_count": fact_total,
        "observation_count": len(OBSERVATIONS),
        "archive_type": "documents",
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for index, document in enumerate(DOCUMENTS):
            zf.writestr(
                f"documents/{index:06d}.json",
                json.dumps(document, indent=2),
            )
        zf.writestr(
            "observations.json",
            json.dumps(OBSERVATIONS, indent=2),
        )
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
    return buffer.getvalue()


def main() -> None:
    out = Path(__file__).resolve().parent / "sample-data" / "project-atlas-agent.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_archive_bytes())
    print(f"Wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
