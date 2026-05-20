from __future__ import annotations

import argparse
from pathlib import Path

from skill_memory import (
    LocalJsonlBackend,
    build_backend,
    post_skill,
    pre_skill,
    repeated_instruction_reduction,
)


SESSION_ONE = """Task: Review auth-refresh architecture.
Decision: Keep refresh token rotation in AuthGateway, not React components.
Preference: Use typed Result objects for recoverable API errors.
Instruction: Never leak refresh tokens into browser-visible logs.
Artifact: AuthGateway owns refresh-token exchange and retry policy.
"""

SESSION_TWO_TASK = (
    "Write TDD coverage for refresh-token retry behavior in AuthGateway "
    "without repeating the earlier architectural rules."
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["local", "sdk"], default="local")
    parser.add_argument("--store", type=Path, default=Path(".demo-memory.jsonl"))
    parser.add_argument("--agent-id", default="claude-skills-demo")
    args = parser.parse_args()

    if args.backend == "local" and args.store.exists():
        args.store.unlink()

    backend = build_backend(args.backend, args.store, args.agent_id)
    stored = post_skill(backend, "grill-with-docs", SESSION_ONE)
    injected = pre_skill(backend, "tdd", SESSION_TWO_TASK)
    score = repeated_instruction_reduction(SESSION_ONE, SESSION_TWO_TASK, injected)

    print(f"stored_memories={stored}")
    print(injected)
    print(f"benchmark={score}")
    print("demo complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

