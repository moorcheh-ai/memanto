"""Generate a real multi-thread LangGraph SqliteSaver database for the demo."""

from __future__ import annotations

import argparse
import operator
import sqlite3
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import NotRequired


class DemoState(TypedDict):
    messages: Annotated[list[Any], add_messages]
    profile: dict[str, str]
    preferences: dict[str, str]
    facts: Annotated[list[str], operator.add]
    decisions: Annotated[list[dict[str, str]], operator.add]
    event: NotRequired[dict[str, Any]]


def _remember(state: DemoState) -> dict[str, Any]:
    event = state.get("event") or {}
    profile = dict(state.get("profile") or {})
    profile.update(event.get("profile") or {})
    preferences = dict(state.get("preferences") or {})
    preferences.update(event.get("preferences") or {})

    reply = event.get("reply") or "I saved that context in this thread."
    return {
        "profile": profile,
        "preferences": preferences,
        "facts": list(event.get("facts") or []),
        "decisions": list(event.get("decisions") or []),
        "messages": [AIMessage(content=reply)],
    }


def _build_graph(checkpointer: SqliteSaver):
    builder = StateGraph(DemoState)
    builder.add_node("remember", _remember)
    builder.add_edge(START, "remember")
    builder.add_edge("remember", END)
    return builder.compile(checkpointer=checkpointer)


DEMO_THREADS: dict[str, list[dict[str, Any]]] = {
    "mira-travel": [
        {
            "prompt": "I live in Shanghai and eat vegetarian food.",
            "profile": {"home_city": "Shanghai"},
            "preferences": {"diet": "vegetarian"},
            "reply": "I will plan from Shanghai and keep meals vegetarian.",
        },
        {
            "prompt": "For flights I usually choose an aisle seat.",
            "preferences": {"flight_seat": "aisle"},
            "reply": "I noted your aisle-seat preference.",
        },
        {
            "prompt": "Correction: I now prefer a window seat on flights.",
            "preferences": {"flight_seat": "window"},
            "reply": "Updated: window seat replaces the earlier aisle preference.",
        },
        {
            "prompt": "Book the Kyoto research trip for October.",
            "decisions": [
                {
                    "decision": "Kyoto research trip",
                    "date": "October 2026",
                    "status": "approved",
                }
            ],
            "facts": ["Kyoto trip research should prioritize rail-accessible areas."],
            "reply": "The Kyoto research trip is approved for October 2026.",
        },
    ],
    "mira-work": [
        {
            "prompt": "The Atlas service runs PostgreSQL 16.",
            "facts": ["Atlas uses PostgreSQL 16."],
            "reply": "Saved the Atlas database version.",
        },
        {
            "prompt": "Keep project updates concise and lead with blockers.",
            "preferences": {"status_updates": "concise, blockers first"},
            "reply": "Future status updates will lead with blockers and stay concise.",
        },
        {
            "prompt": "We decided to release Atlas on Friday after the migration test.",
            "decisions": [
                {
                    "decision": "Release Atlas on Friday",
                    "condition": "migration test passes",
                }
            ],
            "reply": "Release timing and its migration-test gate are recorded.",
        },
        {
            "prompt": "The on-call owner for launch week is Priya.",
            "facts": ["Priya owns on-call coverage for Atlas launch week."],
            "reply": "Priya is recorded as launch-week on-call owner.",
        },
    ],
    "mira-learning": [
        {
            "prompt": "I learn best from runnable examples before theory.",
            "preferences": {"learning_style": "runnable examples before theory"},
            "reply": "I will start technical explanations with runnable examples.",
        },
        {
            "prompt": "I am studying Rust ownership and async cancellation.",
            "facts": ["Current study topics: Rust ownership and async cancellation."],
            "reply": "Saved both Rust study topics.",
        },
        {
            "prompt": "Use 25-minute focused sessions for this study plan.",
            "preferences": {"study_session": "25 minutes"},
            "reply": "The study plan will use 25-minute focused sessions.",
        },
    ],
}


def generate_database(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing checkpoint database: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(output, check_same_thread=False)
    saver = SqliteSaver(conn)
    try:
        graph = _build_graph(saver)
        for thread_id, turns in DEMO_THREADS.items():
            config = {"configurable": {"thread_id": thread_id}}
            for turn in turns:
                graph.invoke(
                    {
                        "messages": [HumanMessage(content=turn["prompt"])],
                        "event": {
                            key: value for key, value in turn.items() if key != "prompt"
                        },
                    },
                    config=config,
                )
        conn.commit()
    finally:
        conn.close()
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path("artifacts/demo-checkpoints.sqlite"),
    )
    args = parser.parse_args()
    database = generate_database(args.output)
    print(f"Generated {len(DEMO_THREADS)} real LangGraph threads at {database}")


if __name__ == "__main__":
    main()
