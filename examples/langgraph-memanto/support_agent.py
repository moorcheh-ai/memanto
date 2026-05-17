#!/usr/bin/env python3
"""
LangGraph + Memanto customer support example.

This example keeps the conversational workflow inside LangGraph, while using
Memanto as an external long-term memory layer. The graph has three nodes:

1. greet
2. handle_query
3. store_memory

Run the script multiple times with the same ``customer_id`` to see Memanto
recall the previous support interaction across sessions.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from memanto.cli.client.sdk_client import SdkClient

AGENT_ID = "langgraph-support-agent"
SESSION_HOURS = 6


class SupportState(TypedDict, total=False):
    customer_id: str
    customer_name: str
    message: str
    customer_tag: str
    greeting: str
    memory_context: str
    response: str
    stored_memory_id: str


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "customer"


def _customer_tag(customer_id: str) -> str:
    return f"customer_{_slugify(customer_id)}"


def _memory_excerpt(memory: dict[str, Any]) -> str:
    title = str(memory.get("title") or "Untitled memory")
    content = str(memory.get("content") or memory.get("text") or "").strip()
    if len(content) > 140:
        content = content[:137].rstrip() + "..."
    if content:
        return f"{title}: {content}"
    return title


def _format_memory_context(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return "No prior support history found."

    excerpts = [_memory_excerpt(memory) for memory in memories[:3]]
    return "Previous interactions: " + " | ".join(excerpts)


def _support_response(message: str, memory_context: str) -> str:
    text = message.lower()

    if any(keyword in text for keyword in ("login", "sign in", "password", "access")):
        return (
            "It looks like this is a login issue. Please try resetting your password, "
            "clear your browser cache, and confirm that two-factor authentication is "
            "not blocking the sign-in flow. "
            f"{memory_context}"
        )

    if any(keyword in text for keyword in ("bill", "billing", "invoice", "charge", "refund")):
        return (
            "I can help with billing. Please share the invoice number or the last four "
            "digits of the card used so we can trace the charge. "
            f"{memory_context}"
        )

    if any(keyword in text for keyword in ("slow", "lag", "crash", "error", "bug")):
        return (
            "This sounds like a product stability issue. Please send the exact error "
            "message and the steps that reproduce it so we can narrow it down. "
            f"{memory_context}"
        )

    return (
        "Thanks for the details. I will document this and keep the prior support "
        f"history in mind. {memory_context}"
    )


def build_graph(client: SdkClient, agent_id: str) -> Any:
    """Build the three-node LangGraph workflow."""

    def greet(state: SupportState) -> dict[str, str]:
        customer_name = state["customer_name"]
        customer_tag = state["customer_tag"]
        message = state["message"]

        recall_result = client.recall(
            agent_id=agent_id,
            query=f"prior support interactions for {customer_name} about {message}",
            limit=3,
            tags=[customer_tag],
        )
        memory_context = _format_memory_context(recall_result.get("memories", []))

        if "No prior support history found." in memory_context:
            greeting = (
                f"Hello {customer_name}. I am your support assistant for this account. "
                "I will check memory for anything useful and help with your request."
            )
        else:
            greeting = (
                f"Welcome back, {customer_name}. I found your previous support history "
                "and will use it to keep this session consistent."
            )

        return {"greeting": greeting, "memory_context": memory_context}

    def handle_query(state: SupportState) -> dict[str, str]:
        message = state["message"]
        memory_context = state.get("memory_context", "No prior support history found.")
        response = _support_response(message, memory_context)
        return {"response": response}

    def store_memory(state: SupportState) -> dict[str, str]:
        customer_id = state["customer_id"]
        customer_name = state["customer_name"]
        customer_tag = state["customer_tag"]
        message = state["message"]
        response = state["response"]

        result = client.remember(
            agent_id=agent_id,
            memory_type="event",
            title=f"{customer_name} support interaction",
            content=(
                f"Customer {customer_name} ({customer_id}) asked: {message}. "
                f"Support response: {response}"
            ),
            confidence=0.92,
            tags=[customer_tag, "support", "customer_service"],
            source="langgraph-node",
            provenance="explicit_statement",
        )

        return {"stored_memory_id": str(result["memory_id"])}

    graph = StateGraph(SupportState)
    graph.add_node("greet", greet)
    graph.add_node("handle_query", handle_query)
    graph.add_node("store_memory", store_memory)
    graph.add_edge(START, "greet")
    graph.add_edge("greet", "handle_query")
    graph.add_edge("handle_query", "store_memory")
    graph.add_edge("store_memory", END)

    return graph.compile()


def create_client(api_key: str) -> SdkClient:
    client = SdkClient(api_key=api_key)

    try:
        client.create_agent(
            agent_id=AGENT_ID,
            pattern="tool",
            description="LangGraph customer support agent with Memanto long-term memory",
        )
    except Exception:
        pass

    client.activate_agent(agent_id=AGENT_ID, duration_hours=SESSION_HOURS)
    return client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LangGraph customer support demo with Memanto persistence."
    )
    parser.add_argument(
        "--customer-id",
        default="acme-001",
        help="Stable customer identifier used to scope memory across sessions.",
    )
    parser.add_argument(
        "--customer-name",
        default="Customer",
        help="Display name used in the greeting and response.",
    )
    parser.add_argument(
        "--message",
        help="Customer support message. If omitted, the script prompts interactively.",
    )
    return parser.parse_args()


def main() -> None:
    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print(
            "Error: MOORCHEH_API_KEY is not set. Set it before running this example."
        )
        sys.exit(1)

    args = parse_args()
    message = args.message or input("Customer message: ").strip()
    if not message:
        print("Error: customer message cannot be empty.")
        sys.exit(1)

    client = create_client(api_key)
    customer_tag = _customer_tag(args.customer_id)
    graph = build_graph(client, AGENT_ID)

    state: SupportState = {
        "customer_id": args.customer_id,
        "customer_name": args.customer_name,
        "customer_tag": customer_tag,
        "message": message,
    }

    try:
        result = graph.invoke(state)

        print("\n=== LangGraph Support Agent ===")
        print(result["greeting"])
        print()
        print(result["response"])
        print()
        print(f"Stored Memanto memory ID: {result['stored_memory_id']}")
        print(f"Memanto customer tag: {customer_tag}")
    finally:
        try:
            client.deactivate_agent(AGENT_ID)
        except Exception:
            pass


if __name__ == "__main__":
    main()
