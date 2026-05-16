"""
LangGraph workflow with Memanto persistent memory.

This module defines a customer support agent that uses Memanto to remember
user preferences and past interactions across sessions.
"""

from __future__ import annotations

import sys
from typing import Annotated, Literal, Sequence, TypedDict

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

sys.path.insert(0, "../../integrations/langgraph")
from memanto_langgraph import get_all_tools

from memanto.cli.client.sdk_client import SdkClient


class AgentState(TypedDict):
    """State container for the LangGraph agent."""

    messages: Annotated[Sequence[BaseMessage], add_messages]


SYSTEM_PROMPT = """You are a helpful customer support assistant with access to persistent memory.

You have three memory tools available:
1. memanto_remember - Store important information about the user (preferences, facts, decisions)
2. memanto_recall - Search and retrieve previously stored memories
3. memanto_answer - Get AI-generated answers based on stored memories

IMPORTANT GUIDELINES:
- When the user shares preferences or important information, ALWAYS use memanto_remember to store it
- When the user asks about past conversations or their preferences, use memanto_recall first
- Be proactive about storing useful information that might help in future conversations
- When storing memories, use appropriate types: 'preference' for likes/dislikes, 'fact' for information, 'decision' for choices made

Remember: Memories persist across sessions, so what you store now will be available in future conversations."""


def build_support_graph(
    client: SdkClient,
    agent_id: str,
    model: str = "gpt-4o-mini",
) -> StateGraph:
    """
    Build the customer support LangGraph workflow with Memanto tools.

    Args:
        client: Initialized Memanto SdkClient with an active session.
        agent_id: The Memanto agent ID to use for memory operations.
        model: The OpenAI model to use (default: gpt-4o-mini).

    Returns:
        Compiled StateGraph ready for invocation.
    """
    tools = get_all_tools(client, agent_id)
    llm = ChatOpenAI(model=model, temperature=0.7)
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState) -> dict:
        """Process messages and generate a response."""
        messages = list(state["messages"])

        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
        """Determine if we should continue to tools or end."""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    tool_node = ToolNode(tools)
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END},
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()
