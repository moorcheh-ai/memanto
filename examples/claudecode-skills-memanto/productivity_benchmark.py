"""Credential-free productivity benchmark for the Memanto skill bridge.

The benchmark models three separate skill invocations:

1. /grill-with-docs captures durable architectural constraints.
2. /tdd starts later and receives the recalled constraints.
3. /handoff starts in another context and receives the same constraints.

Without a memory bridge, the user would need to repeat those constraints in
each later skill prompt. With the bridge, the constraints are recalled from the
local preview backend and injected automatically.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from skill_memory import (
    LocalJsonBackend,
    SkillRun,
    extract_memories,
    render_injected_context,
)

REPEATED_CONSTRAINTS = (
    "authentication middleware stateless",
    "tenant lookup into a small dependency",
    "avoid global mutable caches",
)


def run_benchmark(memory_file: Path | None = None) -> dict[str, object]:
    """Run the benchmark and return machine-readable metrics."""

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if memory_file is None:
        temp_dir = tempfile.TemporaryDirectory()
        memory_file = Path(temp_dir.name) / "memory.json"

    try:
        backend = LocalJsonBackend(memory_file)
        first_run = SkillRun(
            skill="/grill-with-docs",
            task="Review the auth refactor plan for a FastAPI service.",
            output=(
                "Decision: keep authentication middleware stateless and push "
                "tenant lookup into a small dependency. Must avoid global "
                "mutable caches because tests run with parallel workers. "
                "Preference: the auth module owns token parsing."
            ),
            cwd="services/api",
            files=["services/api/auth.py", "services/api/dependencies.py"],
        )
        for memory in extract_memories(first_run):
            backend.remember(memory)

        later_sessions = [
            (
                "/tdd",
                "Write auth dependency tests for services/api/auth.py",
                ["services/api/auth.py", "services/api/test_auth.py"],
            ),
            (
                "/handoff",
                "Prepare implementation handoff for the auth refactor",
                ["services/api/auth.py", "docs/auth-handoff.md"],
            ),
        ]
        injected_contexts = []
        for skill, task, files in later_sessions:
            query = " ".join([skill, task, "services/api", *files])
            injected_contexts.append(render_injected_context(backend.recall(query, 5)))

        baseline_repeated = len(REPEATED_CONSTRAINTS) * len(later_sessions)
        injected_text = "\n".join(injected_contexts).lower()
        recovered = sum(
            1
            for context in injected_contexts
            for constraint in REPEATED_CONSTRAINTS
            if constraint in context.lower()
        )
        reduction_pct = round((recovered / baseline_repeated) * 100, 2)
        return {
            "skill_sequence": [
                first_run.skill,
                *[session[0] for session in later_sessions],
            ],
            "baseline_repeated_instructions": baseline_repeated,
            "memanto_injected_constraints": recovered,
            "repeated_instruction_reduction_pct": reduction_pct,
            "recalled_context_contains": {
                constraint: constraint in injected_text
                for constraint in REPEATED_CONSTRAINTS
            },
        }
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def main() -> int:
    print(json.dumps(run_benchmark(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
