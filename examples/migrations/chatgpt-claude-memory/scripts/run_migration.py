#!/usr/bin/env python3
"""Map the generated source archives into Memanto memory and (optionally)
export a valid OKF bundle.

This is the heart of the Path B demo: it feeds the *new* ChatGPT/Claude
adapters through the *shipped* Memanto tooling, proving the "lib
the memory your assistant has built about you" story without touching the
CLI internals.

    python3 scripts/run_migration.py                 # map + print summary
    python3 scripts/run_migration.py --export-okf    # also write okf/ bundle
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

# Run against the local memanto checkout so the demo tracks the adapter source.
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent.parent.parent  # -> /tmp/memanto
sys.path.insert(0, str(PROJECT))

from memanto.app.services.okf_export_service import OkfExportService  # noqa: E402
from memanto.cli.migrate.mappers import map_chatgpt, map_claude  # noqa: E402

DATA = HERE.parent / "data"
OKF_DIR = HERE.parent / "okf"


def load(source: str) -> tuple[str, dict]:
    path = DATA / f"{source}_conversations.json"
    with path.open() as fh:
        return source, json.load(fh)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export-okf", action="store_true",
                    help="Also write the OKF bundle under okf/")
    args = ap.parse_args()

    providers: dict[str, list[dict]] = {"claude": [], "chatgpt": []}
    for source, _mapper in (("claude", map_claude), ("chatgpt", map_chatgpt)):
        _, export = load(source)
        providers[source] = _mapper(export)

    all_rows = providers["claude"] + providers["chatgpt"]
    types = Counter(r["type"] for r in all_rows)

    # Render the migration summary (the "migration summary + per-type
    # breakdown" evidence the bounty asks for).
    print("=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"{'source':<10}{'records':<10}{'memories':<12}")
    for source, rows in providers.items():
        print(f"{source:<10}{len(rows):<10}{len(rows):<12}")
    print(f"\n{len(all_rows)} memories mapped, by type:")
    for t, n in types.most_common():
        print(f"  {str(t or 'auto-classify'):<14}{n:>3}")

    preview = HERE.parent / "mapped_preview.json"
    preview.write_text(json.dumps(providers, indent=2, ensure_ascii=False, default=str))
    print(f"\nMapped preview -> {preview}")

    if args.export_okf:
        by_type: dict[str, list[dict]] = {}
        for r in all_rows:
            by_type.setdefault(r["type"] or "context", []).append(r)
        exporter = OkfExportService()
        # The exporter validates that output_path sits inside the agent data
        # directory (~/.memanto), so we write there and copy the finished
        # bundle into the repo so it is the PR artifact.
        result = exporter.write_okf_bundle(
            agent_id="demo-user",
            memories_by_type=by_type,
            output_dir=None,  # default ~/.memanto/exports/demo-user_okf
        )
        src = Path(result["output_path"])
        if OKF_DIR.exists():
            shutil.rmtree(OKF_DIR)
        shutil.copytree(src, OKF_DIR)
        print(f"\nOKF bundle -> {OKF_DIR}")
        print(f"  total: {result['total_memories']}, sections: {result['sections']}")

    # Sanity: the OKF bundle must round-trip (loader reads it back).
    if args.export_okf:
        from memanto.cli.migrate.okf_loader import load_okf_bundle
        reloaded = load_okf_bundle(OKF_DIR)
        print(f"Round-trip load: {len(reloaded.get('memories', []))} memories "
              f"read back from the bundle")


if __name__ == "__main__":
    main()
