#!/usr/bin/env python3
"""
Session 1 — Research Agent

Stores findings into Memanto's persistent memory. Run this first,
then run run_recall.py to verify cross-session memory persistence.

Usage:
    export MOORCHEH_API_KEY=your-key
    python run_research.py
"""

import os
import logging

from dotenv import load_dotenv
from memanto.cli.client.sdk_client import SdkClient
from memanto_langgraph import MemantoSetup, create_memanto_tools

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
load_dotenv()

API_KEY = os.environ["MOORCHEH_API_KEY"]
AGENT_ID = "langgraph-research-agent"


def main():
    # Setup Memanto session
    setup = MemantoSetup(api_key=API_KEY)
    client = setup.setup(agent_id=AGENT_ID, description="LangGraph Research Agent")

    tools = create_memanto_tools(client, AGENT_ID)

    # Store research findings — these should be recallable tomorrow
    print("=== Storing Session 1 memories ===\n")

    result = tools["remember"]._run(
        memory_type="fact",
        title="LLM Memory Survey 2025",
        content="Memory-augmented LLMs improve task completion by 34% over base models in long-horizon tasks.",
        confidence=0.9,
        tags="research,llm,memory",
    )
    print(result)
    print()

    result = tools["remember"]._run(
        memory_type="observation",
        title="Tool-Use Pattern",
        content="LangGraph agents using persistent memory show 2.3x fewer repeated tool calls.",
        confidence=0.85,
        tags="langgraph,agents,memory",
    )
    print(result)
    print()

    result = tools["remember"]._run(
        memory_type="decision",
        title="Adopt Memanto for cross-agent memory",
        content="Selected Memanto as shared memory layer for multi-agent LangGraph workflows.",
        confidence=1.0,
        tags="decision,architecture,memanto",
    )
    print(result)
    print()

    # Teardown
    setup.teardown(AGENT_ID)
    print("Session 1 complete. Memories persist in Memanto.")


if __name__ == "__main__":
    main()
