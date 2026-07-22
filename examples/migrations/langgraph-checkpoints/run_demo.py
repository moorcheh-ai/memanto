"""Run the full offline LangGraph checkpoint to OKF migration showcase."""

from __future__ import annotations

import json
from pathlib import Path

from generate_source import generate_database
from langgraph_to_okf import convert_checkpoint_database
from validate_bundle import validate_recall

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
SOURCE = ARTIFACTS / "langgraph-checkpoints.sqlite"
BUNDLE = ARTIFACTS / "langgraph-okf"
GOLDEN = ROOT / "golden_qa.json"


def main() -> None:
    print("1/3 Running LangGraph and writing real SQLite checkpoints")
    generate_database(SOURCE)

    print("2/3 Converting the latest state of every thread to OKF")
    summary = convert_checkpoint_database(SOURCE, BUNDLE, overwrite=True)
    print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))

    print("3/3 Checking golden-question recall parity")
    report = validate_recall(BUNDLE, GOLDEN)
    report_path = ARTIFACTS / "recall-report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["recall_parity"] != 1.0:
        raise SystemExit(1)
    print(f"OKF bundle: {BUNDLE}")


if __name__ == "__main__":
    main()
