"""
CLI entry point for the benchmark.

Usage:
    python run_benchmark.py
    python run_benchmark.py --skip-judge        # only collect latency/token metrics
    python run_benchmark.py --judge-model anthropic/claude-3-haiku-20240307
    python run_benchmark.py --no-save           # disable saving results to results/
"""

from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv
from harness import run_benchmark
from reporter import print_report, save_results

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Memanto vs Mem0 — Executive Shadow Benchmark"
    )
    parser.add_argument(
        "--skip-judge",
        action="store_true",
        help="Skip LLM-as-judge scoring (only collect latency and token metrics)",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="LLM model for the judge (default: anthropic/claude-3-5-haiku via OpenRouter)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save results to results/ directory",
    )
    args = parser.parse_args()

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Memanto vs Mem0 — The Executive Shadow Benchmark")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    try:
        result = run_benchmark(
            skip_judge=args.skip_judge,
            judge_model=args.judge_model,
        )
    except Exception as exc:
        logging.error("Benchmark failed: %s", exc)
        sys.exit(1)

    print_report(result)

    if not args.no_save:
        path = save_results(result)
        print(f"\nResults saved → {path}\n")


if __name__ == "__main__":
    main()
