from __future__ import annotations

import argparse
from pathlib import Path

from incident_memory_pressure.runner import run_benchmark


def main() -> None:
    """Parse CLI arguments and print or write benchmark results."""

    parser = argparse.ArgumentParser(description="Run the incident memory benchmark")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format",
    )
    parser.add_argument(
        "--write-results",
        action="store_true",
        help="Write sample results into the benchmark results directory",
    )
    args = parser.parse_args()

    report = run_benchmark()
    if args.write_results:
        results_dir = Path(__file__).parent / "results"
        results_dir.mkdir(exist_ok=True)
        (results_dir / "sample_results.json").write_text(report.to_json(), encoding="utf-8")
        (results_dir / "sample_results.md").write_text(
            report.to_markdown(), encoding="utf-8"
        )

    if args.format == "json":
        print(report.to_json())
    else:
        print(report.to_markdown())


if __name__ == "__main__":
    main()
