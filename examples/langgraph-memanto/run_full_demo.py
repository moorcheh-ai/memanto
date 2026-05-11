"""Run the two-session LangGraph + Memanto demo end to end."""

from __future__ import annotations

from run_day1_seed_memory import main as run_day1
from run_day2_recall import main as run_day2


if __name__ == "__main__":
    print("=== Day 1: seed memory ===")
    run_day1()
    print("\n=== Day 2: recall memory in a new graph session ===")
    run_day2()
