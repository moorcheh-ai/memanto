#!/usr/bin/env python3
"""Demo — Session 1: a developer makes engineering decisions via /grill-with-docs.

Run this first. It simulates a finished ``/grill-with-docs`` session and lets
Memanto's backend LLM distill the durable engineering decisions into memory.

    python demo_session_1.py

Then run ``demo_session_2.py`` in a SEPARATE process to prove the decisions are
recalled with zero shared in-process state.  ← FIXED: added API-key validation.
"""

from __future__ import annotations
from __future__ import annotations

from memanto_skills import SkillMemory

SESSION_1_TRANSCRIPT = """
user: /grill-with-docs let's nail down the architecture for the orders service
assistant: A few questions to align on the design.
user: We will use CQRS for the Order domain — commands and queries are separate.
  The read model is denormalised and rebuilt from events.
assistant: Understood. What about terminology?
user: Important rule: Cart and Order are different concepts. A Cart is mutable and
  pre-purchase; an Order is immutable once placed. Never use the terms
  interchangeably in code or docs.
assistant: Got it. Storage?
user: We decided on Postgres for the write side and Redis for the read-model cache.
  Always wrap money values in a Money value object — never raw floats.


def main() -> None:
    import os
    import sys

    api_key = os.getenv("MOORCHEH_API_KEY", "").strip()
    if not api_key:
        print("[error] MOORCHEH_API_KEY environment variable is not set or is empty.")
        print("Export it before running:  export MOORCHEH_API_KEY=mch_...")
        raise SystemExit(1)
    if not api_key.startswith("mch_"):
        print("[error] MOORCHEH_API_KEY does not look valid (should start with 'mch_').")
        raise SystemExit(1)

    mem = SkillMemory()
    mem.setup()
    print("Session 1: distilling /grill-with-docs decisions via Memanto's LLM…\n")
    stored = mem.distill_and_store("grill-with-docs", SESSION_1_TRANSCRIPT)
    if not stored:
        print("No memories were extracted. Check MOORCHEH_API_KEY and connectivity.")
        raise SystemExit(1)
    print(f"Stored {len(stored)} engineering memories:")
    for m in stored:
        print(f"  - [{m['type']}] {m['content']}")
    print("\nNow run:  python demo_session_2.py")
        print(f"  - [{m['type']}] {m['content']}")
    print("\nNow run:  python demo_session_2.py")
if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        print(f"\n[error] {exc}")
        raise SystemExit(1)
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")
        raise SystemExit(1)
