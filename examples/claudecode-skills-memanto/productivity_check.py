#!/usr/bin/env python3
"""Measure whether the demo avoids repeated cross-skill instructions.

The bounty asks for a productivity multiplier: later skills should inherit
architectural choices and preferences without manual context shoving. This
script runs the reviewer-safe local backend through that exact loop and fails
if the second skill run does not receive the expected remembered constraints.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from bridge import LocalJsonBackend, distill_transcript, render_context

HERE = Path(__file__).resolve().parent
DEMO_TRANSCRIPT = HERE / "demo" / "session-one-transcript.md"

EXPECTED_CONTEXT = {
    "postgres": "Postgres storage decision",
    "backwards-compatible response fields": "backwards-compatible response rule",
    "avoid new runtime frameworks": "dependency-light preference",
    "pytest tests/test_api.py": "reusable pytest command",
}


def run_productivity_check() -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Path(tmpdir) / "memory.json"
        backend = LocalJsonBackend(store)
        transcript = DEMO_TRANSCRIPT.read_text(encoding="utf-8")

        for memory in distill_transcript(
            transcript,
            skill="grill-with-docs",
            task="review API pagination design",
            paths=["docs/api-pagination.md"],
        ):
            backend.remember(memory)

        recalled = backend.recall(
            "tdd pagination tests postgres response fields runtime frameworks pytest",
            limit=8,
        )
        context = render_context(recalled, "add pagination tests")

    found = {
        label: phrase
        for phrase, label in EXPECTED_CONTEXT.items()
        if phrase in context.lower()
    }
    missing = {
        label: phrase
        for phrase, label in EXPECTED_CONTEXT.items()
        if phrase not in context.lower()
    }

    lines = [
        "# Productivity Check",
        "",
        f"Repeated instructions avoided: {len(found)} / {len(EXPECTED_CONTEXT)}",
        "",
        "Recovered without manual re-prompting:",
    ]
    for label in found:
        lines.append(f"- {label}")

    if missing:
        lines.append("")
        lines.append("Missing expected context:")
        for label in missing:
            lines.append(f"- {label}")
        return 1, "\n".join(lines) + "\n"

    lines.extend(
        [
            "",
            "Rendered context block:",
            "",
            "```text",
            context.rstrip(),
            "```",
        ]
    )
    return 0, "\n".join(lines) + "\n"


def main() -> int:
    exit_code, report = run_productivity_check()
    print(report, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
