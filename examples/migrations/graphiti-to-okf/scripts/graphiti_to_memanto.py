#!/usr/bin/env python
"""Phase 2 — the adapter: raw Graphiti export → something the memanto CLI eats.

Writes two artifacts from one mapping pass:

``data/graphiti_okf_bundle/``
    An OKF bundle for ``memanto migrate okf``. **This is the recommended path.**
    It is the only one that preserves ``source: graphiti``, the per-record
    confidence derived from temporal standing, and the exact Memanto type.

``data/memanto_provider_import.json``
    The same memories in the shape ``memanto migrate mem0 --file`` accepts. The
    CLI has no ``graphiti`` provider, and the savings report is only wired to
    the provider paths, so this exists to obtain that report. It costs
    fidelity: ``map_mem0`` overwrites source with ``"mem0"`` and confidence
    with a flat ``0.8``.

No memory is written to Memanto here. Importing is the CLI's job — this script
only transforms.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphiti_okf.mapping import map_export  # noqa: E402
from graphiti_okf.okf_writer import write_bundle  # noqa: E402
from graphiti_okf.provider_json import write_provider_export  # noqa: E402
from graphiti_okf.report import render_mapping_table, render_run_summary  # noqa: E402
from graphiti_okf.runtime import (  # noqa: E402
    DATA_DIR,
    OKF_BUNDLE_DIR,
    PROVIDER_JSON_PATH,
    RAW_EXPORT_PATH,
    log,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=RAW_EXPORT_PATH,
        help=f"Raw Graphiti export JSON (default: {RAW_EXPORT_PATH}).",
    )
    parser.add_argument(
        "--okf-out",
        type=Path,
        default=OKF_BUNDLE_DIR,
        help=f"OKF bundle output directory (default: {OKF_BUNDLE_DIR}).",
    )
    parser.add_argument(
        "--provider-out",
        type=Path,
        default=PROVIDER_JSON_PATH,
        help=f"Provider-JSON output path (default: {PROVIDER_JSON_PATH}).",
    )
    parser.add_argument(
        "--agent-label",
        default="graphiti-import",
        help="Label written into the bundle's root index.md.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(
            f"ERROR: {args.input} not found. Run scripts/export_graphiti.py first."
        )

    export = json.loads(args.input.read_text(encoding="utf-8"))
    records = map_export(export)
    if not records:
        raise SystemExit(
            f"ERROR: {args.input} produced zero mapped memories. The export is "
            "empty or malformed; refusing to write an empty bundle."
        )

    bundle = write_bundle(records, args.okf_out, agent_label=args.agent_label)
    write_provider_export(records, export, args.provider_out)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    table_path = DATA_DIR / "mapping_table.md"
    table_path.write_text(render_mapping_table(export, records), encoding="utf-8")

    log(render_run_summary(export, records))
    log("")
    log(f"OKF bundle      : {bundle['output_path']}")
    log("  per type      : " + ", ".join(f"{k}={v}" for k, v in bundle["per_type_counts"].items()))
    log(f"Provider JSON   : {args.provider_out}")
    log(f"Mapping table   : {table_path}")
    log("")
    log("Next: memanto migrate okf " + str(args.okf_out) + " --dry-run")


if __name__ == "__main__":
    main()
