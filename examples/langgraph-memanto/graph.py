"""
graph.py
========
LangGraph research-assistant with Memanto as the long-term memory layer.

Graph structure:
  [start] → recall_node → agent_node ⇄ tools_node → [end]
                                ↑_______________|

Key design:
  • recall_node runs FIRST every session — loads past context from Memanto
  • agent_node decides when to call Memanto tools (remember / recall / correct)
  • LangGraph state holds ONLY the current conversation thread
  • Memanto holds ALL long-term memory — survives across sessions/restarts

This is the correct pattern: LangGraph manages flow, Memanto manages memory.
No LangGraph checkpointer is used for long-term memory — Memanto is the sole store.
"""
from __future__ import annotations

import os
from typing import Annotated, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from tools import MEMANTO_TOOLS, init_tools

# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """
    LangGraph thread state — current session only.
    Long-term memory lives in Memanto, not here.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    session_id: str          # for logging/tracing
    memory_context: str      # injected by recall_node at session start


# ── Nodes ─────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a persistent research assistant powered by Memanto long-term memory.

CRITICAL RULES:
1. Relevant memories may already be injected into context by the recall_node.
2. Use recall_memory or recall_preferences only when you need additional retrieval during the conversation.
3. When you learn something new and important, call remember_fact or remember_preference.
4. When a stored fact is outdated, call correct_memory with the old fact and the corrected fact.
5. Use answer_from_memory to synthesise multiple past findings.
6. NEVER claim you don't remember something without first calling recall_memory.

You have permanent memory across sessions. Today's conversation is one thread
in a long-running relationship — act accordingly.
"""


def make_recall_node(client):
    """
    Injects prior session context into state BEFORE the agent runs.
    This is what enables cross-session recall without any extra agent calls.
    """
    def recall_node(state: AgentState) -> dict:
        # Pull the last human message to seed the recall query
        last_human = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            "recent context"
        )
        memories = client.recall(query=last_human, limit=5)
        prefs    = client.recall(query="user preferences communication style", limit=3, memory_type="preference")

        context_parts = []
        if memories:
            context_parts.append("📚 Relevant past memories:")
            for m in memories:
                context_parts.append(f"  [{m.get('id','?')}] {m.get('content','')[:200]}")
        if prefs:
            context_parts.append("👤 User preferences:")
            for p in prefs:
                context_parts.append(f"  • {p.get('content','')}")

        context = "\n".join(context_parts) if context_parts else "No prior memories found."

        # Inject context as a system message so the agent always sees it
        context_msg = SystemMessage(content=f"[MEMANTO CONTEXT — loaded at session start]\n{context}")
        return {
            "memory_context": context,
            "messages": [context_msg],
        }

    return recall_node


def make_agent_node(llm_with_tools):
    def agent_node(state: AgentState) -> dict:
        # Build messages: system prompt + conversation history
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(state["messages"])
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}
    return agent_node


def should_continue(state: AgentState) -> str:
    """Route to tools if the agent made tool calls, otherwise end."""
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_graph(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    agent_id: str = "langgraph-agent",
    model: str = "gpt-4o",
):
    """
    Build and compile the LangGraph + Memanto agent.

    Args:
        base_url:  Memanto server URL (or MEMANTO_BASE_URL env var)
        api_key:   Moorcheh API key (or MOORCHEH_API_KEY env var)
        agent_id:  Memanto namespace — SAME value across all sessions for persistence
        model:     LLM model name

    Returns:
        Compiled LangGraph runnable
    """
    # Init Memanto client + tools
    client = init_tools(base_url=base_url, api_key=api_key, agent_id=agent_id)

    # LLM with Memanto tools bound
    llm = ChatOpenAI(model=model, temperature=0)
    llm_with_tools = llm.bind_tools(MEMANTO_TOOLS)

    # Nodes
    recall_node = make_recall_node(client)
    agent_node  = make_agent_node(llm_with_tools)
    tool_node   = ToolNode(MEMANTO_TOOLS)

    # Graph
    g = StateGraph(AgentState)
    g.add_node("recall",  recall_node)
    g.add_node("agent",   agent_node)
    g.add_node("tools",   tool_node)

    g.add_edge(START,     "recall")   # always recall first
    g.add_edge("recall",  "agent")
    g.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    g.add_edge("tools",   "agent")    # loop back after tool calls

    return g.compile()