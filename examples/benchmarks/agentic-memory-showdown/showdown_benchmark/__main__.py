"""CLI entry point: python -m showdown_benchmark"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .backends.memanto import MemantoBackend
from .backends.mem0 import Mem0Backend
from .backends.offline import ActiveMemoryBackend, AppendLogBackend, SnapshotBackend
from .runner import run_benchmark
from .report import generate_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Agentic Memory Showdown — benchmark Memanto vs alternatives."
    )
    parser.add_argument(
        "--n-runs", type=int, default=3, metavar="N",
        help="Number of independent runs per (backend, scenario) pair. Default: 3",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results"),
        help="Directory to write results.md and results.json. Default: results/",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="Force offline mode (skip live API backends even if keys are set).",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-run progress output.",
    )
    args = parser.parse_args(argv)

    if args.offline:
        # Override env vars
        import os
        os.environ.pop("MOORCHEH_API_KEY", None)
        os.environ.pop("MEM0_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("OPENROUTER_API_KEY", None)

    backends = [
        MemantoBackend(),
        Mem0Backend(),
        ActiveMemoryBackend(),
        AppendLogBackend(),
        SnapshotBackend(),
    ]

    live = [b.name for b in backends if getattr(b, "is_live", False)]
    fallback = [b.name for b in backends if not getattr(b, "is_live", True)]

    if not args.quiet:
        print("\n🔬 Agentic Memory Showdown")
        print(f"  Runs per (backend × scenario): {args.n_runs}")
        print(f"  Output directory: {args.output_dir}")
        if live:
            print(f"  Live backends: {', '.join(live)}")
        print(f"  Offline/fallback backends: {', '.join(fallback)}")

    summaries = run_benchmark(
        backends=backends,
        n_runs=args.n_runs,
        verbose=not args.quiet,
    )

    report = generate_report(summaries, output_dir=args.output_dir)
    print("\n" + "="*60)
    print(report)
    print(f"\n✅ Results written to {args.output_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
