#!/usr/bin/env python
"""Phase 1 — ingest the source conversation into a live Graphiti graph.

Episodes are added strictly in chronological order and one at a time. That is
not an optimisation oversight: Graphiti detects contradictions by comparing a
new fact against what it already believes, so ingesting session 4 before
session 2 would produce a graph where the reversals point the wrong way, and
``invalid_at`` would be meaningless. ``add_episode_bulk`` is faster but skips
that edge-invalidation step entirely.

Everything this writes is produced by Graphiti's own extraction pipeline. The
only hand-authored input is the conversation in :mod:`graphiti_okf.dataset`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphiti_okf import graphiti_client  # noqa: E402
from graphiti_okf.dataset import EPISODES, session_span  # noqa: E402
from graphiti_okf.runtime import DATA_DIR, load_env, log  # noqa: E402


async def populate(*, clear: bool, limit: int | None, build_communities: bool) -> dict:
    from graphiti_core.nodes import EpisodeType
    from graphiti_core.utils.maintenance.graph_data_operations import clear_data

    config = graphiti_client.describe_config()
    group = graphiti_client.group_id()
    log(f"Backend      : {config['backend']}")
    log(f"LLM provider : {config['llm_provider']} ({config['llm_model']})")
    log(f"Group id     : {group}")

    graphiti = graphiti_client.build_graphiti()
    episodes = list(EPISODES)[: limit or len(EPISODES)]
    timings: list[dict] = []

    try:
        if clear:
            log(f"Clearing existing data for group '{group}'...")
            await clear_data(graphiti.driver, group_ids=[group])

        log("Building indices and constraints...")
        await graphiti.build_indices_and_constraints()

        log(f"Ingesting {len(episodes)} episode(s) in chronological order...")
        for index, episode in enumerate(episodes, 1):
            started = time.perf_counter()
            await graphiti.add_episode(
                name=episode.name,
                episode_body=episode.body,
                source_description=episode.source_description,
                reference_time=episode.reference_time,
                source=EpisodeType.message,
                group_id=group,
            )
            elapsed = time.perf_counter() - started
            timings.append({"episode": episode.name, "seconds": round(elapsed, 2)})
            log(
                f"  [{index}/{len(episodes)}] {episode.name} "
                f"({episode.reference_time.date()}) — {elapsed:.1f}s"
            )

        if build_communities:
            log("Building communities...")
            started = time.perf_counter()
            communities, _ = await graphiti.build_communities(group_ids=[group])
            log(f"  {len(communities)} community node(s) — {time.perf_counter() - started:.1f}s")
    finally:
        await graphiti.close()

    first, last = session_span()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "episodes_ingested": len(episodes),
        "conversation_span": {"first": first.isoformat(), "last": last.isoformat()},
        "episode_timings": timings,
        "total_seconds": round(sum(t["seconds"] for t in timings), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not wipe the group before ingesting (default is a clean rebuild).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ingest only the first N episodes — for a quick smoke run.",
    )
    parser.add_argument(
        "--no-communities",
        action="store_true",
        help="Skip community detection (saves several LLM calls).",
    )
    args = parser.parse_args()

    load_env()
    manifest = asyncio.run(
        populate(
            clear=not args.keep_existing,
            limit=args.limit,
            build_communities=not args.no_communities,
        )
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "populate_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"\nIngest complete in {manifest['total_seconds']}s. Manifest: {path}")


if __name__ == "__main__":
    main()
