#!/usr/bin/env python3
"""Validate a real Memanto import with the same Hindsight golden set."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

try:
    from examples.migrations.hindsight.validation import (
        build_parity_report,
        evaluate_retriever,
        memanto_retriever,
        write_parity_report,
        write_report,
    )
except ModuleNotFoundError:
    from validation import (  # type: ignore[no-redef]
        build_parity_report,
        evaluate_retriever,
        memanto_retriever,
        write_parity_report,
        write_report,
    )

EXAMPLE_DIR = Path(__file__).resolve().parent
DEFAULT_ARTIFACTS = EXAMPLE_DIR / "artifacts" / "beacon-live-run"


def wait_for_indexed_memories(
    client: Any,
    agent_id: str,
    *,
    expected_count: int,
    timeout: float,
    poll_interval: float,
) -> int:
    """Wait for asynchronous cloud ingestion to expose every imported row."""
    deadline = time.monotonic() + timeout
    while True:
        result = client.recall_recent(agent_id=agent_id, limit=100)
        count = int(result.get("count") or len(result.get("memories", [])))
        if count >= expected_count:
            return count
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Memanto exposed {count}/{expected_count} imported memories "
                f"after {timeout:g} seconds"
            )
        print(
            f"[indexing] {count}/{expected_count} memories visible",
            flush=True,
        )
        time.sleep(poll_interval)


def build_parser() -> argparse.ArgumentParser:
    """Create the destination-validation argument parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the shared golden questions against a real Memanto agent and "
            "write source-to-destination recall parity evidence."
        )
    )
    parser.add_argument("--agent", required=True, help="Imported Memanto agent ID.")
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=DEFAULT_ARTIFACTS,
        help=f"Source artifact directory (default: {DEFAULT_ARTIFACTS}).",
    )
    parser.add_argument(
        "--evidence-output",
        type=Path,
        help="Destination for recall reports (defaults to <artifacts>/evidence).",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        help="Expected imported memory count (defaults to run-summary.json).",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=300,
        help="Maximum wait for asynchronous indexing (default: 300).",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=5,
        help="Indexing poll interval (default: 5).",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    """Run real destination recall and write reproducible evidence."""
    args = build_parser().parse_args(argv)
    artifacts = args.artifacts.expanduser().resolve()
    evidence_dir = (
        args.evidence_output.expanduser().resolve()
        if args.evidence_output
        else artifacts / "evidence"
    )
    try:
        summary = json.loads(
            (artifacts / "run-summary.json").read_text(encoding="utf-8")
        )
        source_report = json.loads(
            (evidence_dir / "source-recall.json").read_text(encoding="utf-8")
        )
        expected_count = (
            args.expected_count
            if args.expected_count is not None
            else int(summary["migration"]["importable_records"])
        )
        if expected_count < 1:
            raise ValueError("--expected-count must be positive")
        if args.wait_seconds < 0 or args.poll_seconds <= 0:
            raise ValueError("wait and poll durations must be non-negative")

        from memanto.cli.client.sdk_client import SdkClient
        from memanto.cli.config.manager import ConfigManager

        api_key = ConfigManager().get_api_key()
        if not api_key:
            raise RuntimeError("MOORCHEH_API_KEY is not configured in ~/.memanto/.env")
        client = SdkClient(api_key)
        client.activate_agent(args.agent)
        indexed_count = wait_for_indexed_memories(
            client,
            args.agent,
            expected_count=expected_count,
            timeout=args.wait_seconds,
            poll_interval=args.poll_seconds,
        )
        destination_report = evaluate_retriever(
            "memanto",
            memanto_retriever(client, args.agent),
        )
        write_report(
            destination_report,
            evidence_dir,
            prefix="memanto-recall",
            title="Memanto destination recall — golden validation set",
            note=(
                "Scores are deterministic phrase-group coverage over raw Memanto "
                "semantic recall results, not an LLM self-grade."
            ),
        )
        parity_report = build_parity_report(source_report, destination_report)
        parity_report["agent_id"] = args.agent
        parity_report["indexed_memories"] = indexed_count
        write_parity_report(parity_report, evidence_dir)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"Memanto recall: {destination_report['passed']}/"
        f"{destination_report['questions']} full passes; "
        f"mean score retention {parity_report['mean_score_retention']:.1%}.",
        flush=True,
    )
    return int(destination_report["passed"] != destination_report["questions"])


if __name__ == "__main__":
    raise SystemExit(run())
