#!/usr/bin/env python3
"""Seed a Graphiti graph from the lived-in fixture ($0 with mocks).

Modes
-----
offline (default)
    Build ``out/graphiti_export.json`` directly from the fixture's
    ``expected_graph`` + episodes. Guarantees a reproducible dry-run without
    installing graphiti-core / spinning up FalkorDB. The export schema matches
    what the live exporter writes.

live
    Construct Graphiti with MockLLM + MockEmbedder + MockCrossEncoder and a
    local graph backend (Kuzu file DB preferred; FalkorDB Docker if
    ``GRAPHITI_BACKEND=falkordb``), then ``add_episode`` for each fixture
    episode. After seeding, dump via export_graphiti.

This keeps the examples-only Path B demo runnable at $0 while still offering a
real Graphiti ingestion path when dependencies are present.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / 'fixtures' / 'lived_in_script.json'
OUT = ROOT / 'out' / 'graphiti_export.json'
META = ROOT / 'out' / 'seed_meta.json'


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def build_offline_export(fixture: dict[str, Any]) -> dict[str, Any]:
    """Materialize a Graphiti-shaped export from the fixture (dry-run seed)."""
    eg = fixture['expected_graph']
    episodes = []
    for ep in fixture['episodes']:
        episodes.append(
            {
                'id': ep['id'],
                'uuid': str(uuid.uuid5(uuid.NAMESPACE_URL, f"graphiti-okf:{ep['id']}")),
                'name': ep.get('name'),
                'content': ep.get('content'),
                'source': ep.get('source'),
                'source_description': ep.get('source_description'),
                'reference_time': ep.get('reference_time'),
                'group_id': fixture['group_id'],
            }
        )
    return {
        'source': 'graphiti',
        'schema_version': 'graphiti-okf/1.0',
        'seed_mode': 'offline',
        'exported_at': _now(),
        'group_id': fixture['group_id'],
        'story': fixture.get('story'),
        'episodes': episodes,
        'entities': eg['entities'],
        'edges': eg['edges'],
        'invalidated': eg.get('invalidated', []),
    }


async def seed_live(fixture: dict[str, Any], backend: str) -> dict[str, Any]:
    """Real Graphiti add_episode loop with mocks + local backend."""
    sys.path.insert(0, str(ROOT))
    from mocks.cross_encoder import MockCrossEncoder
    from mocks.embedder import MockEmbedder
    from mocks.llm_client import MockLLMClient

    try:
        from graphiti_core import Graphiti
    except ImportError as e:
        raise SystemExit(
            'graphiti-core not installed. pip install -r requirements.txt '
            'or use --mode offline'
        ) from e

    llm = MockLLMClient(FIXTURE)
    embedder = MockEmbedder(embedding_dim=64)
    reranker = MockCrossEncoder()

    graph_dir = ROOT / '.graphiti-data'
    graph_dir.mkdir(exist_ok=True)

    graphiti: Any
    if backend == 'falkordb':
        from graphiti_core.driver.falkordb_driver import FalkorDriver

        driver = FalkorDriver(
            host='localhost',
            port=6379,
            username='',
            password='',
        )
        graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm,
            embedder=embedder,
            cross_encoder=reranker,
        )
    else:
        # Default: embedded Kuzu (no Docker)
        from graphiti_core.driver.kuzu_driver import KuzuDriver

        db_path = str(graph_dir / 'kuzu.db')
        driver = KuzuDriver(db=db_path)
        graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm,
            embedder=embedder,
            cross_encoder=reranker,
        )

    await graphiti.build_indices_and_constraints()

    group_id = fixture['group_id']
    episode_results = []
    for ep in fixture['episodes']:
        ref = datetime.fromisoformat(ep['reference_time'].replace('Z', '+00:00'))
        print(f"  add_episode {ep['id']} @ {ep['reference_time']}")
        try:
            result = await graphiti.add_episode(
                name=ep.get('name') or ep['id'],
                episode_body=ep['content'],
                source_description=ep.get('source_description') or 'fixture',
                reference_time=ref,
                group_id=group_id,
            )
            episode_results.append(
                {
                    'id': ep['id'],
                    'ok': True,
                    'result_type': type(result).__name__,
                }
            )
        except Exception as exc:  # noqa: BLE001 — surface per-episode failures
            print(f"  ! episode {ep['id']} failed: {exc}")
            episode_results.append({'id': ep['id'], 'ok': False, 'error': str(exc)})

    meta = {
        'seed_mode': 'live',
        'backend': backend,
        'group_id': group_id,
        'episodes': episode_results,
        'seeded_at': _now(),
    }
    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')

    # Close driver if available
    close = getattr(getattr(graphiti, 'driver', None), 'close', None)
    if close:
        maybe = close()
        if asyncio.iscoroutine(maybe):
            await maybe

    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description='Seed Graphiti from lived-in fixture')
    parser.add_argument(
        '--mode',
        choices=('offline', 'live'),
        default='offline',
        help='offline = fixture→export (default, $0); live = real add_episode',
    )
    parser.add_argument(
        '--backend',
        choices=('kuzu', 'falkordb'),
        default='kuzu',
        help='Graph backend for --mode live (default kuzu embedded)',
    )
    parser.add_argument('--out', type=Path, default=OUT)
    args = parser.parse_args()

    fixture = load_fixture()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == 'offline':
        export = build_offline_export(fixture)
        args.out.write_text(json.dumps(export, indent=2) + '\n', encoding='utf-8')
        print(f"[offline] wrote {args.out}")
        print(
            f"  episodes={len(export['episodes'])} "
            f"entities={len(export['entities'])} edges={len(export['edges'])}"
        )
        return

    print(f"[live] seeding via Graphiti backend={args.backend}")
    meta = asyncio.run(seed_live(fixture, args.backend))
    ok = sum(1 for e in meta['episodes'] if e.get('ok'))
    print(f"[live] episodes ok={ok}/{len(meta['episodes'])} meta→{META}")
    if ok != len(meta['episodes']):
        raise SystemExit(1)
    print('Next: python export_graphiti.py --mode live')


if __name__ == '__main__':
    main()
