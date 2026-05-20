#!/usr/bin/env python3
"""Run a two-session skill-memory demo."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from skill_memory import after_skill, backend_from_args, before_skill


TRANSCRIPT_ONE = """
Decision: Prefer server-side validation helpers over duplicating schema checks in React components.
Preference: Keep PRs small enough that each skill handoff has one obvious owner.
Artifact: docs/architecture/forms.md records the validation boundary.
"""

EXPECTED_RECALLED_RULE = (
    "Prefer server-side validation helpers over duplicating schema checks in React components."
)


@dataclass(frozen=True)
class DemoResult:
    stored_memories: int
    recalled_expected_rule: bool
    baseline_repeated_instructions: int
    memanto_repeated_instructions: int

    @property
    def avoided_repeated_instructions(self) -> int:
        return self.baseline_repeated_instructions - self.memanto_repeated_instructions

    @property
    def reduction_percent(self) -> int:
        if self.baseline_repeated_instructions == 0:
            return 0
        return round(
            (self.avoided_repeated_instructions / self.baseline_repeated_instructions) * 100
        )


def write_benchmark_report(result: DemoResult, path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Claude Code Skills + Memanto Benchmark",
                "",
                "This credential-free benchmark compares a two-skill workflow with and",
                "without Memanto memory injection.",
                "",
                "| Metric | Value |",
                "| --- | ---: |",
                f"| Memories stored after `/grill-with-docs` | {result.stored_memories} |",
                f"| Expected architecture rule recalled before `/tdd` | {str(result.recalled_expected_rule)} |",
                f"| Baseline repeated instructions needed | {result.baseline_repeated_instructions} |",
                f"| Memanto repeated instructions needed | {result.memanto_repeated_instructions} |",
                f"| Repeated instructions avoided | {result.avoided_repeated_instructions} |",
                f"| Repeated-instruction reduction | {result.reduction_percent}% |",
                "",
                "The benchmark is intentionally tiny and deterministic: `/grill-with-docs`",
                "records one architectural validation rule, then `/tdd` recalls that rule",
                "without the user restating it in the second prompt.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["local", "memanto"], default="local")
    parser.add_argument("--store", default=".memanto-local/skill-memory.jsonl")
    parser.add_argument("--agent-id", default="claudecode-skills-demo")
    parser.add_argument("--benchmark-out", default="benchmark_report.md")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    store = Path(args.store)
    if args.reset and store.exists():
        store.unlink()

    backend = backend_from_args(args)

    print("== Session 1: /grill-with-docs ==")
    print(
        before_skill(
            backend,
            "/grill-with-docs",
            "Review the form architecture docs",
            ["docs/architecture/forms.md"],
        )
    )
    stored = after_skill(
        backend,
        "/grill-with-docs",
        "Review the form architecture docs",
        TRANSCRIPT_ONE,
        ["docs/architecture/forms.md"],
    )
    print(f"Stored {len(stored)} memories")

    print("\n== Session 2: /tdd ==")
    injected = before_skill(
        backend,
        "/tdd",
        "Write tests for the form validation path",
        ["app/forms/signup.py", "tests/test_signup_forms.py"],
    )
    print(injected)

    recalled_expected_rule = "server-side validation helpers" in injected
    result = DemoResult(
        stored_memories=len(stored),
        recalled_expected_rule=recalled_expected_rule,
        baseline_repeated_instructions=1,
        memanto_repeated_instructions=0 if recalled_expected_rule else 1,
    )
    write_benchmark_report(result, Path(args.benchmark_out))
    print(
        "\nBenchmark: "
        f"{result.avoided_repeated_instructions}/"
        f"{result.baseline_repeated_instructions} repeated instructions avoided "
        f"({result.reduction_percent}% reduction)"
    )

    if not recalled_expected_rule:
        raise SystemExit("demo failed: expected validation decision was not recalled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
