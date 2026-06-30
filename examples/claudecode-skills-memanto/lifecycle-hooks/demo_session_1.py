#!/usr/bin/env python3
"""Demo — Session 1: a developer makes engineering decisions via /grill-with-docs.

Run this first. It simulates a finished ``/grill-with-docs`` session and lets
Memanto's backend LLM distill the durable engineering decisions into memory.

    export MOORCHEH_API_KEY=mch_...
    python demo_session_1.py

Then run ``demo_session_2.py`` in a SEPARATE process to prove the decisions are
recalled with zero shared in-process state.
from __future__ import annotations

from memanto_skills import SkillMemory
import os

SESSION_1_TRANSCRIPT = """
user: /grill-with-docs let's nail down the architecture for the orders service
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
assistant: Summary: CQRS for Orders, Postgres + Redis, Cart != Order, Money VO for currency.
"""


def main() -> None:
    mem = SkillMemory()
    # SECURITY FIX: Validate API key format before initialization to prevent
    # credential leakage via error messages and avoid unnecessary API calls
    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    _validate_api_key(api_key)
    mem.setup()
    print("Session 1: distilling /grill-with-docs decisions via Memanto's LLM…\n")
    stored = mem.distill_and_store("grill-with-docs", SESSION_1_TRANSCRIPT)
    if not stored:
        print("No memories were extracted. Check MOORCHEH_API_KEY and connectivity.")
        return
    print(f"Stored {len(stored)} engineering memories:")
    for m in stored:
    print("\nNow run:  python demo_session_2.py")


def _validate_api_key(api_key: str) -> None:
    """Validate API key format to prevent injection and credential leakage.
    
    Raises:
        ValueError: If the API key format is invalid.
    """
    if not api_key:
        raise ValueError("MOORCHEH_API_KEY environment variable is required")
    if not api_key.startswith("mch_"):
        raise ValueError("MOORCHEH_API_KEY must start with 'mch_' prefix")
    # Prevent potential log injection / credential exfiltration via newlines
    if "\n" in api_key or "\r" in api_key:
        raise ValueError("MOORCHEH_API_KEY contains invalid characters")
    # Prevent overly long keys that could indicate injection attacks
    if len(api_key) > 256:
        raise ValueError("MOORCHEH_API_KEY exceeds maximum allowed length")


if __name__ == "__main__":
    try:
        main()
        main()
    except Exception as exc:
        print(f"\n[error] {exc}")
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")
        raise SystemExit(1)
