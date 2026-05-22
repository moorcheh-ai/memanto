"""
langgraph-memanto: LangGraph integration for Memanto's persistent memory.

Provides LangChain/LangGraph-compatible tools and a pre-built LangGraph
workflow for agents that need cross-session persistent memory via Memanto.

Quick start:
    from langgraph_memanto import MemantoSetup, create_memanto_tools

    setup = MemantoSetup(api_key="...")
    client = setup.setup(agent_id="my-agent")
    tools = create_memanto_tools(client, agent_id="my-agent")
"""

from .setup import MemantoSetup
from .tools import (
    MemantoAnswerTool,
    MemantoRecallTool,
    MemantoRememberTool,
    create_memanto_tools,
)
from .graph import (
    build_memanto_graph,
    create_memanto_agent,
)

__all__ = [
    "MemantoSetup",
    "MemantoRememberTool",
    "MemantoRecallTool",
    "MemantoAnswerTool",
    "create_memanto_tools",
    "build_memanto_graph",
    "create_memanto_agent",
]
