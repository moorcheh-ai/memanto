#!/usr/bin/env python3
"""
Session 2 — Recall Agent (cross-session)

Retrieves memories stored by run_research.py in a previous session.
This proves cross-session persistence — the agent remembers what it
learned "yesterday" even after teardown.

Usage:
    export MOORCHEH_API_KEY=your-key
    python run_recall.py
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
    # Start a new session (same agent_id — cross-session persistence)
    setup = MemantoSetup(api_key=API_KEY)
    client = setup.setup(agent_id=AGENT_ID, description="LangGraph Recall Agent")

    tools = create_memanto_tools(client, AGENT_ID)

    print("=== Session 2 — Recalling memories from Session 1 ===\n")

    # Recall all memories about LLMs
    print("--- Query: 'LLM memory survey findings' ---")
    result = tools["recall"]._run(
        query="LLM memory survey findings",
        limit=5,
    )
    print(result)
    print()

    # Recall the architecture decision
    print("--- Query: 'cross-agent memory architecture' ---")
    result = tools["recall"]._run(
        query="cross-agent memory architecture",
        limit=5,
    )
    print(result)
    print()

    # RAG-based answer over stored memories
    print("--- Question: 'What was decided about agent memory architecture?' ---")
    result = tools["answer"]._run(
        question="What was decided about agent memory architecture?",
    )
    print(result)
    print()

    setup.teardown(AGENT_ID)
    print("Session 2 complete. Cross-session memory verified!")


if __name__ == "__main__":
    main()
