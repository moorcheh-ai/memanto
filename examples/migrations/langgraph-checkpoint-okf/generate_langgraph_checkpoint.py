"""Generate a real LangGraph SQLite checkpoint for the OKF migration showcase.

The graph is intentionally deterministic: it uses LangGraph, LangChain message
objects, and SqliteSaver, but no hosted LLM. That keeps the source data genuine
and reproducible without requiring API keys.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


THREAD_ID = "founder-os-agent"


def append_list(left: list[dict] | None, right: list[dict] | None) -> list[dict]:
    return (left or []) + (right or [])


class MemoryState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    memories: Annotated[list[dict], append_list]


SCENARIO = [
    {
        "session": "s01_foundation",
        "user": (
            "I prefer concise executive summaries and dislike fluffy progress "
            "updates. For internal dashboards, use dark mode with teal accents."
        ),
        "assistant": "Saved your communication and internal dashboard preferences.",
        "memory": {
            "id": "lg-mem-001",
            "type": "preference",
            "title": "Concise executive summaries",
            "content": (
                "The user prefers concise executive summaries and wants progress "
                "updates to avoid fluff."
            ),
            "tags": ["communication", "style"],
            "confidence": 0.95,
            "timestamp": "2026-07-27T09:15:00Z",
        },
    },
    {
        "session": "s01_foundation",
        "user": (
            "Store another preference: customer-facing tools should feel calm, "
            "light, and work-focused. Do not copy my internal dark dashboard taste."
        ),
        "assistant": "Saved the customer-facing UI distinction.",
        "memory": {
            "id": "lg-mem-002",
            "type": "preference",
            "title": "Customer-facing UI should be calm and light",
            "content": (
                "Customer-facing tools should use a calm, light, work-focused UI. "
                "Do not apply the user's internal dark-dashboard preference to "
                "customer-facing products."
            ),
            "tags": ["product", "design"],
            "confidence": 0.97,
            "timestamp": "2026-07-27T09:22:00Z",
        },
    },
    {
        "session": "s02_launch",
        "user": (
            "Our launch goal is an investor memo by 2026-08-07. The memo must "
            "include traction, burn, risks, and a one-page ask."
        ),
        "assistant": "Saved the investor memo goal and required sections.",
        "memory": {
            "id": "lg-mem-003",
            "type": "goal",
            "title": "Investor memo due 2026-08-07",
            "content": (
                "Prepare an investor memo by 2026-08-07 with traction, burn, "
                "risks, and a one-page ask."
            ),
            "tags": ["fundraising", "deadline"],
            "confidence": 0.96,
            "timestamp": "2026-07-28T14:05:00Z",
        },
    },
    {
        "session": "s02_launch",
        "user": (
            "Decision: use Moorcheh as retrieval backend for the agent memory "
            "prototype after the zero-indexing latency test beat vector search."
        ),
        "assistant": "Saved the retrieval backend decision and rationale.",
        "memory": {
            "id": "lg-mem-004",
            "type": "decision",
            "title": "Use Moorcheh for retrieval",
            "content": (
                "Use Moorcheh as the retrieval backend for the agent memory "
                "prototype because the zero-indexing latency test beat vector "
                "search."
            ),
            "tags": ["architecture", "retrieval"],
            "confidence": 0.93,
            "timestamp": "2026-07-28T14:31:00Z",
        },
    },
    {
        "session": "s03_growth",
        "user": (
            "For onboarding emails, avoid exclamation marks. The tone should be "
            "direct, helpful, and calm."
        ),
        "assistant": "Saved the onboarding email tone instruction.",
        "memory": {
            "id": "lg-mem-005",
            "type": "instruction",
            "title": "Onboarding email tone",
            "content": (
                "Onboarding emails should avoid exclamation marks and use a "
                "direct, helpful, calm tone."
            ),
            "tags": ["growth", "email"],
            "confidence": 0.94,
            "timestamp": "2026-07-29T16:40:00Z",
        },
    },
]


MEMORY_BY_PROMPT = {item["user"]: item for item in SCENARIO}


def display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def capture_memory(state: MemoryState) -> MemoryState:
    last_message = state["messages"][-1]
    content = str(getattr(last_message, "content", ""))
    scenario_item = MEMORY_BY_PROMPT[content]

    memory = dict(scenario_item["memory"])
    memory["source_session"] = scenario_item["session"]
    memory["evidence_prompt"] = content

    return {
        "messages": [AIMessage(content=scenario_item["assistant"])],
        "memories": [memory],
    }


def build_graph():
    graph = StateGraph(MemoryState)
    graph.add_node("capture_memory", capture_memory)
    graph.add_edge(START, "capture_memory")
    graph.add_edge("capture_memory", END)
    return graph


def generate_checkpoint(output: Path, transcript_path: Path | None = None) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    conn = sqlite3.connect(output, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    app = build_graph().compile(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": THREAD_ID}}
    transcript = []

    try:
        for item in SCENARIO:
            result = app.invoke(
                {"messages": [HumanMessage(content=item["user"])]},
                config=config,
            )
            transcript.append(
                {
                    "session": item["session"],
                    "user": item["user"],
                    "assistant": item["assistant"],
                    "memory_id": item["memory"]["id"],
                    "checkpoint_memories": len(result.get("memories", [])),
                }
            )
    finally:
        conn.close()

    summary = {
        "thread_id": THREAD_ID,
        "source": "langgraph-checkpoint-sqlite",
        "database": display_path(output),
        "turns": len(SCENARIO),
        "memories": len(SCENARIO),
    }

    if transcript_path is not None:
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(
            json.dumps(
                {"summary": summary, "transcript": transcript},
                indent=2,
                ensure_ascii=True,
            )
            + "\n",
            encoding="utf-8",
        )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("sample_output/source/langgraph_memory.sqlite"),
    )
    parser.add_argument(
        "--transcript",
        type=Path,
        default=Path("sample_output/source/transcript.json"),
    )
    args = parser.parse_args()

    summary = generate_checkpoint(args.output, args.transcript)
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
