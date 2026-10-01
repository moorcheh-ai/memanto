"""LangMem export -> OKF bundle.

Doesn't re-implement OKF serialization -- maps LangMem records onto Memanto
memory dicts (``mapping.map_record``) and hands them to the existing
``OkfExportService.write_okf_bundle``. Building on the shipped writer keeps
the bundle compatible with ``memanto migrate okf`` and keeps this file small.

Flow:

    langmem_export.json
        -> mapping.map_record (per record)         # LangMem -> Memanto dict
        -> group by inferred type                  # memories_by_type
        -> OkfExportService.write_okf_bundle(...)   # shipped serializer
        -> OKF bundle (index.md + memories/<type>/*.md)

The produced bundle is consumable as-is:

    memanto migrate okf ./okf-bundle --agent <id>
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from memanto.app.services.okf_export_service import OkfExportService

from .export import load_export
from .mapping import map_record, type_breakdown


def build_memories_by_type(export: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Map every LangMem record and group the results by inferred Memanto type."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in export.get("memories", []) or []:
        if not (record.get("value") or {}).get("content"):
            continue
        row = map_record(record)
        grouped.setdefault(row["type"], []).append(row)
    return grouped


def write_okf_bundle(
    export: dict[str, Any],
    output_dir: Path,
    agent_id: str = "langmem-import",
) -> dict[str, Any]:
    """Convert a LangMem export dict into an OKF bundle at ``output_dir``.

    Returns a summary dict: source/mapped counts, per-type breakdown, and the
    resolved bundle path.
    """
    output_dir = Path(output_dir)
    memories_by_type = build_memories_by_type(export)
    mapped = [row for rows in memories_by_type.values() for row in rows]

    # OkfExportService guards writes to within ``exports_dir.parent``. Point its
    # exports_dir at a work area whose parent contains our target, so the guard
    # is satisfied, then relocate the finished bundle to ``output_dir``.
    work_root = output_dir.parent / "_okf_work"
    exports_dir = work_root / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    service = OkfExportService(exports_dir=exports_dir)
    result = service.write_okf_bundle(
        agent_id=agent_id,
        memories_by_type=memories_by_type,
        output_dir=None,  # -> exports_dir/<agent_id>_okf
        split="file",  # one readable markdown file per memory
    )

    produced = Path(result["output_path"])
    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.move(str(produced), str(output_dir))
    shutil.rmtree(work_root, ignore_errors=True)

    return {
        "source_count": export.get("count", len(export.get("memories", []) or [])),
        "mapped_count": len(mapped),
        "type_counts": type_breakdown(mapped),
        "bundle_path": str(output_dir.resolve()),
        "sections": result.get("sections", []),
    }


def adapt_file(
    export_path: Path, output_dir: Path, agent_id: str = "langmem-import"
) -> dict[str, Any]:
    """Convenience: load a ``langmem_export.json`` and build the bundle."""
    return write_okf_bundle(load_export(Path(export_path)), Path(output_dir), agent_id)
