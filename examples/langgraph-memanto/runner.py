"""
Shared runner helpers for the LangGraph + Memanto example scripts.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from graph import build_support_graph
from memory_backend import LocalJsonMemoryBackend, MemantoMemoryBackend, MemoryBackend


DEFAULT_AGENT_ID = "langgraph-memanto-support"


def build_memory_backend() -> MemoryBackend:
    """Create the configured memory backend."""

    load_dotenv()

    agent_id = os.environ.get("MEMANTO_AGENT_ID", DEFAULT_AGENT_ID)
    offline_demo = os.environ.get("MEMANTO_OFFLINE_DEMO") == "1"

    if offline_demo:
        return LocalJsonMemoryBackend(Path(".langgraph-memanto-demo.json"))

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        raise SystemExit(
            "MOORCHEH_API_KEY is required for the Memanto demo. "
            "Copy .env.example to .env and fill it in, or set "
            "MEMANTO_OFFLINE_DEMO=1 for a local graph-only smoke test."
        )

    return MemantoMemoryBackend(api_key=api_key, agent_id=agent_id)


def run_message(title: str, message: str) -> dict:
    """Run one graph invocation with a fresh memory backend session."""

    memory = build_memory_backend()
    memory.setup()

    try:
        graph = build_support_graph(memory)
        result = graph.invoke({"user_message": message})
        stored_ids = result.get("stored_memory_ids", [])
        if stored_ids:
            memory.wait_until_indexed(
                query=message,
                minimum_count=len(stored_ids),
            )
    finally:
        memory.close()

    print(title)
    print("=" * len(title))
    print(f"User message: {message}\n")
    print(result["response"])
    return result
