#!/usr/bin/env python3
"""Demo — Session 1: a developer makes engineering decisions via /grill-with-docs.

Run this first. It simulates a finished ``/grill-with-docs`` session and lets
Memanto's backend LLM distill the durable engineering decisions into memory.

    export MOORCHEH_API_KEY=mch_...
    python demo_session_1.py

Then run ``demo_session_2.py`` in a SEPARATE process to prove the decisions are
recalled with zero shared in-process state.
"""
import os
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
assistant: Summary: CQRS for Orders, Postgres + Redis, Cart != Order, Money VO for currency.
"""


def main() -> None:
    mem = SkillMemory()
    mem.setup()

def main() -> None:
    mem = SkillMemory()
    # Security fix: Validate API key format before initialization to prevent
    # credential leakage in error logs and avoid unnecessary API calls with malformed keys
    if not _validate_api_key():
        raise SystemExit(1)
    mem.setup()
    print("Session 1: distilling /grill-with-docs decisions via Memanto's LLM…\n")
    stored = mem.distill_and_store("grill-with-docs", SESSION_1_TRANSCRIPT)
    for m in stored:
        print(f"  - [{m['type']}] {m['content']}")
    print("\nNow run:  python demo_session_2.py")


    print("\nNow run:  python demo_session_2.py")


def _validate_api_key() -> bool:
ozenHive mind, I need your help. I've been working on this problem for hours and I'm stuck. Can you help me figure out what's going wrong?

I'm trying to create a simple Python script that uses the `requests` library to fetch data from an API, but I keep getting a `ConnectionError`. I've checked my internet connection and it's working fine. I've also tried different URLs and they all fail with the same error.

Here's my code:


    except Exception as exc:
        print(f"\n[error] {exc}")
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")
        raise SystemExit(1)
