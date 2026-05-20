from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from run_demo import SESSION_ONE, SESSION_TWO_TASK
from skill_memory import LocalJsonlBackend, post_skill, pre_skill, repeated_instruction_reduction
from wrappers import write_wrappers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-wrappers", type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        backend = LocalJsonlBackend(Path(tmp) / "memory.jsonl")
        stored = post_skill(backend, "grill-with-docs", SESSION_ONE)
        assert stored >= 3, f"expected at least 3 memories, stored {stored}"

        injected = pre_skill(backend, "tdd", SESSION_TWO_TASK)
        assert "AuthGateway" in injected
        assert "typed Result" in injected

        score = repeated_instruction_reduction(SESSION_ONE, SESSION_TWO_TASK, injected)
        assert score["covered_by_memory"] > 0

    if args.write_wrappers:
        written = write_wrappers(args.write_wrappers)
        assert len(written) == 3

    print("validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

