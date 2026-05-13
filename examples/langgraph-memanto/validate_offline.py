#!/usr/bin/env python3
"""Credential-free verification for the LangGraph + Memanto example."""

from __future__ import annotations

import tempfile
from pathlib import Path

from memory_backend import LocalJsonMemory
from run_demo import SESSION_ONE_MESSAGE, SESSION_TWO_MESSAGE, USER_ID
from support_graph import run_turn


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        store_path = Path(directory) / "memories.json"

        day_one_backend = LocalJsonMemory(store_path)
        day_one = run_turn(
            backend=day_one_backend,
            session_id="validator-day-one",
            user_id=USER_ID,
            user_message=SESSION_ONE_MESSAGE,
        )
        assert len(day_one["stored_memories"]) == 4

        # Re-open the backend to prove recall survives beyond Python objects
        # and outside the first LangGraph invocation's state.
        day_two_backend = LocalJsonMemory(store_path)
        day_two = run_turn(
            backend=day_two_backend,
            session_id="validator-day-two-fresh-thread",
            user_id=USER_ID,
            user_message=SESSION_TWO_MESSAGE,
        )

        response = day_two["response"].lower()
        assert "pr-1842" in response
        assert "replacement before refund" in response
        assert "may 28" in response
        assert len(day_two["recalled_memories"]) >= 3

    print("offline validation passed")


if __name__ == "__main__":
    main()

