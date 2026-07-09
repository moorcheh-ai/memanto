#!/usr/bin/env python3
"""Demo — Session 1: a developer makes engineering decisions via /grill-with-docs.

Run this first. It simulates a finished ``/grill-with-docs`` session and lets
Memanto's backend LLM distill the durable engineering decisions into memory.

    export MOORCHEH_API_KEY=mch_...
    python demo_session_1.py


from __future__ import annotations

try:
    from memanto import SkillMemory
except ImportError:
    try:
        from memanto.skills import SkillMemory
    except ImportError:
        raise ImportError("Could not import SkillMemory. Ensure memanto is installed: pip install memanto")

SESSION_1_TRANSCRIPT = """
user: /grill-with-docs let's nail down the architecture for the orders service

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
    mem.setup()
    print("Session 1: distilling /grill-with-docs decisions via Memanto's LLM…")
    if not os.environ.get("MOORCHEH_API_KEY"):
        print("[warning] MOORCHEH_API_KEY environment variable is not set.")
        print("Set it with: export MOORCHEH_API_KEY=mch_...")
        print("Continuing anyway in case key is configured elsewhere…\n")
    stored = mem.distill_and_store("grill-with-docs", SESSION_1_TRANSCRIPT)
    if not stored:
        print("No memories were extracted. Check MOORCHEH_API_KEY and connectivity.")
    print("Session 1: distilling /grill-with-docs decisions via Memanto's LLM…\n")
    stored = mem.distill_and_store("grill-with-docs", SESSION_1_TRANSCRIPT)
    if not stored:
        print("No memories were extracted. Check MOORCHEH_API_KEY and connectivity.")
        return


if __name__ == "__main__":
    import os
    try:
        main()
    except Exception as exc:
if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[error] {exc}")
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")
        raise SystemExit(1)
