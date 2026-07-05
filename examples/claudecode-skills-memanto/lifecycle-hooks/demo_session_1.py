#!/usr/bin/env python3
"""Demo — Session 1: a developer makes engineering decisions via /grill-with-docs.

Run this first. It simulates a finished ``/grill-with-docs`` session and lets
Memanto's backend LLM distill the durable engineering decisions into memory.

    export MOORCHEH_API_KEY=mch_...
    python demo_session_1.py

Then run ``demo_session_2.py`` in a SEPARATE process to prove the decisions are
recalled with zero shared in-process state.

from __future__ import annotations

import sys
from memanto_skills import SkillMemory

SESSION_1_TRANSCRIPT = """
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
    mem = SkillMemory()
    try:
        setup_ok = mem.setup()
    except Exception as exc:
        print(f"[FATAL] SkillMemory.setup() raised an exception: {exc}")
        print("Check that MOORCHEH_API_KEY is set and valid.")
        raise SystemExit(1)
    
    if not setup_ok:
        print("[FATAL] SkillMemory.setup() returned a falsy value — setup failed.")
        print("Verify MOORCHEH_API_KEY, network connectivity, and backend status.")
        raise SystemExit(1)
    
    print("Session 1: distilling /grill-with-docs decisions via Memanto's LLM…\n")
    
    try:
        stored = mem.distill_and_store("grill-with-docs", SESSION_1_TRANSCRIPT)
    except Exception as exc:
        print(f"[FATAL] distill_and_store() raised an exception: {exc}")
        print("The backend may be unreachable or the API key may have insufficient permissions.")
        raise SystemExit(1)
    
    if not stored:
        print("[WARNING] No memories were extracted from the transcript.")
        print("This could indicate:")
        print("  1. The backend LLM failed to identify extractable decisions")
        print("  2. MOORCHEH_API_KEY is invalid or has expired")
        print("  3. Network connectivity issues to the moorcheh.ai backend")
        print("  4. The transcript format is not parseable by the distillation engine")
        print("\nCheck MOORCHEH_API_KEY and connectivity, then re-run.")
        raise SystemExit(1)
    
    print(f"Stored {len(stored)} engineering memories:")
    for m in stored:
        print(f"  - [{m['type']}] {m['content']}")
    print("\n[SUCCESS] Memories stored. Now run:  python demo_session_2.py")


if __name__ == "__main__":


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[error] {exc}")
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")
        raise SystemExit(1)
