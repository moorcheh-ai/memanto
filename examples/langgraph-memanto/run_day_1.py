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

    decision = (
        "For the customer support assistant, store audit logs in PostgreSQL "
        "because compliance needs SQL retention policies and easy exports."
    )

    try:
        result = app.invoke(
            {
                "prompt": "Remember the storage decision for audit logs.",
                "recalled_context": "",
                "answer": "",
                "memory_to_store": decision,
            }
        )
    except Exception as exc:
        print(f"Error running Day 1 demo: {exc}")
        sys.exit(1)

    print("Day 1 complete. Stored decision:")
    print(decision)
    print()
    print(result["answer"])


if __name__ == "__main__":
    main()
