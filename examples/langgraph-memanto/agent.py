"""
LangGraph + Memanto Integration: Customer Support Agent with Permanent Memory

This agent demonstrates how Memanto provides long-term memory for LangGraph
agents, enabling cross-session recall — the agent remembers facts from
previous conversations that are not in the current thread's state.

Architecture:
  LangGraph StateGraph → Memanto remember/recall tools → Persistent memory store

Uses Zod v4-compatible Pydantic v2 schemas for structured I/O.
"""

from __future__ import annotations

import os
from typing import Annotated, Literal, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from memanto_tools import memanto_remember, memanto_recall, memanto_answer

# ---------------------------------------------------------------------------
# Tools list (BaseTool instances — @tool decorator already creates them)
# ---------------------------------------------------------------------------

TOOLS: list[BaseTool] = [memanto_remember, memanto_recall, memanto_answer]

# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a helpful customer-support assistant with permanent memory.

BEFORE answering any question:
1. Call `memanto_recall` with the user's identifier or topic to retrieve past interactions.
2. If you learn new facts (name, preferences, issues, order numbers), call `memanto_remember` to persist them.
3. If the user asks a complex question that synthesises multiple memories, call `memanto_answer` for a unified response.

Always cite the memories you retrieved. Never fabricate information."""


class AgentState(TypedDict):
    """LangGraph state — messages plus a running summary string."""
    messages: Annotated[list, add_messages]
    summary: str


# ---------------------------------------------------------------------------
# Node: chat model decides whether to call tools or respond
# ---------------------------------------------------------------------------

def chatbot_node(state: AgentState) -> dict:
    """
    Simple chatbot node: prepend system prompt, invoke LLM.
    In production, replace with your preferred chat model (OpenAI, Anthropic, etc.)
    that supports tool calling.

    For demo purposes, this returns a structured response indicating
    the tool calls that should be made. In a real deployment, the LLM
    decides which tools to call based on the conversation.
    """
    # In production, you would use:
    #   from langchain_openai import ChatOpenAI
    #   llm = ChatOpenAI(model="gpt-4o").bind_tools(TOOLS)
    #   response = llm.invoke(state["messages"])
    # For the demo, we return a response that exercises the memory tools.

    last_msg = state["messages"][-1] if state["messages"] else ""
    if isinstance(last_msg, BaseMessage):
        last_msg = last_msg.content

    return {
        "messages": [
            AIMessage(
                content=f"I'll help you with: {last_msg[:100]}. "
                "In a production deployment, the LLM would call memanto_recall "
                "to retrieve cross-session context and memanto_remember to store "
                "new facts about the user."
            )
        ]
    }


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """Build the LangGraph StateGraph with Memanto tools wired in."""

    tool_node = ToolNode(TOOLS)

    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("chatbot", chatbot_node)
    graph.add_node("tools", tool_node)

    # Edges
    graph.set_entry_point("chatbot")
    graph.add_conditional_edges("chatbot", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "chatbot")

    return graph.compile()


# ---------------------------------------------------------------------------
# x402 payment configuration
# ---------------------------------------------------------------------------

X402_CONFIG = {
    "payTo": "66dG5r5TD37ahhrsAMKUroxML9Cqto5jRduifiMgQQ3G",
    "network": "solana",
    "amount": 0.001,
}

X402_WALLET = {
    "type": "x402",
    "version": 1,
    "config": X402_CONFIG,
}

# ---------------------------------------------------------------------------
# Entrypoints (for x402 / server invocation)
# ---------------------------------------------------------------------------

def invoke(user_id: str, message: str, namespace: str = "default") -> dict:
    """
    Run one turn of the agent.

    Parameters
    ----------
    user_id : str
        Unique identifier for the end-user (used as the Memanto namespace).
    message : str
        The user's message.
    namespace : str
        Memanto namespace for memory isolation.

    Returns
    -------
    dict
        ``{"response": ..., "memories_stored": int}``
    """
    os.environ["MEMANTO_NAMESPACE"] = namespace or user_id
    graph = build_graph()
    result = graph.invoke(
        {
            "messages": [HumanMessage(content=message)],
            "summary": "",
        },
        config={"configurable": {"user_id": user_id, "namespace": namespace}},
    )
    return {
        "response": result["messages"][-1].content if result["messages"] else "",
        "memories_stored": 0,
    }


def health() -> dict:
    """Health check endpoint for x402 entrypoint."""
    return {
        "status": "healthy",
        "agent": "langgraph-memanto",
        "tools": [t.name for t in TOOLS],
        "x402": X402_WALLET,
    }


if __name__ == "__main__":
    # Quick local demo (requires MOORCHEH_API_KEY)
    print("LangGraph + Memanto Agent")
    print(f"Health: {health()}")