#!/usr/bin/env python3
"""
Full Pipeline: Research Agent -> Writer Agent in a single Crew run.

Both agents share the same Memanto memory namespace. The Research Agent
stores findings, then the Writer Agent retrieves and synthesizes them
into an executive briefing -- all in one sequential pipeline.

Usage:
    python run_full_pipeline.py
"""

from __future__ import annotations

import os
import sys

from crew import build_full_crew
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

    # Set up Memanto
    setup = MemantoSetup(api_key)
    client = setup.setup(
        agent_id=AGENT_ID,
        description="Shared memory for CrewAI research pipeline",
    )

    print(f"\n{'=' * 60}")
    print("  Full Pipeline: Research -> Write")
    print(f"  Agent ID: {AGENT_ID}")
    print(f"  Topic: {TOPIC}")
    print(f"{'=' * 60}\n")

    try:
        crew = build_full_crew(client, AGENT_ID, topic=TOPIC, llm=llm)
        result = crew.kickoff()

        print(f"\n{'=' * 60}")
        print("  Pipeline Complete!")
        print(f"{'=' * 60}")
        print(f"\n{result.raw}")
    finally:
        setup.teardown(AGENT_ID)


if __name__ == "__main__":
    main()
