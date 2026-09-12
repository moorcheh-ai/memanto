"""Generate a real, deterministic LangGraph checkpoint database.

No LLM or API key is used. The graph still runs normally through LangGraph and
persists every turn with SqliteSaver, which makes the resulting source data a
real checkpoint history rather than a hand-written export fixture.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


def merge_mapping(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    return {**(left or {}), **(right or {})}


def append_unique(left: list[str], right: list[str]) -> list[str]:
    return list(dict.fromkeys([*(left or []), *(right or [])]))


class MemoryState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    profile: Annotated[dict[str, str], merge_mapping]
    decisions: Annotated[list[str], append_unique]
    facts: Annotated[list[str], append_unique]
    goals: Annotated[list[str], append_unique]


def acknowledge(state: MemoryState) -> dict[str, Any]:
    latest = state.get("messages", [])[-1]
    text = latest.content if isinstance(latest.content, str) else "memory update"
    return {"messages": [AIMessage(content=f"Saved: {text}")]}


SESSIONS: dict[str, list[dict[str, Any]]] = {
    "product-launch": [
        {
            "message": "I prefer launch reports as PDF files.",
            "profile": {"report_format_preference": "PDF"},
        },
        {
            "message": "Correction: use Markdown for launch reports, not PDF.",
            "profile": {"report_format_preference": "Markdown"},
        },
        {
            "message": "We decided to ship the Atlas release on September 14.",
            "decisions": ["Ship the Atlas release on September 14."],
        },
        {
            "message": "Maya Chen owns the Atlas launch.",
            "facts": ["Maya Chen owns the Atlas launch."],
        },
    ],
    "travel-planning": [
        {
            "message": "For work trips, I prefer trains for journeys under four hours.",
            "profile": {
                "short_trip_preference": "Train when travel is under four hours"
            },
        },
        {
            "message": "My next work trip is to Lyon for the October planning workshop.",
            "facts": [
                "The next work trip is to Lyon for the October planning workshop."
            ],
        },
        {
            "message": "The goal is to keep the Lyon trip below 450 euros.",
            "goals": ["Keep the Lyon work trip below 450 euros."],
        },
    ],
}


def generate_database(path: str | Path) -> Path:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)

    conn = sqlite3.connect(destination, check_same_thread=False)
    try:
        saver = SqliteSaver(conn)
        builder = StateGraph(MemoryState)
        builder.add_node("remember", acknowledge)
        builder.add_edge(START, "remember")
        builder.add_edge("remember", END)
        graph = builder.compile(checkpointer=saver)

        for thread_id, turns in SESSIONS.items():
            config = {"configurable": {"thread_id": thread_id}}
            for turn in turns:
                payload: dict[str, Any] = {
                    "messages": [HumanMessage(content=turn["message"])]
                }
                for channel in ("profile", "decisions", "facts", "goals"):
                    if channel in turn:
                        payload[channel] = turn[channel]
                graph.invoke(payload, config)
    finally:
        conn.close()
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path("artifacts/langgraph-checkpoints.sqlite"),
    )
    args = parser.parse_args()
    print(generate_database(args.output))


if __name__ == "__main__":
    main()
