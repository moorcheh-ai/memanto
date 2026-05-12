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
from dotenv import load_dotenv
from memanto_crewai import MemantoSetup

AGENT_ID = "crewai-research-team"
TOPIC = "AI agent frameworks"


def main() -> None:
    load_dotenv()

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print(
            "Error: MOORCHEH_API_KEY not set. Copy .env.example to .env and fill it in."
        )
        sys.exit(1)

    llm = os.environ.get("CREWAI_LLM", "openrouter/tencent/hy3-preview:free")

    # Set up Memanto - reuses the SAME agent_id as the Research Agent
    setup = MemantoSetup(api_key)
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
        print(f"\n{result.raw}")
    finally:
        setup.teardown(AGENT_ID)


if __name__ == "__main__":
    main()
