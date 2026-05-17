from __future__ import annotations

import argparse
import os
import shutil
import textwrap
from pathlib import Path
from typing import Any

from graph import build_recruiting_graph
from memory_store import build_memory_store

EXAMPLE_DIR = Path(__file__).resolve().parent
DEFAULT_LOCAL_DB = EXAMPLE_DIR / ".local" / "recruiting_memories.json"

DAY_ONE_THREAD = "intake-2026-05-17"
DAY_TWO_THREAD = "briefing-2026-05-18"

DAY_ONE_MESSAGE = (
    "Record this from yesterday: Candidate Maya Chen is interviewing for "
    "Staff AI Platform. She prefers concise technical deep-dives, is "
    "available after 14:00 UTC, and we promised a take-home by Friday."
)
DAY_TWO_MESSAGE = (
    "I have a new LangGraph thread with no notes in state. Prepare my "
    "reminder for today's Maya interview."
)


def run_two_session_demo(
    *,
    backend: str,
    agent_id: str,
    local_db: Path,
    reset_local: bool = False,
) -> dict[str, Any]:
    if backend == "local" and reset_local and local_db.parent.exists():
        shutil.rmtree(local_db.parent)

    store = build_memory_store(backend, agent_id=agent_id, local_path=local_db)
    store.setup()
    graph = build_recruiting_graph(store)

    try:
        session_one = graph.invoke(
            {
                "thread_id": DAY_ONE_THREAD,
                "user_message": DAY_ONE_MESSAGE,
            },
            config={"configurable": {"thread_id": DAY_ONE_THREAD}},
        )
        session_two = graph.invoke(
            {
                "thread_id": DAY_TWO_THREAD,
                "user_message": DAY_TWO_MESSAGE,
            },
            config={"configurable": {"thread_id": DAY_TWO_THREAD}},
        )
    finally:
        store.close()

    return {
        "backend": backend,
        "agent_id": agent_id,
        "session_one": session_one,
        "session_two": session_two,
    }


def main() -> None:
    _load_dotenv(EXAMPLE_DIR / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend",
        choices=["local", "memanto"],
        default="local",
        help="Use 'memanto' for the live SDK backend or 'local' for no secrets.",
    )
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("MEMANTO_AGENT_ID", "langgraph-recruiting-memory"),
    )
    parser.add_argument("--local-db", type=Path, default=DEFAULT_LOCAL_DB)
    parser.add_argument("--reset-local", action="store_true")
    args = parser.parse_args()

    result = run_two_session_demo(
        backend=args.backend,
        agent_id=args.agent_id,
        local_db=args.local_db,
        reset_local=args.reset_local,
    )
    print_demo(result)


def print_demo(result: dict[str, Any]) -> None:
    one = result["session_one"]
    two = result["session_two"]

    print("LangGraph + Memanto cross-session recall demo")
    print(f"Backend: {result['backend']}")
    print(f"Memanto agent id: {result['agent_id']}")
    print()

    print(f"SESSION 1 - yesterday, thread_id={DAY_ONE_THREAD}")
    print(_wrap("User", DAY_ONE_MESSAGE))
    print(_wrap("Agent", one["answer"]))
    print(f"Stored memories: {len(one.get('stored_memories', []))}")
    print()

    print(f"SESSION 2 - today, thread_id={DAY_TWO_THREAD}")
    print(_wrap("User", DAY_TWO_MESSAGE))
    print(_wrap("Agent", two["answer"]))
    print(f"Recalled memories: {len(two.get('recalled_memories', []))}")
    print()

    print("Proof")
    print(f"- Different LangGraph thread ids: {DAY_ONE_THREAD} != {DAY_TWO_THREAD}")
    print("- Session 2 did not include Maya's role, style, time, or commitment.")
    print("- Those details came from the long-term memory backend.")


def _wrap(label: str, value: str) -> str:
    rendered = []
    first_line = True
    for line in value.splitlines():
        prefix = f"{label}: " if first_line else "  "
        rendered.append(
            textwrap.fill(
                line,
                width=78,
                initial_indent=prefix,
                subsequent_indent="  ",
            )
        )
        first_line = False
    return "\n".join(rendered)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if __name__ == "__main__":
    main()
