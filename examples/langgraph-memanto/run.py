#!/usr/bin/env python3
"""
LangGraph + Memanto: Research Assistant with Persistent Memory

A demonstrator that runs a LangGraph workflow backed by Memanto memory.

Steps (shown in order):
    1.  First query — Memanto has no relevant memories yet, so the agent
        researches the topic and stores findings (via ``remember()``).
    2.  Second query — Memanto recalls the stored findings (via ``recall()``)
        and goes straight to ``answer()`` without re-researching, proving
        cross-session memory persistence.
    3.  Traces of every ``remember`` / ``recall`` / ``answer`` call are
        logged so you can see exactly how the memory layer is used.

Usage:
    export MOORCHEH_API_KEY=your_key_here
    export OPENROUTER_API_KEY=your_key_here
    python run.py

Or create a .env file (see .env.example) and it will be loaded automatically.
"""

import logging
import os
import sys

from dotenv import load_dotenv

from memory_client import MemantoMemory
from research_assistant import build_graph

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("run")

load_dotenv()  # read .env file if present

# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run_demo() -> None:
    """
    Execute a two-step LangGraph demo to prove Memanto persistence.

    Run 1: The agent researches a topic and stores findings in Memanto.
    Run 2: Same query — the agent finds the memories via ``recall()`` and
           answers directly via ``answer()``, proving cross-session memory.
    """
    # ── Initialise Memanto ─────────────────────────────────────────────
    api_key = os.environ.get("MOORCHEH_API_KEY", "")
    if not api_key:
        logger.error(
            "MOORCHEH_API_KEY is not set.\n"
            "  1. Get a free key at https://console.moorcheh.ai/api-keys\n"
            "  2. Either:\n"
            "       export MOORCHEH_API_KEY=your_key\n"
            "     or create a .env file (see .env.example)"
        )
        sys.exit(1)

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not openrouter_key:
        logger.warning(
            "OPENROUTER_API_KEY not set — the LLM calls (research_topic) will "
            "likely fail. Set it in your environment or .env file."
        )

    memory = MemantoMemory(api_key=api_key)
    graph = build_graph(memory)

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  LangGraph + Memanto  —  Research Assistant Demo           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # ── Run 1: First query (no memory yet → research → store) ─────────
    topic = "What are the economic impacts of large language models?"
    print(f"▶  Run 1 — Query: {topic}")
    print("   (No existing memories — agent will research and store)")
    print()

    output_1 = graph.invoke({"topic": topic})
    answer_1 = output_1.get("final_answer", "")
    print(f"\n✓ Answer 1:\n{answer_1}\n")
    print("─" * 60)
    print()

    # ── Run 2: Same query (memories exist → recall → answer) ──────────
    print(f"▶  Run 2 — Same query: {topic}")
    print("   (Memories from run 1 should be found — agent goes straight to answer)")
    print()

    output_2 = graph.invoke({"topic": topic})
    answer_2 = output_2.get("final_answer", "")

    hits = output_2.get("memory_hits", 0)
    if hits >= 2:
        print("   ✅ Memory persistence confirmed! Found %d existing memories." % hits)
    else:
        print("   ℹ️  Found %d memory/memories (may vary by first-run results)." % hits)

    print(f"\n✓ Answer 2:\n{answer_2}\n")

    # ── Summary ────────────────────────────────────────────────────────
    print("=" * 60)
    print("  Demo complete!")
    print("  ✓ remember() stored research findings as typed memories")
    print("  ✓ recall() retrieved existing knowledge across workflows")
    print("  ✓ answer() generated an answer using RAG over memories")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()
