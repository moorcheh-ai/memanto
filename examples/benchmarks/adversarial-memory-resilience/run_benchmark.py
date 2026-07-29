#!/usr/bin/env python3
"""CLI for the adversarial incident-memory benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from adversarial_memory.runner import BenchmarkConfig, run_benchmark
from dotenv import load_dotenv


def _seeds(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare live Memanto and Mem0 under evolving adversarial incidents."
    )
    parser.add_argument("--backends", nargs="+", default=("memanto", "mem0"))
    parser.add_argument("--seeds", type=_seeds, default=(7, 19, 43))
    parser.add_argument("--tenants", type=int, default=3)
    parser.add_argument("--incidents", type=int, default=4)
    parser.add_argument("--revisions", type=int, default=4)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--keep-backend-state", action="store_true")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    output = run_benchmark(
        BenchmarkConfig(
            backends=tuple(args.backends),
            seeds=args.seeds,
            tenants=args.tenants,
            incidents=args.incidents,
            revisions=args.revisions,
            top_k=args.top_k,
            output_dir=args.output_dir,
            cleanup=not args.keep_backend_state,
        )
    )
    print(f"Benchmark artifacts: {output.resolve()}")


if __name__ == "__main__":
    main()
