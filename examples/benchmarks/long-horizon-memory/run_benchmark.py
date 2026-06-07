#!/usr/bin/env python3
"""CLI entry point for the long-horizon memory benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv
from long_horizon.runner import BenchmarkConfig, run_benchmark


def _csv_ints(value: str) -> tuple[int, ...]:
    """Parse a comma-separated CLI integer list."""

    try:
        return tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc


def parse_args() -> argparse.Namespace:
    """Parse benchmark CLI options."""

    parser = argparse.ArgumentParser(
        description=(
            "Compare live Memanto and Mem0 retrieval over a deterministic "
            "long-horizon state-change workload."
        )
    )
    parser.add_argument(
        "--backends",
        nargs="+",
        choices=("memanto", "mem0"),
        default=("memanto", "mem0"),
    )
    parser.add_argument("--seeds", type=_csv_ints, default=(7, 19, 43))
    parser.add_argument("--sessions", type=int, default=48)
    parser.add_argument(
        "--checkpoints",
        type=_csv_ints,
        default=(8, 16, 24, 32, 48),
    )
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--keep-backend-state",
        action="store_true",
        help="Keep temporary Memanto agents, namespaces, and local backend state.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the configured benchmark and print its generated report."""

    load_dotenv()
    args = parse_args()
    config = BenchmarkConfig(
        backends=tuple(args.backends),
        seeds=args.seeds,
        sessions=args.sessions,
        checkpoints=args.checkpoints,
        top_k=args.top_k,
        output_dir=args.output_dir,
        cleanup=not args.keep_backend_state,
    )
    output = run_benchmark(config)
    print(f"Benchmark artifacts: {output.resolve()}")
    print((output / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
