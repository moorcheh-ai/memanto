from __future__ import annotations

import argparse

from langgraph_memanto import (
    DEFAULT_AGENT_ID,
    LocalJsonMemoryBackend,
    backend_from_name,
    run_two_session_demo,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the LangGraph + Memanto cross-session memory demo."
    )
    parser.add_argument(
        "--backend",
        choices=["local", "memanto"],
        default="local",
        help="Use local JSON storage or live Memanto.",
    )
    parser.add_argument(
        "--agent-id",
        default=DEFAULT_AGENT_ID,
        help="Memanto agent id for the live backend.",
    )
    parser.add_argument(
        "--reset-local",
        action="store_true",
        help="Delete the local JSON store before running.",
    )
    args = parser.parse_args()

    backend = backend_from_name(args.backend, agent_id=args.agent_id)
    if args.reset_local and isinstance(backend, LocalJsonMemoryBackend):
        backend.reset()

    result = run_two_session_demo(backend)
    session_1 = result["session_1"]
    session_2 = result["session_2"]

    print("Session 1 wrote memory ids:")
    for memory_id in session_1.get("written_memories", []):
        print(f"- {memory_id}")

    print("\nSession 2 recalled:")
    for memory in session_2.get("recalled_memories", []):
        print(f"- {memory.content}")

    print("\nSession 2 response:")
    print(session_2["response"])


if __name__ == "__main__":
    main()
