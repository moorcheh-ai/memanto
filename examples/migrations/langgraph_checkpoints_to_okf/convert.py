"""Convert exported LangGraph checkpoints into an importable OKF bundle."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memanto.app.services.okf_export_service import OkfExportService

MEMANTO_TYPES = {
    "fact",
    "preference",
    "goal",
    "commitment",
    "relationship",
    "event",
    "decision",
    "observation",
    "artifact",
    "learning",
    "instruction",
    "error",
    "context",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(base_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_records(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "memory"


def extract_latest_memories(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return latest memory value per source id, preserving checkpoint lineage."""
    latest: dict[str, dict[str, Any]] = {}
    order: dict[str, int] = {}

    for index, record in enumerate(records):
        values = record.get("channel_values") or {}
        memories = values.get("memories") or []
        if not isinstance(memories, list):
            continue
        for memory in memories:
            if not isinstance(memory, dict):
                continue
            content = str(memory.get("content") or "").strip()
            if not content:
                continue
            source_id = str(memory.get("id") or _slug(content)[:48])
            latest[source_id] = {
                **memory,
                "id": source_id,
                "source_checkpoint_id": record.get("checkpoint_id"),
                "source_parent_checkpoint_id": record.get("parent_checkpoint_id"),
                "source_thread_id": record.get("thread_id"),
                "source_checkpoint_ts": record.get("timestamp"),
                "source_step": (record.get("metadata") or {}).get("step"),
            }
            order.setdefault(source_id, index)

    return [latest[key] for key, _ in sorted(order.items(), key=lambda item: item[1])]


def to_memanto_rows(memories: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for source in memories:
        source_type = str(source.get("type") or "observation").strip().lower()
        mem_type = source_type if source_type in MEMANTO_TYPES else "observation"
        source_ref = (
            "langgraph://"
            f"{source.get('source_thread_id')}/"
            f"{source.get('source_checkpoint_id')}/"
            f"{source.get('id')}"
        )
        content = str(source.get("content") or "").strip()
        evidence = str(source.get("evidence") or "").strip()
        footer = [
            "",
            "---",
            "[LangGraph checkpoint provenance]",
            f"- Source type: {source_type}",
            f"- Thread: {source.get('source_thread_id')}",
            f"- Checkpoint: {source.get('source_checkpoint_id')}",
            f"- Parent checkpoint: {source.get('source_parent_checkpoint_id')}",
            f"- Checkpoint timestamp: {source.get('source_checkpoint_ts')}",
            f"- LangGraph step: {source.get('source_step')}",
        ]
        if evidence:
            footer.append(f"- Evidence turn: {evidence}")

        by_type[mem_type].append(
            {
                "id": source["id"],
                "title": source["id"].replace("-", " ").title(),
                "content": content + "\n".join(footer),
                "tags": list(source.get("tags") or []) + ["source=langgraph"],
                "confidence": float(source.get("confidence") or 0.8),
                "provenance": "imported",
                "source": "langgraph-checkpoint",
                "status": "active",
                "created_at": source.get("updated_at") or source.get("source_checkpoint_ts"),
                "source_ref": source_ref,
            }
        )

    return dict(by_type)


def write_reports(
    *,
    base_dir: Path,
    source_path: Path,
    records: list[dict[str, Any]],
    memories: list[dict[str, Any]],
    okf_result: dict[str, Any],
) -> None:
    reports = base_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    per_type = okf_result.get("per_type_counts", {})
    mapped = sum(per_type.values())
    source_memory_versions = sum(
        len((record.get("channel_values") or {}).get("memories") or [])
        for record in records
    )
    original_chars = sum(len(json.dumps(record, ensure_ascii=False)) for record in records)
    okf_path = Path(okf_result["output_path"])
    okf_chars = sum(
        len(path.read_text(encoding="utf-8"))
        for path in okf_path.rglob("*.md")
    )

    mapping_lines = [
        "# Mapping table",
        "",
        "| LangGraph source | OKF / Memanto target | Fidelity note |",
        "| --- | --- | --- |",
        "| `memories[].id` | OKF `title`, `x_memanto.id` | Stable source identity is preserved. |",
        "| `memories[].type` | OKF `type`, `x_memanto.type` | Unknown types fall back to `observation`. |",
        "| `memories[].content` | Markdown body | Human-readable portable memory text. |",
        "| `memories[].confidence` | `x_memanto.confidence` | Numeric confidence round-trips. |",
        "| `memories[].tags` | OKF `tags` | Source tags stay filterable. |",
        "| checkpoint ids | OKF `resource` plus provenance footer | Lineage stays auditable. |",
        "| evidence turn | provenance footer | Recall claims point back to source data. |",
        "",
    ]
    (reports / "mapping-table.md").write_text("\n".join(mapping_lines), encoding="utf-8")

    summary = [
        "# Migration summary",
        "",
        f"- Generated at: {_now()}",
        f"- Source file: `{_rel(base_dir, source_path)}`",
        f"- LangGraph checkpoint records: {len(records)}",
        f"- Memory versions observed across checkpoints: {source_memory_versions}",
        f"- Latest deduped memories exported: {len(memories)}",
        f"- OKF mapped memories: {mapped}",
        f"- Per-type breakdown: `{json.dumps(per_type, sort_keys=True)}`",
        f"- OKF output: `{_rel(base_dir, okf_path)}`",
        "",
        "## Savings report",
        "",
        (
            "This local demo intentionally avoids paid APIs. The storage comparison "
            "below measures source checkpoint JSONL versus readable OKF markdown."
        ),
        "",
        f"- Source checkpoint JSONL bytes: {original_chars}",
        f"- OKF markdown bytes: {okf_chars}",
        f"- Compression ratio (OKF/source): {okf_chars / max(original_chars, 1):.2f}",
        "",
        "## Fidelity summary",
        "",
        "Every exported OKF file keeps the source thread, checkpoint id, parent "
        "checkpoint id, step, confidence, tags, and the original evidence turn.",
        "",
    ]
    (reports / "migration-summary.md").write_text("\n".join(summary), encoding="utf-8")


def convert(base_dir: Path) -> dict[str, Any]:
    source_path = base_dir / "data" / "source" / "langgraph_checkpoints.jsonl"
    records = load_records(source_path)
    memories = extract_latest_memories(records)
    rows_by_type = to_memanto_rows(memories)

    output_dir = base_dir / "okf_bundle"
    result = OkfExportService(exports_dir=base_dir).write_okf_bundle(
        "langgraph_checkpoint_escape",
        rows_by_type,
        output_dir=output_dir,
        split="file",
    )
    write_reports(
        base_dir=base_dir,
        source_path=source_path,
        records=records,
        memories=memories,
        okf_result=result,
    )
    manifest = {
        "converted_at": _now(),
        "source_path": _rel(base_dir, source_path),
        "checkpoint_records": len(records),
        "deduped_memories": len(memories),
        "okf_output": _rel(base_dir, Path(result["output_path"])),
        "per_type_counts": result["per_type_counts"],
    }
    out_path = base_dir / "reports" / "conversion-manifest.json"
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    manifest = convert(args.base_dir.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
