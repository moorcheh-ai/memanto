"""
LangGraph + Memanto Integration: Customer Support Agent

A LangGraph agent that uses Memanto as its persistent, cross-session
memory layer. The agent can:
- Remember facts about users across sessions
- Recall past interactions to provide personalized support
- Answer questions grounded in stored knowledge

This demonstrates how LangGraph's state graph can be augmented with
Memanto's three primitives: remember, recall, and answer.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Literal, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from memanto.cli.client.sdk_client import SdkClient
from memanto_langgraph import MemantoSetup, create_memanto_tools

# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    """State shared across the LangGraph agent's nodes."""

    messages: Annotated[list, add_messages]
    user_id: str
    session_id: str
    memories_recalled: bool
    agent_id: str


# ---------------------------------------------------------------------------
# Agent builder
# ---------------------------------------------------------------------------


def build_customer_support_agent(
    api_key: str,
    agent_id: str = "langgraph-support-agent",
    model_name: str = "gpt-4o-mini",
) -> tuple[StateGraph, SdkClient, MemantoSetup]:
    """
    Build a LangGraph customer support agent with Memanto memory.

    Returns:
        Tuple of (compiled_graph, sdk_client, memanto_setup)
    """
    # Setup Memanto
    setup = MemantoSetup(api_key=api_key)
    client = setup.setup(
        agent_id=agent_id,
        pattern="tool",
        description="LangGraph customer support agent with persistent memory",
    )

    # Create tools
    memanto_tools = create_memanto_tools(client, agent_id)

    # -----------------------------------------------------------------------
    # Define typed tools for LangGraph's ToolNode
    # -----------------------------------------------------------------------

    @tool
    def memanto_remember(
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: str = "",
    ) -> dict:
        """Store information in persistent memory. Use to save user preferences,
        facts, decisions, or anything worth remembering across sessions.

        Args:
            memory_type: Type of memory (fact, preference, observation, decision, etc.)
            title: Short title (max 100 chars)
            content: Memory content (max 500 chars)
            confidence: Confidence 0.0-1.0 (1.0 for explicit facts)
            tags: Comma-separated tags
        """
        return memanto_tools["remember"](
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
        )

    @tool
    def memanto_recall(
        query: str,
        limit: int = 5,
        memory_types: str = "",
    ) -> dict:
        """Search persistent memory for relevant information. Use to
        recall past interactions, user preferences, or stored knowledge.

        Args:
            query: Natural language search query
            limit: Max memories to return (1-20)
            memory_types: Comma-separated types to filter by
        """
        return memanto_tools["recall"](
            query=query,
            limit=limit,
            memory_types=memory_types,
        )

    @tool
    def memanto_answer(question: str) -> dict:
        """Get an AI-generated answer grounded in stored memories (RAG).
        Use this to synthesize knowledge from multiple memories.

        Args:
            question: Question to answer from stored knowledge
        """
        return memanto_tools["answer"](question=question)

    tools = [memanto_remember, memanto_recall, memanto_answer]
    tool_node = ToolNode(tools)

    # -----------------------------------------------------------------------
    # Graph nodes
    # -----------------------------------------------------------------------

    SYSTEM_PROMPT = """You are a helpful customer support agent with persistent memory powered by Memanto.

Your capabilities:
- **remember**: Store facts about users, their preferences, past issues, and resolutions
- **recall**: Look up past interactions and stored knowledge before responding
- **answer**: Synthesize answers from stored memories

Workflow for every user message:
1. First, use **recall** to check if you have any stored memories about this user or topic
2. Then respond to the user, referencing any relevant memories you found
3. After helping the user, use **remember** to store key facts for future sessions

Always be warm and personalized. Reference past interactions when relevant."""

    def call_model(state: AgentState) -> dict:
        """Call the LLM with tools available."""
        model = ChatOpenAI(model=model_name, temperature=0.3)
        model_with_tools = model.bind_tools(tools)

        if not state.get("memories_recalled"):
            # First turn: ask agent to recall before responding
            human_msg = state["messages"][-1]
            recall_prompt = HumanMessage(
                content=(
                    f"User {state['user_id']} says: {human_msg.content}\n\n"
                    "Before responding, use memanto_recall to check for "
                    f"past interactions with user '{state['user_id']}' and "
                    "any stored knowledge about their topic."
                )
            )
            messages = [SystemMessage(content=SYSTEM_PROMPT), recall_prompt]
        else:
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]

        response = model_with_tools.invoke(messages)
        return {"messages": [response], "memories_recalled": True}

    def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
        """Route to tools or end based on last message."""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "__end__"

    # Build the graph
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", "__end__": END})
    workflow.add_edge("tools", "agent")

    return workflow.compile(), client, setup
