"""Run a local OKF -> Memanto schema -> OKF production-code round trip."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from memanto.app.services.okf_export_service import OkfExportService
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle


def round_trip(source: Path, target: Path) -> dict[str, Any]:
    """Map an OKF bundle to Memanto rows and export those rows back to OKF."""
    source_export = load_okf_bundle(source)
    rows = map_okf(source_export)
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_type[row.get("type") or "observation"].append(row)

    service = OkfExportService(exports_dir=target.parent)
    return service.write_okf_bundle(
        agent_id="portability-audit-demo",
        memories_by_type=dict(by_type),
        output_dir=target,
        split="file",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Round-trip a local OKF bundle through Memanto's schema."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    result = round_trip(args.source, args.target)
    print(
        f"Round-tripped {result['total_memories']} memories to {result['output_path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
