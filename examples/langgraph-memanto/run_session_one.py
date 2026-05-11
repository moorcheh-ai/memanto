#!/usr/bin/env python3
"""
Session one: store explicit user preferences in Memanto.

Run this first, then run run_session_two.py from a separate terminal session to
prove the LangGraph state was not carrying the memory.
"""

from __future__ import annotations

from runner import run_message


MESSAGE = (
    "My name is Maya. I prefer vegetarian meal kits and I hate cilantro. "
    "Please remember that for future dinner recommendations."
)


if __name__ == "__main__":
    run_message("Session one - write memories", MESSAGE)
