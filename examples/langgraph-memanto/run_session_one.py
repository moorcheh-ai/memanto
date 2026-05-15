from __future__ import annotations

import argparse

from memory_adapter import build_memory_adapter
from support_graph import build_support_graph


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    graph = build_support_graph(build_memory_adapter(offline=args.offline))
    result = graph.invoke(
        {
            "user_message": (
                "I am Sam. Please keep replies concise. I am migrating billing "
                "alerts by Friday."
            ),
            "recalled_memories": [],
            "answer": "",
        }
    )
    print(result["answer"])
    print("\nStored session-one memories in Memanto.")


if __name__ == "__main__":
    main()
