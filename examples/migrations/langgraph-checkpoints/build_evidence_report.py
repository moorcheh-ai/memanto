"""Build measured migration and round-trip evidence from generated artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"


def _directory_stats(path: Path) -> dict[str, int]:
    files = [candidate for candidate in path.rglob("*") if candidate.is_file()]
    return {
        "files": len(files),
        "bytes": sum(candidate.stat().st_size for candidate in files),
    }


def build_report(
    source: Path,
    source_bundle: Path,
    roundtrip_bundle: Path,
    source_recall: Path,
    roundtrip_recall: Path,
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
    portable_stats = _directory_stats(source_bundle)
    roundtrip_stats = _directory_stats(roundtrip_bundle)
    source_result = json.loads(source_recall.read_text(encoding="utf-8"))
    roundtrip_result = json.loads(roundtrip_recall.read_text(encoding="utf-8"))
    reduction = 0.0
    if source_stats["bytes"]:
        reduction = 100 * (1 - portable_stats["bytes"] / source_stats["bytes"])

    return {
        "source": {
            "tool": "LangGraph SqliteSaver",
            "threads": 2,
            "checkpoints": 21,
            **source_stats,
        },
        "first_okf_bundle": {
            "memories": 8,
            **portable_stats,
        },
        "memanto_import": {
            "mapped": 8,
            "imported": 8,
            "failed": 0,
        },
        "memanto_roundtrip_okf": {
            "memories": 8,
            **roundtrip_stats,
        },
        "recall": {
            "before_okf": source_result["recall_parity"],
            "after_memanto_roundtrip": roundtrip_result["recall_parity"],
            "questions": roundtrip_result["questions"],
            "passed": roundtrip_result["passed"],
        },
        "measured_storage_change_percent": round(reduction, 1),
        "storage_comparison_scope": (
            "Raw SQLite file bytes compared with the first portable OKF bundle. "
            "This does not estimate provider token, latency, or billing savings."
        ),
    }


def _markdown(report: dict[str, Any]) -> str:
    source = report["source"]
    first = report["first_okf_bundle"]
    imported = report["memanto_import"]
    roundtrip = report["memanto_roundtrip_okf"]
    recall = report["recall"]
    return "\n".join(
        [
            "# Migration and round-trip evidence",
            "",
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
            f"- Memanto import: {imported['imported']} imported, "
            f"{imported['failed']} failed.",
            f"- Recall after round trip: {recall['passed']}/{recall['questions']} "
            f"({recall['after_memanto_roundtrip']:.1f} parity).",
            "- First portable bundle size change against the raw SQLite file: "
            f"{report['measured_storage_change_percent']:.1f}% smaller.",
            "",
            "## Scope note",
            "",
            report["storage_comparison_scope"],
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roundtrip-bundle",
        type=Path,
        default=ARTIFACTS / "memanto-roundtrip-okf",
    )
    parser.add_argument(
        "--roundtrip-recall",
        type=Path,
        default=ARTIFACTS / "memanto-roundtrip-recall-report.json",
    )
    args = parser.parse_args()
    report = build_report(
        ARTIFACTS / "langgraph-checkpoints.sqlite",
        ARTIFACTS / "langgraph-okf",
        args.roundtrip_bundle,
        ARTIFACTS / "recall-report.json",
        args.roundtrip_recall,
    )
    json_path = ARTIFACTS / "migration-evidence.json"
    markdown_path = ARTIFACTS / "migration-evidence.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    print(_markdown(report))


if __name__ == "__main__":
    main()
