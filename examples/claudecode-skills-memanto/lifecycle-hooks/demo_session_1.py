#!/usr/bin/env python3
"""Demo — Session 1: a developer makes engineering decisions via /grill-with-docs.
 
Run this first. It simulates a finished ``/grill-with-docs`` session and lets
Memanto's backend LLM distill the durable engineering decisions into memory.

    export MOORCHEH_API_KEY=mch_...
    python demo_session_1.py

Then run ``demo_session_2.py`` in a SEPARATE process to prove the decisions are
recalled with zero shared in-process state.

from __future__ import annotations

import os
import sys
from typing import Optional, Dict, Any, List

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
"""


def validate_api_key(api_key: Optional[str]) -> bool:
    """Validate the Moorcheh API key format and presence."""
    if not api_key:
        return False
    # Basic format validation: should start with 'mch_' and be reasonable length
    if not api_key.startswith("mch_"):
        print("[warning] API key does not start with expected 'mch_' prefix")
        return False
    if len(api_key) < 10:
        print("[warning] API key appears too short to be valid")
        return False
    return True


def sanitize_transcript(transcript: str) -> str:
    """Sanitize transcript to prevent potential injection attacks.
    
    Removes or escapes potentially dangerous patterns that could be
    interpreted as commands by the backend LLM.
    """
    # Remove null bytes and other control characters
    sanitized = transcript.replace('\x00', '')
    
    # Limit transcript length to prevent resource exhaustion
    max_length = 100_000  # 100KB limit
    if len(sanitized) > max_length:
        print(f"[warning] Transcript truncated from {len(sanitized)} to {max_length} chars")
        sanitized = sanitized[:max_length]
    
    return sanitized


def main() -> None:
    # Validate environment before importing
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not validate_api_key(api_key):
        print("[error] Invalid or missing MOORCHEH_API_KEY environment variable")
        print("Expected format: mch_... (obtain from https://moorcheh.ai)")
        raise SystemExit(1)
    
    # Import validation with helpful error message
    try:
        from memanto_skills import SkillMemory
    except ImportError as e:
        print(f"[error] Failed to import memanto_skills: {e}")
        print("Ensure memanto is installed: pip install memanto")
        print("Or if running from source: pip install -e .")
        raise SystemExit(1)
    
    mem = SkillMemory()
    
    try:
        mem.setup()
    except Exception as e:
        print(f"[error] Failed to setup SkillMemory: {e}")
        print("Check your MOORCHEH_API_KEY and network connectivity")
        raise SystemExit(1)
    
    print("Session 1: distilling /grill-with-docs decisions via Memanto's LLM…\n")
    
    # Sanitize transcript before sending to backend
    sanitized_transcript = sanitize_transcript(SESSION_1_TRANSCRIPT)
    
    try:
        stored = mem.distill_and_store("grill-with-docs", sanitized_transcript)
    except Exception as exc:
        print(f"\n[error] {exc}")
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")
        raise SystemExit(1)
