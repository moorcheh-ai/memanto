#!/usr/bin/env python3
"""
examples/memory_demo.py
=======================
Self-contained demo that shows Memanto's cross-session memory in action
WITHOUT requiring an LLM API key.

It directly exercises the MeMantoMemory and MeMantoCrewMemory classes
to prove the store → recall → correct → recall cycle works.

Run:
    # Start Memanto first
    memanto serve   # or:  cd memanto && uvicorn memanto.main:app

    # Then in another terminal:
    python examples/memory_demo.py --api-key YOUR_MOORCHEH_KEY
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memanto_bridge import MeMantoCrewMemory

DIVIDER = "─" * 60


def step(n: int, title: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  STEP {n}: {title}")
    print(DIVIDER)


def main() -> None:
    parser = argparse.ArgumentParser(description="Memanto memory demo (no LLM required)")
    parser.add_argument("--url", default=os.getenv("MEMANTO_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.getenv("MOORCHEH_API_KEY", ""))
    parser.add_argument("--namespace", default="crewai-memory-demo")
    args = parser.parse_args()

    print("\n🧠  CrewAI + Memanto  –  Memory Demo")
    print(f"    Server   : {args.url}")
    print(f"    Namespace: {args.namespace}")

    mem = MeMantoCrewMemory(
        base_url=args.url,
        api_key=args.api_key,
        agent_id=args.namespace,
    )

    # ── Step 1: ResearchAgent stores findings ────────────────────────────────
    step(1, "ResearchAgent stores findings (simulates Session A)")

    findings = [
        ("Python 3.12 introduced 'perf' mode which speeds up CPython by ~5%.", ["python", "performance"]),
        ("LLM-assisted code review reduces bug escape rate by ~30% (2024 study).", ["llm", "code-review"]),
        ("GitHub Copilot is used by over 1.8 million developers as of Q1 2025.", ["copilot", "adoption"]),
        ("The global AI developer tools market will reach $12B by 2027.", ["market", "forecast"]),
    ]

    stored_ids = []
    for content, tags in findings:
        result = mem.store_finding(content=content, agent="ResearchAgent", tags=tags)
        mem_id = result.get("id", "N/A")
        stored_ids.append(mem_id)
        print(f"  ✅ Stored [{mem_id}]: {content[:70]}…")
        time.sleep(0.3)  # avoid rate limits

    print(f"\n  Stored {len(stored_ids)} findings. IDs: {stored_ids}")

    # ── Step 2: Simulate session boundary ────────────────────────────────────
    step(2, "Simulating session boundary (different process / 24 hours later)")
    print("  💤  (In a real scenario this would be a new Python process run)")
    time.sleep(1)

    # ── Step 3: WriterAgent recalls findings ─────────────────────────────────
    step(3, "WriterAgent recalls findings from Memanto (Session B)")

    queries = [
        "Python performance improvements",
        "AI tools impact on developers",
        "LLM code assistance statistics",
    ]

    for q in queries:
        print(f"\n  🔍 Recalling: '{q}'")
        results = mem.recall_findings(query=q, limit=3)
        if results:
            for r in results:
                print(f"     [{r['id']}] {r['memory'][:100]}…")
        else:
            print("     (no results – is Memanto server running?)")

    # ── Step 4: RAG answer ────────────────────────────────────────────────────
    step(4, "WriterAgent uses RAG to synthesize an answer")
    question = "What is the current state of AI developer tools adoption and their impact?"
    print(f"  ❓ Question: {question}")
    answer = mem.answer(question)
    print(f"  🧠 Answer:\n     {answer or '(empty – check Memanto server)'}")

    # ── Step 5: Contradictory memory correction ───────────────────────────────
    step(5, "Correcting a contradictory memory (bonus: conflict resolution)")

    if stored_ids and stored_ids[2] != "N/A":
        old_id = stored_ids[2]
        new_fact = "GitHub Copilot surpassed 2.3 million developers as of Q2 2025 (updated figure)."
        print(f"  🔄 Memory {old_id} had outdated Copilot adoption figure.")
        print(f"     Correcting with: {new_fact}")
        updated = mem.correct_memory(memory_id=old_id, new_fact=new_fact)
        print(f"  ✅ Memory corrected. Old content archived in metadata.")

        # Confirm new fact is recalled
        results = mem.recall_findings(query="GitHub Copilot developers", limit=1)
        if results:
            print(f"  🔍 Re-recalled: {results[0]['memory'][:120]}")
    else:
        print("  ⚠️  Skipping correction (no valid memory IDs – check server connection)")

    # ── Done ─────────────────────────────────────────────────────────────────
    print(f"\n{DIVIDER}")
    print("  ✨  Demo complete!")
    print("  All memories are permanently stored in Memanto.")
    print("  Run this script again to see cross-session recall from the top.")
    print(f"{DIVIDER}\n")


if __name__ == "__main__":
    main()
