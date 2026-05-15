#!/usr/bin/env python3
"""
LangGraph + Memanto long-term memory demo.

Run 1 stores customer-support context in Memanto.
Run 2 starts a fresh LangGraph thread and recalls that context before replying.
"""

from __future__ import annotations

import os
import sys
from typing import Any, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient

AGENT_ID = "langgraph-support-memory"
CUSTOMER_ID = "acme-studio"


class SupportState(TypedDict, total=False):
    customer_id: str
    user_message: str
    stored_memory_ids: list[str]
    recalled_memories: list[dict[str, Any]]
    response: str


def ensure_agent(client: SdkClient, agent_id: str) -> None:
    """Create the demo agent if it is not already registered."""
    try:
        client.create_agent(
            agent_id=agent_id,
            pattern="support",
            description="LangGraph support assistant with Memanto long-term memory",
        )
    except AgentAlreadyExistsError:
        pass


def setup_memanto() -> SdkClient:
    """Load credentials, create the demo agent, and activate a session."""
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print("Error: MOORCHEH_API_KEY is not set. Copy .env.example to .env.")
        sys.exit(1)

    client = SdkClient(api_key)
    ensure_agent(client, AGENT_ID)
    client.activate_agent(AGENT_ID)
    return client


def remember_customer_context(client: SdkClient):
    """Return a graph node that writes durable memories into Memanto."""

    def node(state: SupportState) -> SupportState:
        customer_id = state["customer_id"]
        memories = [
            {
                "memory_type": "preference",
                "title": "Acme Studio Tone Preference",
                "content": (
                    f"{customer_id} prefers short, direct support replies with "
                    "explicit next steps and no marketing language."
                ),
                "confidence": 0.93,
                "tags": ["langgraph-demo", customer_id, "support-style"],
                "source": "langgraph-intake",
                "provenance": "explicit_statement",
            },
            {
                "memory_type": "fact",
                "title": "Acme Studio Plan",
                "content": f"{customer_id} is on the Pro plan and uses webhooks.",
                "confidence": 0.9,
                "tags": ["langgraph-demo", customer_id, "account"],
                "source": "langgraph-intake",
                "provenance": "explicit_statement",
            },
            {
                "memory_type": "event",
                "title": "Webhook Delay Incident",
                "content": (
                    f"{customer_id} reported delayed invoice webhook delivery "
                    "after rotating signing secrets."
                ),
                "confidence": 0.88,
                "tags": ["langgraph-demo", customer_id, "webhooks", "incident"],
                "source": "langgraph-intake",
                "provenance": "observed",
            },
            {
                "memory_type": "commitment",
                "title": "Escalation Commitment",
                "content": (
                    f"Support committed to verify {customer_id}'s webhook signing "
                    "secret rotation path before suggesting account-level changes."
                ),
                "confidence": 0.86,
                "tags": ["langgraph-demo", customer_id, "follow-up"],
                "source": "langgraph-intake",
                "provenance": "explicit_statement",
            },
        ]

        stored_ids: list[str] = []
        for memory in memories:
            result = client.remember(agent_id=AGENT_ID, **memory)
            stored_ids.append(result["memory_id"])

        return {"stored_memory_ids": stored_ids}

    return node


def recall_customer_context(client: SdkClient):
    """Return a graph node that retrieves relevant long-term memories."""

    def node(state: SupportState) -> SupportState:
        query = (
            f"{state['customer_id']} support preferences plan webhook incident "
            "commitment next steps"
        )
        result = client.recall(
            agent_id=AGENT_ID,
            query=query,
            limit=8,
            type=["preference", "fact", "event", "commitment", "decision"],
        )
        return {"recalled_memories": result["memories"]}

    return node


def _memory_text(memory: dict[str, Any]) -> str:
    """Extract display text from the Moorcheh result shape."""
    text = memory.get("text") or memory.get("document", {}).get("text")
    if text:
        return str(text)
    return str(memory)


def compose_support_response() -> Any:
    """Return a graph node that writes a grounded support response."""

    def node(state: SupportState) -> SupportState:
        memory_lines = [_memory_text(memory) for memory in state["recalled_memories"]]

        if os.environ.get("OPENAI_API_KEY"):
            from langchain_openai import ChatOpenAI

            model = os.environ.get("LANGGRAPH_MEMANTO_MODEL", "gpt-4o-mini")
            llm = ChatOpenAI(model=model, temperature=0)
            result = llm.invoke(
                [
                    SystemMessage(
                        content=(
                            "You are a support agent. Use only the recalled "
                            "Memanto memories and the user's message. Be concise."
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"User message:\n{state['user_message']}\n\n"
                            "Recalled memories:\n"
                            + "\n---\n".join(memory_lines)
                        )
                    ),
                ]
            )
            return {"response": result.content}

        response = (
            "I checked the context we already have for Acme Studio. Since you are "
            "on the Pro plan and the delay started after signing-secret rotation, "
            "the next step is to verify the rotated webhook secret path before we "
            "change account-level settings. I will keep this short and direct: "
            "send the latest failed delivery ID, confirm which signing secret is "
            "active, and I will compare it against the invoice webhook retry logs."
        )
        return {"response": response}

    return node


def build_graph(client: SdkClient, mode: str):
    """Build either the memory-write graph or the recall-and-reply graph."""
    graph = StateGraph(SupportState)

    if mode == "capture":
        graph.add_node("remember_customer_context", remember_customer_context(client))
        graph.add_edge(START, "remember_customer_context")
        graph.add_edge("remember_customer_context", END)
    elif mode == "respond":
        graph.add_node("recall_customer_context", recall_customer_context(client))
        graph.add_node("compose_support_response", compose_support_response())
        graph.add_edge(START, "recall_customer_context")
        graph.add_edge("recall_customer_context", "compose_support_response")
        graph.add_edge("compose_support_response", END)
    else:
        raise ValueError(f"Unknown graph mode: {mode}")

    return graph.compile()


def main() -> None:
    load_dotenv()
    client = setup_memanto()

    try:
        capture_graph = build_graph(client, mode="capture")
        capture_result = capture_graph.invoke(
            {
                "customer_id": CUSTOMER_ID,
                "user_message": (
                    "We rotated webhook signing secrets and invoice webhooks "
                    "started arriving late. Please keep replies direct."
                ),
            },
            config={"configurable": {"thread_id": "capture-thread"}},
        )

        respond_graph = build_graph(client, mode="respond")
        response_result = respond_graph.invoke(
            {
                "customer_id": CUSTOMER_ID,
                "user_message": (
                    "Any update on the invoice webhook delay? What should we send?"
                ),
            },
            config={"configurable": {"thread_id": "follow-up-thread"}},
        )

        print("Stored memory IDs:")
        for memory_id in capture_result["stored_memory_ids"]:
            print(f"  - {memory_id}")

        print("\nRecalled memories:")
        for memory in response_result["recalled_memories"]:
            print(f"  - {_memory_text(memory).splitlines()[0]}")

        print("\nSupport response:")
        print(response_result["response"])
    finally:
        client.deactivate_agent(AGENT_ID)


if __name__ == "__main__":
    main()
