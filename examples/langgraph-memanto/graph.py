"""
LangGraph research assistant with Memanto as the long-term memory layer.

Architecture:
    START → recall_node → agent_node ⇄ tools_node → END

Responsibilities:
    - LangGraph manages orchestration + session execution state
    - Memanto manages durable semantic memory across sessions
    - recall_node injects memory context at graph startup
    - tools allow dynamic memory operations during conversations

This implementation intentionally does NOT use LangGraph checkpointing
for long-term memory persistence.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from tools import MEMANTO_TOOLS, init_tools
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """
    LangGraph session state only.
    Durable long-term memory is handled externally by Memanto.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]
    session_id: str


SYSTEM_PROMPT = """
You are a persistent research assistant powered by Memanto long-term memory.

RULES:
1. Relevant memories may already be injected into context by the recall_node.
2. Use recall_memory or recall_preferences when additional retrieval is needed.
3. When you learn important new information, store it using:
      - remember_fact
      - remember_preference
      - remember_decision
4. When stored information becomes outdated, use correct_memory.
5. Use answer_from_memory when synthesising multiple memories.
6. Never claim memory loss without checking memory tools first.

You maintain continuity across independent sessions and processes.
"""


def make_recall_node(client):
    """
    Load relevant memories before the agent executes.

    This enables cross-session recall even in a completely fresh
    Python process with a brand-new LangGraph execution state.
    """

    def recall_node(state: AgentState) -> dict:
        last_human = next(
            (
                m.content
                for m in reversed(state["messages"])
                if isinstance(m, HumanMessage)
            ),
            "recent conversation context",
        )

        memories = client.recall(query=last_human, limit=5)
        preferences = client.recall(
            query="user communication preferences",
            limit=3,
            memory_type="preference",
        )

        context_parts = []
        if memories:
            context_parts.append("📚 Relevant past memories:")
            for memory in memories:
                context_parts.append(
                    f"  [{memory.get('id', '?')}] {memory.get('content', '')[:200]}"
                )
        if preferences:
            context_parts.append("👤 User preferences:")
            for pref in preferences:
                context_parts.append(f"  • {pref.get('content', '')}")

        context = (
            "\n".join(context_parts) if context_parts else "No prior memories found."
        )

        combined_system_prompt = (
            f"{SYSTEM_PROMPT.strip()}\n\n"
            f"[MEMANTO CONTEXT — loaded at session start]\n"
            f"{context}"
        )

        return {
            "messages": [
                SystemMessage(id="memanto_context", content=combined_system_prompt)
            ]
        }

    return recall_node


def make_agent_node(llm_with_tools):
    def agent_node(state: AgentState) -> dict:
        response = llm_with_tools.invoke(list(state["messages"]))
        return {"messages": [response]}

    return agent_node


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def build_graph(
    base_url: str | None = None,
    api_key: str | None = None,
    agent_id: str = "langgraph-agent",
    model: str = "gpt-4o",
):
    """
    Build and compile the LangGraph + Memanto workflow.

    Args:
        base_url:  Memanto server URL
        api_key:   Moorcheh API key
        agent_id:  Shared namespace across sessions
        model:     OpenAI-compatible model name

    Returns:
        Compiled LangGraph runnable
    """
    client = init_tools(base_url=base_url, api_key=api_key, agent_id=agent_id)

    llm = ChatOpenAI(model=model, temperature=0)
    llm_with_tools = llm.bind_tools(MEMANTO_TOOLS)

    recall_node = make_recall_node(client)
    agent_node = make_agent_node(llm_with_tools)
    tool_node = ToolNode(MEMANTO_TOOLS)

    workflow = StateGraph(AgentState)
    workflow.add_node("recall", recall_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    workflow.add_edge(START, "recall")
    workflow.add_edge("recall", "agent")
    workflow.add_conditional_edges(
        "agent", should_continue, {"tools": "tools", END: END}
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()
