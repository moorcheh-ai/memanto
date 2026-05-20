#!/usr/bin/env python3
"""Credential-free productivity benchmark for the Memanto skills example."""

from __future__ import annotations

import argparse
import tempfile
from dataclasses import dataclass
from pathlib import Path

from memanto_skills_hook import LocalJsonlBackend, SkillRun, build_context_block, store_completed_run


@dataclass(frozen=True)
class BenchmarkStep:
    skill: str
    task: str
    files: tuple[str, ...]
    transcript: str
    repeated_instruction: str


STEPS: tuple[BenchmarkStep, ...] = (
    BenchmarkStep(
        skill="grill-with-docs",
        task="Review auth session design",
        files=("src/auth/session.ts",),
        transcript=(
            "Decision: keep refresh tokens server-side only. "
            "Preference: test session expiry at the service boundary. "
            "Never: log raw tokens in debug output."
        ),
        repeated_instruction="refresh tokens server-side only",
    ),
    BenchmarkStep(
        skill="tdd",
        task="Add auth session expiry tests",
        files=("src/auth/session.ts", "tests/auth/session.test.ts"),
        transcript=(
            "Decision: cover both valid and expired sessions at the service boundary. "
            "Must: keep token fixtures deterministic."
        ),
        repeated_instruction="test session expiry at the service boundary",
    ),
    BenchmarkStep(
        skill="handoff",
        task="Summarize auth session token logging implementation",
        files=("src/auth/session.ts",),
        transcript="Decision: document the server-side refresh token boundary in handoff notes.",
        repeated_instruction="raw tokens",
    ),
)


def run_benchmark(store: Path) -> dict[str, float | int]:
    """Run a deterministic cross-skill memory benchmark."""
    backend = LocalJsonlBackend(store)
    baseline_repeated_prompts = 0
    memanto_reused_prompts = 0
    stored_memories = 0

    for index, step in enumerate(STEPS):
        run = SkillRun(skill=step.skill, task=step.task, files=step.files)
        context = build_context_block(run, backend)
        if index > 0:
            baseline_repeated_prompts += 1
            if step.repeated_instruction.lower() in context.lower():
                memanto_reused_prompts += 1

        completed = SkillRun(
            skill=step.skill,
            task=step.task,
            files=step.files,
            transcript=step.transcript,
        )
        stored_memories += store_completed_run(completed, backend)

    reduction = (
        memanto_reused_prompts / baseline_repeated_prompts
        if baseline_repeated_prompts
        else 0.0
    )
    return {
        "skill_runs": len(STEPS),
        "stored_memories": stored_memories,
        "baseline_repeated_prompts": baseline_repeated_prompts,
        "memanto_reused_prompts": memanto_reused_prompts,
        "repeated_instruction_reduction": reduction,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure cross-skill repeated-instruction reduction."
    )
    parser.add_argument("--store", type=Path)
    args = parser.parse_args(argv)

    if args.store:
        result = run_benchmark(args.store)
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_benchmark(Path(tmpdir) / "benchmark-memory.jsonl")

    for key, value in result.items():
        if isinstance(value, float):
            print(f"{key}={value:.0%}")
        else:
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
