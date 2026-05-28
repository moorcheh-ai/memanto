import os
import sys

from graph import MemantoMemory, build_graph


def main() -> None:
    if not os.environ.get("MOORCHEH_API_KEY"):
        print("Error: MOORCHEH_API_KEY is not set. Copy .env.example to .env first.")
        sys.exit(1)

    try:
        memory = MemantoMemory.from_env()
        app = build_graph(memory)
    except Exception as exc:
        print(f"Error initializing Memanto memory: {exc}")
        sys.exit(1)

    try:
        result = app.invoke(
            {
                "prompt": "Which storage backend should I use for audit logs?",
                "recalled_context": "",
                "answer": "",
                "memory_to_store": "",
            }
        )
    except Exception as exc:
        print(f"Error running Day 2 demo: {exc}")
        print("Tip: run python run_day_1.py first so Memanto has a decision to recall.")
        sys.exit(1)

    print("Day 2 fresh run. Recalled answer:")
    print(result["answer"])


if __name__ == "__main__":
    main()
