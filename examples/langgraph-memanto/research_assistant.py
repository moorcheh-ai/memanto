"""
LangGraph Research Assistant with Memanto Persistent Memory

Defines the graph structure for a research assistant that uses Memanto
to store and retrieve findings across sessions.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from memanto.cli.client.sdk_client import SdkClient
from memanto_langgraph import MemantoMemorySaver, create_memanto_tools


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    """State for the research assistant graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    past_context: str  # Loaded from Memanto at session start
    mode: str  # "research" or "recall"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_research_graph(
    client: SdkClient,
    agent_id: str = "research-assistant",
    model: str = "gpt-4o-mini",
) -> tuple[Any, MemantoMemorySaver]:
    """
    Build and return the LangGraph research assistant.

    Returns:
        (compiled_graph, memory_saver) — the saver is exposed so the
        caller can load context before invoking and save interactions after.
    """
    # Create Memanto tools and memory saver
    tools = create_memanto_tools(client, agent_id)
    saver = MemantoMemorySaver(client, agent_id=agent_id, max_context_memories=10)

    # Create LLM with Memanto tools bound
    llm = ChatOpenAI(model=model, temperature=0.3).bind_tools(tools)
    tool_node = ToolNode(tools)

    # -- Node functions -----------------------------------------------------

    def agent_node(state: AgentState) -> dict[str, Any]:
        """Main agent node — calls the LLM with Memanto tools."""
        messages = state["messages"]
        past_context = state.get("past_context", "")

        # Build system prompt with persistent memory context
        system_content = (
            "You are a helpful research assistant with access to a persistent "
            "memory system called Memanto. You can store findings using "
            "memanto_remember, search past memories using memanto_recall, "
            "and get synthesized answers using memanto_answer.\n\n"
            "IMPORTANT: Always use memanto_remember to store important findings, "
            "user preferences, and key facts so they persist across sessions. "
            "Use memanto_recall to check if you already know something from "
            "past sessions before researching from scratch."
        )

        if past_context:
            system_content += f"\n\n{past_context}"

        # Prepend system message
        full_messages = [SystemMessage(content=system_content)] + list(messages)
        response = llm.invoke(full_messages)

        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        """Route to tools if the LLM called any, otherwise end."""
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "tools"
        return END

    # -- Build the graph ----------------------------------------------------

    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    compiled = graph.compile()

    return compiled, saver
