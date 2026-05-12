"""
LangGraph Customer Support Agent with Memanto Persistent Memory

This module defines a stateful customer support agent graph that uses Memanto
as its long-term memory layer. It demonstrates:
- Cross-session recall: remembers customer preferences and past interactions
- Persistent context: doesn't need to re-ask for information already known
- Learning from errors: stores correction memories to improve future responses
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel

from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI

from tools import MemantoSetup, create_memanto_tools


# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------


class SupportState(BaseModel):
    """State passed between nodes in the customer support graph."""

    customer_id: str = ""
    customer_name: str = ""
    issue_type: str = ""
    issue_description: str = ""
    prior_interactions: list[dict] = []
    customer_preferences: list[dict] = []
    resolution: str = ""
    messages: list[str] = []
    knowledge_retrieved: bool = False


# ---------------------------------------------------------------------------
# Node Functions
# ---------------------------------------------------------------------------


def greet_and_check_history(state: SupportState, tools: dict, llm) -> SupportState:
    """
    First node: Greet customer and check for any prior interactions/preferences.

    This is where cross-session recall happens - we check Memanto for
    any previous support interactions and customer preferences.
    """
    messages = []

    # Check for prior support interactions
    interactions_result = tools["recall"]._run(
        query=f"customer support interaction {state.customer_id}",
        limit=5,
        memory_types="event,observation",
    )

    # Check for customer preferences (may have been stored during previous sessions)
    preferences_result = tools["recall"]._run(
        query=f"customer {state.customer_id} preferences support style",
        limit=3,
        memory_types="preference,context",
    )

    # Build contextual greeting
    context_parts = []
    if "Found" in interactions_result and "memories" in interactions_result:
        context_parts.append("previous interactions")
        messages.append(f"[Prior Support History]\n{interactions_result}")

    if "Found" in preferences_result and "memories" in preferences_result:
        context_parts.append("customer preferences")
        messages.append(f"[Customer Preferences]\n{preferences_result}")

    context_str = ", ".join(context_parts) if context_parts else "new customer"

    greeting = f"Hello {state.customer_name}! I see you're a {context_str}. How can I help you today?"

    return state.model_copy(
        update={
            "messages": messages + [f"[Greeting]\n{greeting}"],
            "prior_interactions": [{"interactions": interactions_result}],
            "customer_preferences": [{"preferences": preferences_result}],
            "knowledge_retrieved": True,
        }
    )


def diagnose_issue(state: SupportState, tools: dict, llm) -> SupportState:
    """
    Second node: Diagnose the customer issue using LLM with prior context.

    Uses prior interactions and preferences to provide personalized support.
    """
    context = ""
    if state.prior_interactions:
        for item in state.prior_interactions:
            for key, value in item.items():
                if "Found" in value:
                    context += f"\nPrevious support context:\n{value}\n"

    system_prompt = f"""You are a customer support agent. Your task is to understand and diagnose
the customer's issue.

Customer: {state.customer_name}
Issue Type: {state.issue_type}
Issue Description: {state.issue_description}

{context}

Ask a clarifying question or provide initial diagnosis. Be empathetic and efficient."""


    response = llm.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Customer issue: {state.issue_description}"},
        ]
    )

    diagnosis = response.content if hasattr(response, "content") else str(response)

    return state.model_copy(
        update={
            "messages": state.messages + [f"[Diagnosis]\n{diagnosis}"],
        }
    )


def resolve_issue(state: SupportState, tools: dict, llm) -> SupportState:
    """
    Third node: Resolve the issue and store the interaction in memory.

    This stores both the resolution and any new preferences discovered.
    """
    # Generate resolution
    system_prompt = f"""You are a customer support agent. Provide a clear resolution
for the customer's issue.

Customer: {state.customer_name}
Issue: {state.issue_description}

Provide:
1. Solution/explanation
2. Any follow-up actions needed
3. Estimated resolution time if applicable

Be clear and helpful."""

    response = llm.invoke(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Resolve: {state.issue_description}"},
        ]
    )

    resolution = response.content if hasattr(response, "content") else str(response)

    # Store the interaction in Memanto for future reference
    # Store as event type (support interaction)
    tools["remember"]._run(
        memory_type="event",
        title=f"Support interaction: {state.issue_type}",
        content=f"Customer {state.customer_id} ({state.customer_name}) - Issue: {state.issue_description[:200]}... Resolution: {resolution[:200]}...",
        confidence=0.9,
        tags=f"support,{state.issue_type.lower().replace(' ', '-')}",
    )

    # Store any new customer preferences discovered
    if "preferred" in resolution.lower() or "likes" in resolution.lower() or "prefers" in resolution.lower():
        tools["remember"]._run(
            memory_type="preference",
            title=f"Customer preference: {state.customer_id}",
            content=f"Discovered during support: {resolution[:300]}",
            confidence=0.75,
            tags=f"support,preference,{state.customer_id}",
        )

    return state.model_copy(
        update={
            "resolution": resolution,
            "messages": state.messages + [f"[Resolution]\n{resolution}"],
        }
    )


def follow_up(state: SupportState, tools: dict, llm) -> SupportState:
    """
    Fourth node: Schedule follow-up if needed and summarize.

    Uses Memanto's RAG to check if any follow-up is needed based on past patterns.
    """
    # Check if there's a pattern suggesting follow-up
    follow_up_check = tools["recall"]._run(
        query=f"customer {state.customer_id} follow-up needed unresolved",
        limit=3,
        memory_types="commitment,goal",
    )

    follow_up_note = ""
    if "Found" in follow_up_check and "memories" in follow_up_check:
        follow_up_note = "\n\n[Follow-up Required]\n"
        follow_up_note += follow_up_check

    summary = f"Support session complete for {state.customer_name}.\nResolution provided. Thank you for contacting support!{follow_up_note}"

    return state.model_copy(
        update={
            "messages": state.messages + [f"[Summary]\n{summary}"],
        }
    )


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------


def build_support_graph(
    client,
    agent_id: str,
    llm=None,
):
    """
    Build and compile the customer support agent graph.

    Args:
        client: Memanto SdkClient instance
        agent_id: Memanto agent ID for memory namespace
        llm: Language model (defaults to GPT-4o-mini via OpenAI)

    Returns:
        Compiled LangGraph for the customer support agent
    """
    if llm is None:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)

    tools = create_memanto_tools(client, agent_id)

    # Create the graph
    graph = StateGraph(SupportState)

    # Add nodes
    graph.add_node(
        "greet_and_check_history",
        lambda state: greet_and_check_history(state, tools, llm),
    )
    graph.add_node(
        "diagnose_issue",
        lambda state: diagnose_issue(state, tools, llm),
    )
    graph.add_node(
        "resolve_issue",
        lambda state: resolve_issue(state, tools, llm),
    )
    graph.add_node(
        "follow_up",
        lambda state: follow_up(state, tools, llm),
    )

    # Define edges
    graph.add_edge(START, "greet_and_check_history")
    graph.add_edge("greet_and_check_history", "diagnose_issue")
    graph.add_edge("diagnose_issue", "resolve_issue")
    graph.add_edge("resolve_issue", "follow_up")
    graph.add_edge("follow_up", END)

    return graph.compile()