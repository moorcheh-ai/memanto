"""Single-command end-to-end pipeline: seed -> adapt -> validate.

python run.py           # full run (rebuilds checkpoint store if missing)
python run.py --force   # rebuild the source store from scratch first
"""

from __future__ import annotations

import argparse
import os

import adapter
import seed_agent
import validate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild checkpoint store")
    args = ap.parse_args()

    print("=" * 70)
    print("STEP 1/3  Seed a lived-in LangGraph agent (real checkpoint store)")
    print("=" * 70)
    if args.force or not os.path.exists(seed_agent.DB_PATH):
        seed_agent.seed(force=True)
    else:
        print(f"reusing existing store: {seed_agent.DB_PATH}")

    print("\n" + "=" * 70)
    print("STEP 2/3  Migrate LangGraph checkpoints -> OKF bundle")
    print("=" * 70)
    adapter.run()

    print("\n" + "=" * 70)
    print("STEP 3/3  Round-trip recall-parity validation")
    print("=" * 70)
    ok = validate.run()

    print("\n" + "=" * 70)
    print("DONE." if ok else "VALIDATION FAILED.")
    print(f"OKF bundle: {os.path.relpath(adapter.BUNDLE_DIR)}")
    print("Next (live Memanto import, needs a free Moorcheh API key):")
    print(f"  memanto migrate okf {os.path.relpath(adapter.BUNDLE_DIR)} --dry-run")
    print(f"  memanto migrate okf {os.path.relpath(adapter.BUNDLE_DIR)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
