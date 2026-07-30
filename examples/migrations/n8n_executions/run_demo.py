"""One-command n8n execution-history to OKF demonstration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from examples.migrations.n8n_executions.adapter import convert_n8n_executions
from examples.migrations.n8n_executions.recall_validation import (
    validate_recall_parity,
    write_report,
)

HERE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and validate the sample n8n -> OKF migration."
    )
    parser.add_argument(
        "--input",
        default=str(HERE / "sample-executions.json"),
    )
    parser.add_argument(
        "--mapping",
        default=str(HERE / "mapping.yaml"),
    )
    parser.add_argument(
        "--questions",
        default=str(HERE / "golden-questions.yaml"),
    )
    parser.add_argument(
        "--output",
        default=str(HERE / "sample-okf"),
    )
    args = parser.parse_args()

    migration = convert_n8n_executions(args.input, args.mapping, args.output)
    parity = validate_recall_parity(
        args.input,
        args.mapping,
        args.output,
        args.questions,
    )
    report_path = Path(args.output) / "recall-parity-report.json"
    write_report(report_path, parity)

    result = {
        "migration": migration,
        "recall_parity": parity,
        "recall_report": str(report_path.resolve()),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if parity["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
