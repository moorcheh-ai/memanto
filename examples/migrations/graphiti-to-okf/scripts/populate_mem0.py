#!/usr/bin/env python
"""Phase 4 — stand up a small, lived-in Mem0 store for the consolidation act.

This is the second source in the Path C story. The memories here deliberately
overlap and extend the Graphiti dataset (same person, same Atlas project) so
the consolidated OKF export has to absorb new facts without inventing
duplicates of the ones already migrated from Graphiti.

Requires ``MEM0_API_KEY``. Writes ``data/mem0_export.json`` in the shape
``memanto migrate mem0 --file`` already understands — no adapter needed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphiti_okf.runtime import DATA_DIR, load_env, log  # noqa: E402

# A second, smaller lived-in store. Overlaps the Graphiti identity (Daniel
# Okafor / Atlas / Halcyon) so consolidation is a real merge, not two
# unrelated dumps glued together. Includes one correction so Mem0 itself has
# temporal tension for the OKF diff to show.
MEM0_TURNS: tuple[tuple[str, str], ...] = (
    (
        "I'm Daniel Okafor, principal engineer at Halcyon Data working on Atlas. "
        "I prefer short, decision-heavy standups — fifteen minutes max.",
        "personal_preferences",
    ),
    (
        "We just committed to publishing a public changelog for Atlas every Friday. "
        "That's a new process commitment.",
        "goals_and_plans",
    ),
    (
        "Actually, scrap the Friday changelog — we decided Mondays work better for "
        "the customer-facing audience. Changelog goes out every Monday instead.",
        "decisions",
    ),
    (
        "My on-call rotation buddy is Priya Shah. She's the other principal on Atlas.",
        "relationships",
    ),
    (
        "We evaluated Pinecone for a vector side-store and rejected it — sticking "
        "with Moorcheh/Memanto for agent memory instead.",
        "decisions",
    ),
    (
        "Personal preference update: I now prefer Linear over Jira for issue "
        "tracking. The team migrated last week.",
        "personal_preferences",
    ),
)

USER_ID = "daniel-okafor-atlas"


def _require_mem0():
    api_key = os.getenv("MEM0_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "ERROR: MEM0_API_KEY is not set. The consolidation act needs a real "
            "Mem0 store — copy .env.example and fill MEM0_API_KEY, then re-run."
        )
    try:
        from mem0 import MemoryClient
    except ImportError as exc:
        raise SystemExit(
            "ERROR: mem0 package not installed. "
            "pip install 'mem0ai' and re-run."
        ) from exc
    return MemoryClient(api_key=api_key)


def populate() -> dict:
    client = _require_mem0()
    written: list[dict] = []

    # Wipe any previous demo memories for this user so re-runs are reproducible.
    try:
        existing = client.get_all(user_id=USER_ID) or {}
        for mem in existing.get("results") or existing.get("memories") or []:
            mid = mem.get("id")
            if mid:
                client.delete(mid)
    except Exception as exc:
        log(f"  note: could not clear prior Mem0 state ({type(exc).__name__}: {exc})")

    for text, category in MEM0_TURNS:
        log(f"  Mem0 add [{category}]: {text[:72]}...")
        result = client.add(
            [{"role": "user", "content": text}],
            user_id=USER_ID,
            metadata={"category": category, "source": "graphiti-to-okf-demo"},
        )
        written.append({"input": text, "category": category, "result": result})
        time.sleep(0.4)

    # Pull the real store back out — this is the source artifact.
    export_payload = client.get_all(user_id=USER_ID) or {}
    memories = export_payload.get("results") or export_payload.get("memories") or []
    if not memories:
        raise SystemExit(
            "ERROR: Mem0 get_all returned zero memories after populate. "
            "Refusing to write an empty export."
        )

    document = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "export_scope": {"user_id": USER_ID},
        "summary": {
            "entity_count": 0,
            "scope_count": 1,
            "memory_count": len(memories),
        },
        "entities": [],
        "memories": [
            {
                "id": m.get("id"),
                "memory": m.get("memory") or m.get("content") or "",
                "categories": m.get("categories")
                or ([m.get("metadata", {}).get("category")] if m.get("metadata") else []),
                "created_at": m.get("created_at"),
                "updated_at": m.get("updated_at"),
                "metadata": m.get("metadata") or {},
                "export_scope": {"user_id": USER_ID},
            }
            for m in memories
        ],
    }
    return {"document": document, "writes": len(written)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "mem0_export.json",
        help="Where to write the Mem0 export JSON.",
    )
    args = parser.parse_args()
    load_env()

    log(f"Populating Mem0 user '{USER_ID}'...")
    result = populate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result["document"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log(
        f"Wrote {result['document']['summary']['memory_count']} memories "
        f"({result['writes']} turns) to {args.output}"
    )


if __name__ == "__main__":
    main()
