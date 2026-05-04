#!/usr/bin/env python3
"""
run.py  –  CrewAI + Memanto Integration Demo
=============================================

Demonstrates THREE scenarios that prove Memanto's cross-session memory:

  Session A  (--mode research)   ResearchAgent stores findings → Memanto
  Session B  (--mode write)      WriterAgent recalls them (different process run!)
  Full run   (--mode full)       Both agents in one run (default)

Usage
-----
  # Full run (research + write in one go)
  python run.py --topic "The impact of AI on software engineering" --mode full

  # Session A: store findings
  python run.py --topic "Quantum computing in 2025" --mode research

  # Session B: writer recalls from previous session (can be run days later)
  python run.py --topic "Quantum computing in 2025" --mode write

  # Override Memanto connection
  python run.py --topic "..." --memanto-url http://127.0.0.1:8000 --namespace my-crew

Environment variables (alternative to CLI flags):
  MEMANTO_BASE_URL   – Memanto server URL
  MOORCHEH_API_KEY   – Moorcheh API key
  OPENAI_API_KEY     – Required for CrewAI LLM calls
"""

import argparse
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run")

BANNER = """
╔══════════════════════════════════════════════════════════╗
║          CrewAI  +  Memanto  –  Persistent Memory        ║
║     Research Agent stores  →  Writer Agent recalls       ║
╚══════════════════════════════════════════════════════════╝
"""


def print_section(title: str) -> None:
    width = 60
    print("\n" + "─" * width)
    print(f"  {title}")
    print("─" * width)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CrewAI + Memanto cross-session memory demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--topic",
        default="The impact of large language models on software engineering in 2025",
        help="Research topic for the crew.",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "research", "write"],
        default="full",
        help=(
            "full = both agents in sequence | "
            "research = ResearchAgent only (stores to Memanto) | "
            "write = WriterAgent only (recalls from Memanto)"
        ),
    )
    parser.add_argument(
        "--memanto-url",
        default=os.getenv("MEMANTO_BASE_URL", "http://127.0.0.1:8000"),
        help="Memanto server base URL.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("MOORCHEH_API_KEY", ""),
        help="Moorcheh API key.",
    )
    parser.add_argument(
        "--namespace",
        default="research-writer-crew",
        help="Memanto agent_id / namespace (shared across sessions).",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="LLM model for agents.",
    )
    args = parser.parse_args()

    print(BANNER)

    # ── Pre-flight checks ────────────────────────────────────────────────────
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  WARNING: OPENAI_API_KEY not set. CrewAI LLM calls will fail.")
        print("   Export it: export OPENAI_API_KEY=sk-...")

    # Map CLI mode to crew run_mode value
    run_mode_map = {"full": "full", "research": "research_only", "write": "write_only"}
    run_mode = run_mode_map[args.mode]

    print_section(f"Topic    : {args.topic}")
    print(f"  Mode     : {args.mode}")
    print(f"  Namespace: {args.namespace}  (shared Memanto agent_id)")
    print(f"  Server   : {args.memanto_url}")
    print(f"  Model    : {args.model}")

    if args.mode == "write":
        print(
            "\n  ℹ️  Write-only mode: WriterAgent will recall memories stored by a\n"
            "     ResearchAgent from a PREVIOUS run. This proves cross-session memory."
        )
    elif args.mode == "research":
        print(
            "\n  ℹ️  Research-only mode: Findings will be stored in Memanto.\n"
            "     Run with --mode write later to have the Writer recall them."
        )

    # ── Import here so startup errors are caught cleanly ────────────────────
    try:
        from crew import build_crew
    except ImportError as exc:
        print(f"\n❌ Import error: {exc}")
        print("   Run: pip install -r requirements.txt")
        sys.exit(1)

    # ── Build & kick off the crew ────────────────────────────────────────────
    print_section("Building Crew…")
    crew = build_crew(
        topic=args.topic,
        memanto_base_url=args.memanto_url,
        memanto_api_key=args.api_key,
        namespace=args.namespace,
        llm_model=args.model,
        run_mode=run_mode,
    )

    print_section("🚀 Crew Kickoff")
    start = time.time()
    try:
        result = crew.kickoff()
    except Exception as exc:
        logger.error("Crew execution failed: %s", exc, exc_info=True)
        sys.exit(1)

    elapsed = time.time() - start

    print_section(f"✅ Done in {elapsed:.1f}s")
    print("\n" + "═" * 60)
    print(result)
    print("═" * 60 + "\n")


if __name__ == "__main__":
    main()
