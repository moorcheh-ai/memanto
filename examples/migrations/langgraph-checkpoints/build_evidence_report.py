"""Build measured migration and round-trip evidence from generated artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"

_IMPORT_LINE = re.compile(
    r"Imported:\s*(?P<imported>\d+)\s+Failed:\s*(?P<failed>\d+)",
    re.IGNORECASE,
)
_MAPPED_LINE = re.compile(
    r"Mapped memories:\s*(?P<mapped>\d+)\s+\(skipped\s+(?P<skipped>\d+)\)",
    re.IGNORECASE,
)
_OKF_NODES_LINE = re.compile(r"OKF nodes:\s*(?P<nodes>\d+)", re.IGNORECASE)


def _directory_stats(path: Path) -> dict[str, int]:
    files = [candidate for candidate in path.rglob("*") if candidate.is_file()]
    return {
        "files": len(files),
        "bytes": sum(candidate.stat().st_size for candidate in files),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(candidate.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(candidate)))
    return digest.hexdigest()


def _source_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True) as conn:
        checkpoints = int(conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0])
        threads = int(
            conn.execute("SELECT COUNT(DISTINCT thread_id) FROM checkpoints").fetchone()[0]
        )
    return {"threads": threads, "checkpoints": checkpoints}


def _bundle_summary(path: Path) -> dict[str, Any]:
    summary_path = path / "migration-summary.json"
    if summary_path.is_file():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    memory_files = [
        candidate
        for candidate in (path / "memories").rglob("*.md")
        if candidate.name != "index.md"
    ]
    by_type: dict[str, int] = {}
    for candidate in memory_files:
        memory_type = candidate.parent.name
        by_type[memory_type] = by_type.get(memory_type, 0) + 1
    return {"memories": len(memory_files), "memories_by_type": by_type}


def parse_import_counts(lines: list[str] | str) -> dict[str, int] | None:
    """Parse measured Memanto import counts from CLI output.

    Expects a line like ``Imported: 8  Failed: 0``. Optionally also captures
    ``Mapped memories`` / ``OKF nodes``. Returns ``None`` when the import line
    is absent so callers never invent ``memanto_import``.
    """
    text = "\n".join(lines) if isinstance(lines, list) else lines
    imported_match = _IMPORT_LINE.search(text)
    if imported_match is None:
        return None
    counts = {
        "imported": int(imported_match.group("imported")),
        "failed": int(imported_match.group("failed")),
    }
    mapped_match = _MAPPED_LINE.search(text)
    if mapped_match is not None:
        counts["mapped"] = int(mapped_match.group("mapped"))
        counts["skipped"] = int(mapped_match.group("skipped"))
    nodes_match = _OKF_NODES_LINE.search(text)
    if nodes_match is not None:
        counts["okf_nodes"] = int(nodes_match.group("nodes"))
    return counts


def merge_import_counts(
    report: dict[str, Any], import_counts: dict[str, int]
) -> dict[str, Any]:
    """Attach measured import counts without inventing missing fields."""
    merged = dict(report)
    merged["memanto_import"] = dict(import_counts)
    return merged


def build_report(
    source: Path,
    source_bundle: Path,
    roundtrip_bundle: Path,
    source_recall: Path,
    roundtrip_recall: Path,
    *,
    run_id: str | None = None,
    import_output: list[str] | str | None = None,
) -> dict[str, Any]:
    required = [
        source,
        source_bundle,
        roundtrip_bundle,
        source_recall,
        roundtrip_recall,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing evidence artifact: " + ", ".join(missing))

    source_stats = {"files": 1, "bytes": source.stat().st_size}
    source_counts = _source_counts(source)
    portable_stats = _directory_stats(source_bundle)
    roundtrip_stats = _directory_stats(roundtrip_bundle)
    portable_summary = _bundle_summary(source_bundle)
    roundtrip_summary = _bundle_summary(roundtrip_bundle)
    source_result = json.loads(source_recall.read_text(encoding="utf-8"))
    roundtrip_result = json.loads(roundtrip_recall.read_text(encoding="utf-8"))
    source_score = source_result.get(
        "score",
        source_result.get("recall_parity", source_result.get("content_coverage")),
    )
    roundtrip_score = roundtrip_result.get(
        "score", roundtrip_result.get("recall_parity")
    )
    if source_score is None or roundtrip_score is None:
        raise ValueError("Recall reports must contain score or recall_parity")
    reduction = 0.0
    if source_stats["bytes"]:
        reduction = 100 * (1 - portable_stats["bytes"] / source_stats["bytes"])

    report: dict[str, Any] = {
        "source": {
            "tool": "LangGraph SqliteSaver",
            **source_counts,
            **source_stats,
            "sha256": _sha256(source),
        },
        "first_okf_bundle": {
            "memories": int(portable_summary.get("memories", 0)),
            "memories_by_type": portable_summary.get("memories_by_type", {}),
            **portable_stats,
            "sha256": _tree_hash(source_bundle),
        },
        "memanto_roundtrip_okf": {
            "memories": int(roundtrip_summary.get("memories", 0)),
            "memories_by_type": roundtrip_summary.get("memories_by_type", {}),
            **roundtrip_stats,
            "sha256": _tree_hash(roundtrip_bundle),
        },
        "recall": {
            "before_okf": source_score,
            "after_memanto_roundtrip": roundtrip_score,
            "questions": roundtrip_result["questions"],
            "passed": roundtrip_result["passed"],
        },
        "measured_storage_change_percent": round(reduction, 1),
        "storage_comparison_scope": (
            "Raw SQLite file bytes compared with the first portable OKF bundle. "
            "This does not estimate provider token, latency, or billing savings."
        ),
    }
    if run_id:
        report["run_id"] = run_id
    if import_output is not None:
        import_counts = parse_import_counts(import_output)
        if import_counts is not None:
            report = merge_import_counts(report, import_counts)
    return report


def _markdown(report: dict[str, Any]) -> str:
    source = report["source"]
    first = report["first_okf_bundle"]
    roundtrip = report["memanto_roundtrip_okf"]
    recall = report["recall"]
    lines = [
        "# Migration and round-trip evidence",
        "",
    ]
    if report.get("run_id"):
        lines.extend([f"Run ID: `{report['run_id']}`", ""])
    lines.extend(
        [
            "| Stage | Records | Files | Bytes |",
            "| --- | ---: | ---: | ---: |",
            (
                f"| LangGraph SQLite | {source['checkpoints']} checkpoints | "
                f"{source['files']} | {source['bytes']} |"
            ),
            (
                f"| First OKF bundle | {first['memories']} memories | "
                f"{first['files']} | {first['bytes']} |"
            ),
            (
                f"| Memanto round-trip OKF | {roundtrip['memories']} memories | "
                f"{roundtrip['files']} | {roundtrip['bytes']} |"
            ),
            "",
            "- First OKF type breakdown: "
            + ", ".join(
                f"{key}={value}"
                for key, value in sorted(first["memories_by_type"].items())
            )
            + ".",
            f"- Round-trip recovery: {roundtrip['memories']}/{first['memories']} "
            "portable memories exported from Memanto.",
            f"- Recall after round trip: {recall['passed']}/{recall['questions']} "
            f"({recall['after_memanto_roundtrip']:.1f} parity).",
        ]
    )
    import_counts = report.get("memanto_import")
    if isinstance(import_counts, dict) and "imported" in import_counts:
        failed = import_counts.get("failed", 0)
        lines.append(
            f"- Memanto import: {import_counts['imported']} imported, "
            f"{failed} failed."
        )
    lines.extend(
        [
            "- First portable bundle size change against the raw SQLite file: "
            f"{report['measured_storage_change_percent']:.1f}% smaller.",
            "",
            "## Scope note",
            "",
            report["storage_comparison_scope"],
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "migration-evidence.json"
    markdown_path = output_dir / "migration-evidence.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ARTIFACTS / "langgraph-checkpoints.sqlite"
    )
    parser.add_argument(
        "--source-bundle", type=Path, default=ARTIFACTS / "langgraph-okf"
    )
    parser.add_argument(
        "--roundtrip-bundle",
        type=Path,
        default=ARTIFACTS / "memanto-roundtrip-okf",
    )
    parser.add_argument("--run-id")
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS)
    parser.add_argument(
        "--source-recall",
        type=Path,
        default=ARTIFACTS / "content-coverage-report.json",
    )
    parser.add_argument(
        "--roundtrip-recall",
        type=Path,
        default=ARTIFACTS / "memanto-roundtrip-recall-report.json",
    )
    parser.add_argument(
        "--import-output",
        type=Path,
        help="Optional text file of memanto migrate CLI output used to measure imports",
    )
    args = parser.parse_args()
    import_output = None
    if args.import_output is not None:
        import_output = args.import_output.read_text(encoding="utf-8")
    report = build_report(
        args.source,
        args.source_bundle,
        args.roundtrip_bundle,
        args.source_recall,
        args.roundtrip_recall,
        run_id=args.run_id,
        import_output=import_output,
    )
    write_report(report, args.output_dir)
    print(_markdown(report))


if __name__ == "__main__":
    main()
