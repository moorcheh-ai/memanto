"""Run a local OKF -> Memanto schema -> OKF production-code round trip."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from memanto.app.core import MemoryRecord
from memanto.app.services.memory_parsing_service import MemoryParsingService
from memanto.app.services.okf_export_service import OkfExportService
from memanto.cli.migrate.mappers import map_okf
from memanto.cli.migrate.okf_loader import load_okf_bundle


def round_trip(source: Path, target: Path) -> dict[str, Any]:
    """Map OKF memories through Memanto and export to a new bundle.

    Only the importable ``memories/`` section participates. Export-only context
    such as ``daily-summaries/`` and ``sessions/`` is intentionally not copied.
    """
    resolved_source = source.resolve()
    resolved_target = target.resolve()
    if resolved_target == resolved_source:
        raise ValueError("Target must differ from the source bundle")
    if resolved_target.is_relative_to(
        resolved_source
    ) or resolved_source.is_relative_to(resolved_target):
        raise ValueError("Source and target bundles must not overlap")
    if resolved_target.exists():
        raise FileExistsError(f"Target bundle already exists: {resolved_target}")

    source_export = load_okf_bundle(resolved_source)
    rows = map_okf(source_export)
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        memory_type = row.get("type")
        if memory_type is None:
            record = MemoryRecord(
                agent_id="portability-audit-demo",
                actor_id="migration",
                title=row["title"],
                content=row["content"],
                type=None,
                tags=row.get("tags") or [],
                confidence=row.get("confidence", 0.8),
                source=row.get("source") or "okf",
                source_ref=row.get("source_ref"),
                provenance=row.get("provenance") or "imported",
            )
            memory_type = MemoryParsingService().parse_memory(record).type
        assert memory_type is not None
        by_type[memory_type].append(row)

    service = OkfExportService(exports_dir=target.parent)
    return service.write_okf_bundle(
        agent_id="portability-audit-demo",
        memories_by_type=dict(by_type),
        output_dir=resolved_target,
        split="file",
    )


def main() -> int:
    """Run the local round-trip demonstration."""
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
