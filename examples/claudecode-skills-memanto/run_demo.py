#!/usr/bin/env python3
"""Credential-free demo for the Claude Code skills Memanto example."""

from __future__ import annotations

import sys
from pathlib import Path

from context_capsules import main

STORE = Path(".memanto/demo-capsules.jsonl")
PROJECT = "acme-saas"


def run_step(title: str, args: list[str]) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")
    return_code = main(args)
    if return_code:
        sys.exit(return_code)


def main_demo() -> None:
    STORE.unlink(missing_ok=True)

    run_step(
        "Day 1: /grill-with-docs captures architectural decisions",
        [
            "capture",
            "--project",
            PROJECT,
            "--session",
            "day-1-architecture",
            "--skill",
            "/grill-with-docs",
            "--files",
            "src/billing/webhooks.py,src/billing/models.py",
            "--store",
            str(STORE),
            "--summary",
            "\n".join(
                [
                    "Decision: Stripe webhook handlers must be idempotent by event id.",
                    "Constraint: Billing writes must use advisory locks around invoices.",
                    "Preference: Keep HTTP route handlers thin and move billing logic to services.",
                    "Gotcha: Never persist STRIPE_SECRET_KEY=sk_live_1234567890 in logs.",
                ]
            ),
        ],
    )

    run_step(
        "Day 2: /tdd receives only relevant memories for invoice tests",
        [
            "recall",
            "--project",
            PROJECT,
            "--task",
            "/tdd write tests for duplicate Stripe webhook invoice delivery",
            "--files",
            "src/billing/webhooks.py,tests/test_billing_webhooks.py",
            "--store",
            str(STORE),
        ],
    )

    print(
        "\nDemo complete: the second skill starts with prior billing decisions, "
        "while the secret-shaped token was redacted before storage."
    )


if __name__ == "__main__":
    main_demo()
