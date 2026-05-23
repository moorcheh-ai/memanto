#!/usr/bin/env python3
"""
Run 1: store customer preferences in Memanto.

Run this today, then run `run_recall_memory.py` in a separate terminal later.
The second run does not receive these facts in LangGraph state; it recalls them
from Memanto.
"""

from __future__ import annotations

from dotenv import load_dotenv

from memory_tools import MemantoMemory


def main() -> None:
    load_dotenv()

    memory = MemantoMemory.from_env()
    memory.ensure_agent()

    memories = [
        "Customer ACME prefers short support answers with bullet points.",
        "Customer ACME works in CET and wants deployment alerts before 09:00.",
        "Customer ACME wants alert setup steps without background explanation.",
    ]

    for item in memories:
        result = memory.remember(
            item,
            memory_type="preference",
            tags="langgraph,customer-support,acme",
        )
        print(result)

    print("\nStored customer preferences. Run `python run_recall_memory.py` next.")


if __name__ == "__main__":
    main()
