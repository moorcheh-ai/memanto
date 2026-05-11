#!/usr/bin/env python3
"""
Run both sessions in sequence with a new Memanto activation for each session.
"""

from __future__ import annotations

from run_session_one import MESSAGE as SESSION_ONE_MESSAGE
from run_session_two import MESSAGE as SESSION_TWO_MESSAGE
from runner import run_message


def main() -> None:
    run_message("Session one - write memories", SESSION_ONE_MESSAGE)
    print("\n" + "=" * 72 + "\n")
    run_message("Session two - recall from Memanto", SESSION_TWO_MESSAGE)


if __name__ == "__main__":
    main()
