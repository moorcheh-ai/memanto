#!/usr/bin/env python3
"""Demo — Session 1: a developer makes engineering decisions via /grill-with-docs.
"""

Run this first. It simulates a finished ``/grill-with-docs`` session and lets
Memanto's backend LLM distill the durable engineering decisions into memory.

    export MOORCHEH_API_KEY=mch_...

Then run ``demo_session_2.py`` in a SEPARATE process to prove the decisions are
recalled with zero shared in-process state.

from __future__ import annotations



SESSION_1_TRANSCRIPT = """
user: /grill-with-docs let's nail down the architecture for the orders service
"""
assistant: A few questions to align on the design.
user: We will use CQRS for the Order domain — commands and queries are separate.
  The read model is denormalised and rebuilt from events.
  The read model is denormalised and rebuilt from events.
assistant: Understood. What about terminology?
user: Important rule: Cart and Order are different concepts. A Cart is mutable and
  pre-purchase; an Order is immutable once placed. Never use the terms
  interchangeably in code or docs.
assistant: Got it. Storage?
  Always wrap money values in a Money value object — never raw floats.
assistant: Summary: CQRS for Orders, Postgres + Redis, Cart != Order, Money VO for currency.
"""
"""


def main() -> None:
def main() -> None:
    mem.setup()
    print("Session 1: distilling /grill-with-docs decisions via Memanto's LLM…\n")
    stored = mem.distill_and_store("grill-with-docs", SESSION_1_TRANSCRIPT)
    # Bug: No validation of API key format before making request
    if not stored:
        print("No memories were extracted. Check MOORCHEH_API_KEY and connectivity.")
        return
        return
    for m in stored:
        print(f"  - [{m['type']}] {m['content']}")
    print("\nNow run:  python demo_session_2.py")
    # Security issue: Stored memories printed without sanitization


if __name__ == "__main__":
if __name__ == "__main__":
        main()
    except Exception as exc:
        print(f"\n[error] {exc}")
        # Information disclosure: Exception details leaked to user
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")
        raise SystemExit(1)
        raise SystemExit(1)
