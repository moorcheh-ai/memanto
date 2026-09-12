"""Seed a genuinely lived-in LangGraph agent and persist its memory to a real
SQLite checkpoint store.

This runs an actual LangGraph StateGraph (no LLM required: extraction is a
deterministic rule-based node, which keeps the whole demo reproducible with
zero API keys). The agent plays a travel-planner that accumulates user
memories across multiple sessions and threads — preferences, corrections, a
resolved contradiction — and every turn is checkpointed by LangGraph's
SqliteSaver into ``checkpoints.sqlite``.

Run:  python seed_agent.py            # writes checkpoints.sqlite
      python seed_agent.py --force    # rebuild from scratch
"""

from __future__ import annotations

import argparse
import operator
import os
import re
from datetime import datetime, timezone
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

DB_PATH = os.path.join(os.path.dirname(__file__), "checkpoints.sqlite")

# A lived-in history for "Alex", spread over five sessions on the main travel
# thread plus a separate company-policy thread — so the migration must handle
# multiple threads, corrections, and a resolved contradiction.
SCRIPT: dict[str, list[str]] = {
    "alex-travel": [
        "Hi, I'm Alex Rivera. I always fly aisle seat, and my home airport is SFO.",
        "For hotels, keep it under $250 a night, and I prefer boutique hotels over chains.",
        "I'm vegetarian, so plan restaurants accordingly.",
        "Update: I started eating meat again last month — drop the vegetarian constraint.",
        "My United MileagePlus number is 8842-1190. And to be clear: aisle over window, always.",
    ],
    "alex-work-policy": [
        "Work policy reminder: book only refundable fares for business trips.",
        "Finance needs all receipts submitted within 48 hours of trip end.",
    ],
}

# Deterministic "extraction" rules: (kind, pattern, formatter). The same job an
# LLM extractor would do, but offline and reproducible.
RULES: list[tuple[str, str, str]] = [
    ("fact", r"I'm ([A-Z][a-z]+ [A-Z][a-z]+)", "User name is {0}."),
    ("preference", r"always fly aisle seat", "User prefers aisle seat when flying."),
    ("fact", r"home airport is ([A-Z]{3})", "User home airport is {0}."),
    ("preference", r"under \$(\d+) a night", "Hotel budget is under ${0} per night."),
    (
        "preference",
        r"prefer boutique hotels over chains",
        "User prefers boutique hotels over chains.",
    ),
    (
        "constraint",
        r"I'm vegetarian",
        "User is vegetarian (plan restaurants accordingly).",
    ),
    (
        "decision",
        r"started eating meat again",
        "User resolved diet change: no longer vegetarian — remove the vegetarian constraint.",
    ),
    (
        "fact",
        r"MileagePlus number is ([\d-]+)",
        "User United MileagePlus number is {0}.",
    ),
    (
        "preference",
        r"aisle over window, always",
        "Confirmed seating preference: aisle over window, always.",
    ),
    (
        "constraint",
        r"only refundable fares",
        "Work travel policy: book only refundable fares.",
    ),
    (
        "commitment",
        r"receipts submitted within 48 hours",
        "Finance requires receipts within 48 hours of trip end.",
    ),
]


class AgentState(TypedDict):
    messages: Annotated[list[dict[str, str]], operator.add]
    memories: Annotated[list[dict[str, Any]], operator.add]
    turns: Annotated[list[int], operator.add]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def remember(state: AgentState) -> dict[str, Any]:
    """Rule-based memory extraction from the latest user message."""
    text = state["messages"][-1]["content"]
    turn_no = sum(state.get("turns", [])) + 1
    found: list[dict[str, Any]] = []
    for kind, pattern, fmt in RULES:
        m = re.search(pattern, text)
        if m:
            found.append(
                {
                    "kind": kind,
                    "text": fmt.format(*m.groups()) if m.groups() else fmt,
                    "rule": pattern,
                    "ts": _now(),
                    "turn": turn_no,
                }
            )
    ack = ("Noted: " + "; ".join(f["text"] for f in found)) if found else "Noted."
    return {
        "messages": [{"role": "assistant", "content": ack}],
        "memories": found,
        "turns": [1],
    }


def build_graph(checkpointer: SqliteSaver):
    g = StateGraph(AgentState)
    g.add_node("remember", remember)
    g.set_entry_point("remember")
    g.add_edge("remember", END)
    return g.compile(checkpointer=checkpointer)


def seed(force: bool = False) -> None:
    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    if os.path.exists(DB_PATH):
        print(f"checkpoint store already exists: {DB_PATH} (use --force to rebuild)")
        return

    with SqliteSaver.from_conn_string(DB_PATH) as saver:
        app = build_graph(saver)
        for thread_id, turns in SCRIPT.items():
            config = {"configurable": {"thread_id": thread_id}}
            for turn_text in turns:
                app.invoke(
                    {"messages": [{"role": "user", "content": turn_text}]},
                    config=config,
                )
                print(f"  [{thread_id}] {turn_text[:60]}")
    print(
        f"\nSeeded {sum(len(v) for v in SCRIPT.values())} turns across "
        f"{len(SCRIPT)} threads -> {DB_PATH}"
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    seed(force=args.force)
