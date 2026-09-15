"""Run the offline, no-cost LlamaIndex -> OKF showcase end to end."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from generate_source import build_store
from migrate_to_okf import convert
from validate_round_trip import validate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    run_dir = args.output_root / stamp
    database = run_dir / "source" / "llamaindex-memory.sqlite"
    bundle = run_dir / "okf-bundle"
    report_path = run_dir / "fidelity-report.json"

    source_count = build_store(database)
    manifest = convert(database, bundle)
    report = validate(database, bundle, Path(__file__).with_name("golden_qa.json"))
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary = {
        "run_dir": str(run_dir.resolve()),
        "source_records": source_count,
        "mapped_memories": manifest["mapped_memories"],
        "type_counts": manifest["type_counts"],
        "record_recall": report["record_recall"],
        "golden_recall": report["golden_recall"],
        "passed": report["passed"],
        "next_command": f"memanto migrate okf {bundle.resolve()} --dry-run",
    }
    print(json.dumps(summary, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
