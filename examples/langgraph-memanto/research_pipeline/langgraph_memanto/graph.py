"""
LangGraph pipeline for the Research + Writer team with Memanto memory.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from .nodes import research_agent_factory, writer_agent_factory
from .state import ResearchState


def build_research_graph(tools: list) -> StateGraph:
    """
    Build and compile the research pipeline graph.

    Flow:
        START → research_agent ↔ tools
                 ↓ (when finished)
                writer_agent ↔ tools
                 ↓ (when finished)
                END
    """
    graph = StateGraph(ResearchState)

    research_agent = research_agent_factory(tools)
    writer_agent = writer_agent_factory(tools)

    # Add nodes
    graph.add_node("research", research_agent)
    graph.add_node("writer", writer_agent)

    tool_node = ToolNode(tools=tools)
    graph.add_node("research_tools", tool_node)
    graph.add_node("writer_tools", tool_node)

    # Set entry point
    graph.set_entry_point("research")

    # Routing from research
    def research_router(state: dict[str, Any]):
        messages = state.get("messages", [])
        if not messages:
            return "writer"
        last = messages[-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "research_tools"
        return "writer"

    graph.add_conditional_edges(
        "research",
        research_router,
        {"research_tools": "research_tools", "writer": "writer"},
    )
    graph.add_edge("research_tools", "research")

    # Routing from writer
    def writer_router(state: dict[str, Any]):
        messages = state.get("messages", [])
        if not messages:
            return END
        last = messages[-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "writer_tools"
        return END

    graph.add_conditional_edges(
        "writer", writer_router, {"writer_tools": "writer_tools", END: END}
    )
    graph.add_edge("writer_tools", "writer")

    return graph


def compile_graph(tools: list):
    """Build and return a compiled graph ready to invoke."""
    builder = build_research_graph(tools)
    return builder.compile()


# ---------------------------------------------------------------------------
# Convenience runners
# ---------------------------------------------------------------------------


def run_research(
    topic: str, memanto_agent_id: str = "langgraph-research-team"
) -> dict[str, Any]:
    """
    Run the full research → writer pipeline.

    Args:
        topic: The research topic to investigate.
        memanto_agent_id: Memanto agent namespace for shared memory.

    Returns:
        The final state after the graph completes.
    """
    import os

    from langgraph_memanto import create_memanto_tools
    from memanto.cli.client.sdk_client import SdkClient

    client = SdkClient(api_key=os.environ.get("MOORCHEH_API_KEY", ""))
    tools = create_memanto_tools(client, memanto_agent_id)

    compiled = compile_graph(tools)

    initial_state = {
        "messages": [],
        "memanto_agent_id": memanto_agent_id,
        "research_topic": topic,
        "findings": [],
    }

    return compiled.invoke(initial_state)


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()

    topic = os.getenv("RESEARCH_TOPIC", "AI agent framework market size and trends")
    agent_id = os.getenv("MEMANTO_AGENT_ID", "langgraph-research-team")

    print("Running LangGraph + Memanto research pipeline...")
    print(f"Topic: {topic}")
    print(f"Memanto Agent ID: {agent_id}")
    print("---")

    result = run_research(topic, agent_id)

    print("\n=== Final Output ===")
    for msg in result.get("messages", []):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        print(f"\n[{role.upper()}]\n{content}")
