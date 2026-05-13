"""LangGraph agent definition for Memanto-powered memory.

Defines the graph structure and compilation of the LangGraph agent
that uses Memanto as its long-term memory layer.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from langgraph_memanto.memory_client import MemantoClient
from langgraph_memanto.nodes import memory_node, respond_node, think_node
from langgraph_memanto.state import AgentState


def build_agent(
    memanto_client: MemantoClient | None = None,
    agent_id: str = "langgraph-agent",
    llm_model: str = "gpt-4o-mini",
) -> StateGraph:
    """Build a LangGraph agent that uses Memanto for long-term memory.

    The graph has three nodes:
      1. Think — Decide what to remember or recall
      2. Memory — Execute memory operations via Memanto
      3. Respond — Generate the final response

    Returns:
        A compiled LangGraph StateGraph (callable as a runnable).
    """
    client = memanto_client or MemantoClient(agent_id=agent_id)

    # Ensure the Memanto agent exists
    client.ensure_agent()

    # Build the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("think", lambda state: think_node(state, llm_model=llm_model))
    workflow.add_node("memory", lambda state: memory_node(state, client=client))
    workflow.add_node("respond", lambda state: respond_node(state, llm_model=llm_model))

    # Set the entry point
    workflow.set_entry_point("think")

    # Add edges
    workflow.add_conditional_edges(
        "think",
        _route_after_think,
        {"memory": "memory", "respond": "respond"},
    )
    workflow.add_edge("memory", "respond")
    workflow.add_edge("respond", END)

    return workflow.compile()


def _route_after_think(state: AgentState) -> str:
    """Route to memory node if we need to store/retrieve, else respond directly."""
    if state.thoughts and ("remember" in state.thoughts.lower() or "recall" in state.thoughts.lower()):
        return "memory"
    return "respond"
