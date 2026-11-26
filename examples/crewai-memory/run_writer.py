#!/usr/bin/env python3
"""
Run 2: Writer Agent recalls memories and writes a briefing.

This script demonstrates cross-session persistence: the Writer Agent
retrieves memories stored by the Research Agent in a previous run
(run_research.py) and produces an executive briefing.

Usage:
    python run_writer.py
"""

from __future__ import annotations

import os
import sys

from crew import build_writer_crew
from crewai_memanto import MemantoSetup
from dotenv import load_dotenv

AGENT_ID = "crewai-research-team"
TOPIC = "AI agent frameworks"


def main() -> None:
    load_dotenv()

    llm = os.environ.get("CREWAI_LLM", "openrouter/baidu/cobuddy:free")

    # Set up Memanto - reuses the SAME agent_id as the Research Agent
    try:
        setup = MemantoSetup()
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    client = setup.setup(
        agent_id=AGENT_ID,
        description="Shared memory for CrewAI research pipeline",
    )

    print(f"\n{'=' * 60}")
    print("  Writer Agent - Retrieving memories from Memanto")
    print(f"  Agent ID: {AGENT_ID}")
    print(f"  Topic: {TOPIC}")
    print(f"{'=' * 60}")
    print("  (Using memories stored by Research Agent in a previous run)")
    print()

    try:
        crew = build_writer_crew(client, AGENT_ID, topic=TOPIC, llm=llm)
        result = crew.kickoff()

        print(f"\n{'=' * 60}")
        print("  Executive Briefing")
        print(f"{'=' * 60}")
        print(f"\n{result}")
    finally:
        setup.teardown(AGENT_ID)


if __name__ == "__main__":
    main()
