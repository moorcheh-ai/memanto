#!/usr/bin/env python3
"""Run a LangGraph support workflow that recalls long-term Memanto memories."""

from __future__ import annotations

from typing import TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from memory_client import (
    build_client,
    ensure_active_agent,
    format_recalled_memories,
    get_agent_id,
)

SUPPORT_REQUEST = (
    "Can you update me on the billing migration and keep the answer short?"
)


class SupportState(TypedDict):
    request: str
    recalled_memories: list[str]
    draft_response: str


def retrieve_memory(state: SupportState) -> SupportState:
    client = build_client()
    agent_id = get_agent_id()
    ensure_active_agent(
        client,
        agent_id,
        description="LangGraph customer support demo with persistent Memanto memory",
    )

    result = client.recall(
        agent_id=agent_id,
        query=state["request"],
        limit=5,
        type=["preference", "fact", "commitment"],
    )

    return {
        **state,
        "recalled_memories": format_recalled_memories(result.get("memories", [])),
    }


def draft_response(state: SupportState) -> SupportState:
    memory_text = "\n".join(f"- {memory}" for memory in state["recalled_memories"])
    if not memory_text:
        memory_text = "- No relevant long-term memories were found."

    response = (
        "Here is the short update:\n"
        "- The billing migration is still the active follow-up item.\n"
        "- I will keep tracking it and follow up when it completes.\n"
        "- I kept this concise because your saved preference asks for short, "
        "bullet-point replies.\n\n"
        "Memanto context used:\n"
        f"{memory_text}"
    )

    return {**state, "draft_response": response}


def build_graph():
    graph = StateGraph(SupportState)
    graph.add_node("retrieve_memory", retrieve_memory)
    graph.add_node("draft_response", draft_response)
    graph.set_entry_point("retrieve_memory")
    graph.add_edge("retrieve_memory", "draft_response")
    graph.add_edge("draft_response", END)
    return graph.compile()


def main() -> None:
    load_dotenv()

    app = build_graph()
    result = app.invoke(
        {
            "request": SUPPORT_REQUEST,
            "recalled_memories": [],
            "draft_response": "",
        }
    )

    print("Current LangGraph request:")
    print(f"- {result['request']}\n")

    print("Recalled long-term memories:")
    for memory in result["recalled_memories"]:
        print(f"- {memory}")

    print("\nDraft response:")
    print(result["draft_response"])


if __name__ == "__main__":
    main()
