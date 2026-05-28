import os
import sys

from graph import MemantoMemory, build_graph


def main() -> None:
    if not os.environ.get("MOORCHEH_API_KEY"):
        print("Error: MOORCHEH_API_KEY is not set. Copy .env.example to .env first.")
        sys.exit(1)

    memory = MemantoMemory.from_env()
    app = build_graph(memory)

    decision = (
        "For the customer support assistant, store audit logs in PostgreSQL "
        "because compliance needs SQL retention policies and easy exports."
    )

    result = app.invoke(
        {
            "prompt": "Remember the storage decision for audit logs.",
            "recalled_context": "",
            "answer": "",
            "memory_to_store": decision,
        }
    )

    print("Day 1 complete. Stored decision:")
    print(decision)
    print()
    print(result["answer"])


if __name__ == "__main__":
    main()
