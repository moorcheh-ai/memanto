"""Run a two-session LangGraph + Memanto memory demo.

The demo works without API keys by default:

    python demo.py

To use real Memanto memory, install/configure the CLI and run:

    MEMANTO_LANGGRAPH_BACKEND=cli python demo.py
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

from langgraph_memanto import MemantoGraphMemory, make_backend_from_env


STORE_PATH = Path(__file__).with_name(".demo-memory.jsonl")

warnings.simplefilter("ignore")
warnings.showwarning = lambda *args, **kwargs: None
warnings.filterwarnings("ignore", message=r".*urllib3.*doesn't match.*")
warnings.filterwarnings("ignore", message=r".*allowed_objects.*")


def planner_node(state: dict[str, Any]) -> dict[str, Any]:
    """Plan a payment milestone and emit memories worth persisting."""
    context = state.get("memanto_context") or "No durable memory recalled yet."
    print("Planner received memory context:")
    print(context)
    return {
        "messages": [
            {
                "role": "assistant",
                "content": (
                    "Decision: Use Stripe Checkout for Project Apollo because the "
                    "team wants the fastest PCI-light payment path.\n"
                    "Preference: Project Apollo status updates should be concise."
                ),
            }
        ],
        "decisions": [
            {
                "content": (
                    "Project Apollo uses Stripe Checkout for the first payment "
                    "milestone."
                ),
                "type": "decision",
                "tags": ["project-apollo", "payments"],
            }
        ],
    }


def answer_node(state: dict[str, Any]) -> dict[str, Any]:
    """Print an answer that uses recalled memory context."""
    context = state.get("memanto_context") or "No durable memory found."
    answer = "Recovered long-term context:\n" + context
    print(answer)
    return {"answer": answer}


def run_without_langgraph(memory: MemantoGraphMemory) -> dict[str, Any]:
    """Fallback runner that mirrors the LangGraph node sequence."""

    print("\n=== Session 1: plan and store memories ===")
    session_one = {
        "messages": [
            {
                "role": "user",
                "content": "Plan the Project Apollo payment milestone.",
            }
        ]
    }
    hydrated = memory.inject_context(session_one)
    planner_result = planner_node(hydrated)
    saved = memory.remember_node(planner_result)
    print(f"Saved memories: {saved['memanto_saved']}")

    print("\n=== Session 2: new graph run recalls the old decision ===")
    session_two = {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Before coding checkout, what do we remember about Project "
                    "Apollo payments?"
                ),
            }
        ]
    }
    recall_result = memory.recall_node(session_two)
    hydrated = {**session_two, **recall_result}
    return answer_node(hydrated)


def run_with_langgraph(memory: MemantoGraphMemory) -> dict[str, Any]:
    """Run the same flow through LangGraph when it is installed."""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langgraph.graph import END, START, StateGraph

    builder = StateGraph(dict)
    builder.add_node("recall_memory", memory.recall_node)
    builder.add_node("answer", answer_node)
    builder.add_edge(START, "recall_memory")
    builder.add_edge("recall_memory", "answer")
    builder.add_edge("answer", END)
    recall_graph = builder.compile()

    print("\n=== Session 1: plan and store memories ===")
    memory.wrap_node(planner_node, node_name="planner")(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Plan the Project Apollo payment milestone.",
                }
            ]
        }
    )

    print("\n=== Session 2: LangGraph recalls the old decision ===")
    return recall_graph.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Before coding checkout, what do we remember about Project "
                        "Apollo payments?"
                    ),
                }
            ]
        }
    )


def main() -> None:
    """Select a backend and run the two-session demo."""
    if os.getenv("MEMANTO_LANGGRAPH_BACKEND", "local").strip().lower() != "cli":
        STORE_PATH.unlink(missing_ok=True)

    backend = make_backend_from_env(local_path=STORE_PATH)
    memory = MemantoGraphMemory(backend=backend, recall_limit=4)

    try:
        run_with_langgraph(memory)
    except ImportError:
        run_without_langgraph(memory)


if __name__ == "__main__":
    main()
