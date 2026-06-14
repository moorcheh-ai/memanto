"""
run_demo.py
===========
Credential-free demo for the Memanto skills memory companion.

Proves cross-session engineering memory without requiring a Moorcheh API key.
Uses the offline mock backend — switch to live with MOORCHEH_API_KEY set.

Usage:
    python run_demo.py            # offline demo
    python run_demo.py --live     # live Memanto API
    python run_demo.py --reset    # reset and run offline demo
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from skills_memory import SkillsMemory, _offline_demo, _live_demo


def main():
    parser = argparse.ArgumentParser(description="Memanto skills demo")
    parser.add_argument("--live", action="store_true", help="Use live Memanto API")
    parser.add_argument("--reset", action="store_true", help="Reset and run offline demo")
    args = parser.parse_args()

    if args.live:
        if not os.getenv("MOORCHEH_API_KEY"):
            print("❌ MOORCHEH_API_KEY not set. Get a free key at https://moorcheh.ai")
            sys.exit(1)
        _live_demo()
    else:
        _offline_demo()


if __name__ == "__main__":
    main()
