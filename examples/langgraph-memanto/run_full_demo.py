#!/usr/bin/env python3
from __future__ import annotations

from run_today import run_today
from seed_yesterday import seed_yesterday


def main() -> None:
    print("\n=== Session 1: yesterday ===")
    seed_yesterday()
    print("\n=== Session 2: today ===")
    run_today()


if __name__ == "__main__":
    main()
