"""Day 1: seed Memanto with customer facts from one LangGraph session."""

from __future__ import annotations

from memanto_memory import MemantoMemory


CUSTOMER_ID = "customer-aurora"


def main() -> None:
    memory = MemantoMemory.from_env()
    memory.connect()

    try:
        memory_ids = [
            memory.remember(
                title=f"{CUSTOMER_ID} timezone",
                content="Customer Aurora works in Europe/Amsterdam time.",
                memory_type="fact",
                confidence=1.0,
                tags=["langgraph", "support", CUSTOMER_ID],
            ),
            memory.remember(
                title=f"{CUSTOMER_ID} communication preference",
                content=(
                    "Customer Aurora prefers concise answers with a clear next "
                    "step and dislikes long setup walkthroughs."
                ),
                memory_type="preference",
                confidence=0.95,
                tags=["langgraph", "support", CUSTOMER_ID],
            ),
            memory.remember(
                title=f"{CUSTOMER_ID} export commitment",
                content=(
                    "Support promised to help Customer Aurora enable nightly CSV "
                    "exports after 18:00 CET."
                ),
                memory_type="commitment",
                confidence=0.9,
                tags=["langgraph", "support", CUSTOMER_ID],
            ),
        ]
        print("Stored Day 1 memories in Memanto:")
        for memory_id in memory_ids:
            print(f"- {memory_id}")
    finally:
        memory.close()


if __name__ == "__main__":
    main()
