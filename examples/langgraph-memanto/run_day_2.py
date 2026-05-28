import os
import sys

from graph import MemantoMemory, build_graph


def main() -> None:
    if not os.environ.get("MOORCHEH_API_KEY"):
        print("Error: MOORCHEH_API_KEY is not set. Copy .env.example to .env first.")
        sys.exit(1)

    memory = MemantoMemory.from_env()
    app = build_graph(memory)

    result = app.invoke(
        {
            "prompt": "Which storage backend should I use for audit logs?",
            "recalled_context": "",
            "answer": "",
            "memory_to_store": "",
        }
    )

    print("Day 2 fresh run. Recalled answer:")
    print(result["answer"])


if __name__ == "__main__":
    main()
