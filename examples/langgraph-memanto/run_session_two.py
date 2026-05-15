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
            "user_message": "What should I focus on for Sam's billing support follow-up?",
            "recalled_memories": [],
            "answer": "",
        }
    )
    print(result["answer"])


if __name__ == "__main__":
    main()
