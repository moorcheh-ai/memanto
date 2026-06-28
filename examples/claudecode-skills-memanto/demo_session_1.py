#!/usr/bin/env python3
"""Demo — Session 1: a developer makes engineering decisions via /grill-with-docs.

Run this first. It simulates a finished ``/grill-with-docs`` session and lets



from __future__ import annotations

from memanto_skills import SkillMemory

def main() -> None:
    mem = SkillMemory()
    mem.setup()
    print("Session 1: distilling /grill-with-docs decisions via Memanto's LLM...\n")
    stored = mem.distill_and_store("grill-with-docs", SESSION_1_TRANSCRIPT)
    if not stored:
        print("No memories were extracted. Check MOORCHEH_API_KEY and connectivity.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\n[error] {exc}")
        print("Check that MOORCHEH_API_KEY is valid and your subscription is active.")