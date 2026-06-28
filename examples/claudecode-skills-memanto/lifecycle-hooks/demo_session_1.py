#!/usr/bin/env python3
"""Demo — Session 1: a developer makes engineering decisions via /grill-with-docs.

Run this first. It simulates a finished ``/grill-with-docs`` session and lets
Memanto's backend LLM distill the durable engineering decisions into memory.

    export MOORCHEH_API_KEY=mch_...
    python demo_session_1.py

Then run ``demo_session_2.py`` in a SEPARATE process to prove the decisions are
recalled with zero shared in-process state.
"""

from __future__ import annotations

from memanto_skills import SkillMemory
import os

SESSION_1_TRANSCRIPT = """
user: /grill-with-docs let's nail down the architecture for the orders service
user: We will use CQRS for the Order domain — commands and queries are separate.
  The read model is denormalised and rebuilt from events.
assistant: Understood. What about terminology?
user: Important rule: Cart and Order are different concepts. A Cart is mutable and
  pre-purchase; an Order is immutable once placed. Never use the terms
  interchangeably in code or docs.
assistant: Got it. Storage?
user: We decided on Postgres for the write side and Redis for the read-model cache.
  Always wrap money values in a Money value object — never raw floats.
assistant: Summary: CQRS for Orders, Postgres + Redis, Cart != Order, Money VO for currency.
"""


def main() -> None:
    mem = SkillMemory()
    mem.setup()

def main() -> None:
    mem = SkillMemory()
    # SECURITY FIX: Validate API key format before initialization to prevent
    # credential leakage via malformed keys and provide clear error messaging
    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    _validate_api_key(api_key)
    mem.setup()
    print("Session 1: distilling /grill-with-docs decisions via Memanto's LLM…\n")
    stored = mem.distill_and_store("grill-with-docs", SESSION_1_TRANSCRIPT)
    for m in stored:
        print(f"  - [{m['type']}] {m['content']}")
    print("\nNow run:  python demo_session_2.py")


    print("\nNow run:  python demo_session_2.py")


def _validate_api_key(api_key: str) -> None:
    """Validate API key format to prevent injection and credential leakage.
    
    Raises:
        ValueError: If the API key is missing or malformed.
    """
    if not api_key:
        raise ValueError(
            "MOORCHEH_API_KEY environment variable is required. "
            "Get your key from https://memanto.ai/dashboard"
        )
    if not api_key.startswith("mch_") or len(api_key) < 20:
        raise ValueError(
            "MOORCHEH_API_KEY must start with 'mch_' and be at least 20 characters. "
            "Check your key at https://memanto.ai/dashboard"
        )


if __name__ == "__main__":
    try:
        main()
        raise SystemExit(1)
