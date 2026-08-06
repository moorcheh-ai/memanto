#!/usr/bin/env python
"""Phase 1 — dump the live Graphiti graph to ``data/graphiti_raw_export.json``.

This file is the migration's source of truth: it is read by the adapter and by
nothing else, and it is never edited by hand. Graphiti has no built-in
"export the whole graph" command, so the dump is assembled from its own public
accessors (``graphiti.nodes.*`` / ``graphiti.edges.*``) rather than raw Cypher,
which keeps it portable across the Neo4j and FalkorDB backends.

Vector embeddings are the one thing dropped. They are hundreds of floats per
record, they are specific to whichever embedding model happened to be
configured, and Memanto re-embeds on ingest anyway — keeping them would bloat
the artifact past the point of being human-inspectable for zero fidelity gain.
Every other field is preserved verbatim.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphiti_okf import graphiti_client  # noqa: E402
from graphiti_okf.runtime import RAW_EXPORT_PATH, load_env, log  # noqa: E402

_DROP_FIELDS = {"name_embedding", "fact_embedding"}


def _graphiti_version() -> str:
    try:
        return version("graphiti-core")
    except PackageNotFoundError:  # pragma: no cover - always installed in practice
        return "unknown"


def _dump(records: list) -> list[dict]:
    return [record.model_dump(mode="json", exclude=_DROP_FIELDS) for record in records]


async def export_graph(group: str) -> dict:
    graphiti = graphiti_client.build_graphiti()
    try:
        entity_nodes = await graphiti.nodes.entity.get_by_group_ids([group])
        episodes = await graphiti.nodes.episode.get_by_group_ids([group])
        entity_edges = await graphiti.edges.entity.get_by_group_ids([group])
        try:
            communities = await graphiti.nodes.community.get_by_group_ids([group])
        except Exception as exc:
            # Community detection is optional; an absent community table is not
            # a failed export, but it should be visible rather than swallowed.
            log(f"  note: no communities read ({type(exc).__name__}: {exc})")
            communities = []
    finally:
        await graphiti.close()

    return {
        "source": "graphiti",
        "graphiti_version": _graphiti_version(),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "group_id": group,
        "config": graphiti_client.describe_config(),
        "embeddings_excluded": sorted(_DROP_FIELDS),
        "episodes": _dump(episodes),
        "entity_nodes": _dump(entity_nodes),
        "entity_edges": _dump(entity_edges),
        "communities": _dump(communities),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=RAW_EXPORT_PATH,
        help=f"Destination JSON path (default: {RAW_EXPORT_PATH}).",
    )
    args = parser.parse_args()

    load_env()
    group = graphiti_client.group_id()
    log(f"Exporting Graphiti group '{group}'...")
    export = asyncio.run(export_graph(group))

    counts = {
        key: len(export[key])
        for key in ("episodes", "entity_nodes", "entity_edges", "communities")
    }
    total = sum(counts.values())
    if total == 0:
        raise SystemExit(
            f"ERROR: Graphiti group '{group}' is empty — nothing to export. "
            "Run scripts/populate_graphiti.py first. Refusing to write an empty "
            "export, because a downstream migration built on it would be meaningless."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")

    for key, count in counts.items():
        log(f"  {key:<14} {count}")
    temporal = sum(
        1 for edge in export["entity_edges"] if edge.get("invalid_at") or edge.get("expired_at")
    )
    log(f"  {'superseded':<14} {temporal} entity edge(s) carry a closed validity interval")
    log(f"\nWrote {total} objects to {args.output}")


if __name__ == "__main__":
    main()
