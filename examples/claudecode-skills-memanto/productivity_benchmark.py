"""Deterministic two-session benchmark for the developer-skills hook."""

from __future__ import annotations

import json
from pathlib import Path

from skill_memory_hook import (
    DEFAULT_AGENT,
    extract_memories,
    recall_local,
    remember_local,
)

SESSION_ONE_SUMMARY = (
    "Decision: invoices reject negative totals. "
    "Convention: billing tests use domain fixtures. "
    "Gotcha: legacy invoice imports encode totals as Decimal strings."
)
SESSION_TWO_TASK = "/tdd add invoice validation for legacy imports"


def run_benchmark(store: Path) -> dict[str, int]:
    """Persist session-one constraints, then measure session-two recall."""

    expected = extract_memories(SESSION_ONE_SUMMARY)
    for memory in expected:
        remember_local(
            store,
            content=memory.content,
            agent=DEFAULT_AGENT,
            memory_type=memory.memory_type,
            title=memory.title,
            tags=["developer-skills", "/spec"],
        )

    recalled = recall_local(
        store,
        query=SESSION_TWO_TASK,
        agent=DEFAULT_AGENT,
        limit=len(expected),
    )
    recalled_content = {str(record["content"]) for record in recalled}
    missing = [memory for memory in expected if memory.content not in recalled_content]
    return {
        "saved_memories": len(expected),
        "recalled_memories": len(recalled),
        "repeated_instructions": len(missing),
    }


def main() -> int:
    """Run the benchmark and print reviewer-friendly JSON."""

    store = Path(".memanto-skills-benchmark.jsonl")
    if store.exists():
        store.unlink()
    result = run_benchmark(store)
    print(json.dumps(result, indent=2))
    store.unlink(missing_ok=True)
    return 0 if result["repeated_instructions"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
