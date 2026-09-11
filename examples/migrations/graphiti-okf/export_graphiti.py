#!/usr/bin/env python3
"""Export Graphiti graph → out/graphiti_export.json."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / 'fixtures' / 'lived_in_script.json'
DEFAULT_OUT = ROOT / 'out' / 'graphiti_export.json'
META = ROOT / 'out' / 'seed_meta.json'


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def write_offline(out: Path, *, reuse: bool = False) -> Path:
    if reuse and out.exists():
        print(f'[offline] using existing {out}')
        return out
    from seed_graphiti import build_offline_export, load_fixture

    export = build_offline_export(load_fixture())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(export, indent=2) + '\n', encoding='utf-8')
    print(f'[offline] generated {out}')
    return out


def write_live_fallback(out: Path) -> Path:
    from seed_graphiti import build_offline_export, load_fixture

    export = build_offline_export(load_fixture())
    export['seed_mode'] = 'live-fallback'
    export['exported_at'] = _now()
    export['note'] = (
        'Live Graphiti seed completed (see seed_meta.json); export assembled from '
        'fixture expected_graph pending richer driver dump helpers.'
    )
    if META.exists():
        export['seed_meta'] = json.loads(META.read_text(encoding='utf-8'))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(export, indent=2) + '\n', encoding='utf-8')
    print(f'[live-fallback] wrote {out}')
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('offline', 'live'), default='offline')
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        '--reuse-existing',
        action='store_true',
        help='Offline only: reuse out/graphiti_export.json if present instead of regenerating',
    )
    args = parser.parse_args()

    if args.mode == 'offline':
        write_offline(args.out, reuse=args.reuse_existing)
        return

    if not META.exists():
        print(
            '[live] No seed_meta.json — run seed_graphiti.py --mode live first; '
            'refusing to write a live-fallback that claims a completed seed.',
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        write_live_fallback(args.out)
    except Exception as exc:  # noqa: BLE001
        print(f'[live] dump unavailable ({exc}); writing fallback export', file=sys.stderr)
        write_live_fallback(args.out)


if __name__ == '__main__':
    main()
