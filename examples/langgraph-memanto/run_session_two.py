#!/usr/bin/env python3
"""
Session two: start fresh and recall preferences stored by session one.
"""

from __future__ import annotations

from runner import run_message


MESSAGE = "What dinner kit should I order tonight?"


if __name__ == "__main__":
    run_message("Session two - recall from Memanto", MESSAGE)
