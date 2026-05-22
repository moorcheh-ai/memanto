"""
LangGraph + Memanto: Research Assistant with Persistent Memory

This module defines a LangGraph workflow for a research assistant agent
that uses Memanto as its long-term memory layer. The key innovation is
that memories persist across sessions — the agent can recall information
stored "yesterday" that isn't in the current thread's state.

Architecture:
    User → Supervisor → [Research Node | Recall Node | Synthesize Node] → Response
    
    - Research Node: Gathers information and stores findings as Memanto memories
    - Recall Node: Retrieves relevant memories from previous sessions  
    - Synthesize Node: Combines new findings with recalled memories for output
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from memanto_langgraph_tools import MemantoSetup, create_memanto_tools

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MOORCHEH_API_KEY = os.environ.get("MOORCHEH_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
AGENT_ID = "langgraph-research-assistant"

# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------


from typing import TypedDict


class ResearchState(TypedDict):
    """State for the research assistant workflow."""

    messages: list[Any]
    next_step: str  # "research", "recall", "synthesize", or "done"
    research_findings: list[str]
    recalled_memories: list[str]
    final_output: str


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def create_research_graph(
    moorcheh_api_key: str | None = None,
    openai_api_key: str | None = None,
    agent_id: str = AGENT_ID,
    model_name: str = "gpt-4o-mini",
) -> tuple[CompiledStateGraph, MemantoSetup]:
    """
    Build a LangGraph research assistant powered by Memanto memory.

    The graph has three main nodes:
    1. **recall_node**: Searches Memanto for relevant memories from
       previous sessions. This is the key differentiator — the agent
       remembers context that isn't in the current LangGraph state.
    2. **research_node**: An LLM-backed agent that uses Memanto's
       remember tool to store new findings as persistent memories.
    3. **synthesize_node**: Combines recalled memories with new
       findings into a coherent response.

    Args:
        moorcheh_api_key: Moorcheh API key (defaults to env var).
        openai_api_key: OpenAI API key (defaults to env var).
        agent_id: Memanto agent identifier.
        model_name: OpenAI model to use.

    Returns:
        Tuple of (compiled graph, MemantoSetup for cleanup).
    """
    api_key = moorcheh_api_key or MOORCHEH_API_KEY
    oai_key = openai_api_key or OPENAI_API_KEY

    if not api_key:
        raise ValueError("MOORCHEH_API_KEY is required")

    # Set up Memanto
    setup = MemantoSetup(api_key=api_key)
    client = setup.setup(
        agent_id=agent_id,
        pattern="tool",
        description="LangGraph research assistant with persistent Memanto memory",
        duration_hours=6,
    )

    # Create Memanto-powered tools
    tools = create_memanto_tools(client=client, agent_id=agent_id)

    # Build a ReAct agent node that can use Memanto tools
    # This agent stores research findings as persistent memories
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model=model_name, api_key=oai_key) if oai_key else None

    if llm is None:
        raise ValueError("OPENAI_API_KEY is required for LLM-powered nodes")

    research_agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=(
            "You are a research assistant with persistent memory powered by Memanto. "
            "You have three tools: memanto_remember (store memories), memanto_recall "
            "(search memories), and memanto_answer (RAG over memories).\n\n"
            "IMPORTANT: Your memories persist across sessions. When you research a "
            "topic, always store key findings as memories so they're available in "
            "future sessions. When asked about past research, use memanto_recall to "
            "find what was stored previously.\n\n"
            "Store each finding as an atomic memory with the appropriate type "
            "(fact, observation, learning, etc.) and confidence score."
        ),
    )

    # -----------------------------------------------------------------------
    # Node functions
    # -----------------------------------------------------------------------

    def route_query(state: ResearchState) -> Command:
        """Determine the next step based on the user's message."""
        last_message = state["messages"][-1]
        if isinstance(last_message, HumanMessage):
            content = last_message.content.lower()

            # If the user is asking about past research, recall first
            recall_triggers = [
                "what did you find",
                "what do you remember",
                "previous research",
                "yesterday",
                "last time",
                "what have we",
                "recall",
                "from before",
                "earlier findings",
            ]
            if any(trigger in content for trigger in recall_triggers):
                return Command(goto="recall", update={"next_step": "recall"})

            # If the user wants new research, go to research node
            research_triggers = [
                "research",
                "investigate",
                "look into",
                "find out",
                "analyze",
                "explore",
            ]
            if any(trigger in content for trigger in research_triggers):
                return Command(goto="research", update={"next_step": "research"})

        # Default: go to research (which can both recall and store)
        return Command(goto="research", update={"next_step": "research"})

    def recall_node(state: ResearchState) -> dict:
        """Recall relevant memories from previous sessions."""
        last_message = state["messages"][-1]
        query = last_message.content if isinstance(last_message, HumanMessage) else str(last_message)

        # Use the recall tool directly
        recall_tool = tools[1]  # memanto_recall
        result = recall_tool.invoke({"query": query, "limit": 10})

        recalled = state.get("recalled_memories", [])
        recalled.append(result)

        return {
            "recalled_memories": recalled,
            "next_step": "synthesize",
            "messages": [
                AIMessage(
                    content=f"I searched my persistent memory for relevant information...\n\n{result}"
                )
            ],
        }

    def research_node(state: ResearchState) -> dict:
        """Run the research agent with Memanto memory tools."""
        result = research_agent.invoke({"messages": state["messages"]})

        # Extract the agent's response
        agent_messages = result.get("messages", [])
        findings = state.get("research_findings", [])

        for msg in agent_messages:
            if isinstance(msg, AIMessage) and msg.content:
                findings.append(msg.content)

        return {
            "messages": agent_messages,
            "research_findings": findings,
            "next_step": "done",
        }

    def synthesize_node(state: ResearchState) -> dict:
        """Combine recalled memories with new findings into a coherent response."""
        recalled = "\n".join(state.get("recalled_memories", []))
        findings = "\n".join(state.get("research_findings", []))

        prompt = (
            f"Synthesize the following information into a clear, comprehensive response.\n\n"
            f"## Recalled from Previous Sessions:\n{recalled}\n\n"
            f"## New Research Findings:\n{findings}\n\n"
            f"Provide a well-organized summary that integrates both sources. "
            f"Clearly indicate which information comes from previous sessions "
            f"(demonstrating cross-session recall) versus new findings."
        )

        response = llm.invoke([HumanMessage(content=prompt)])

        return {
            "messages": [response],
            "final_output": response.content,
            "next_step": "done",
        }

    # -----------------------------------------------------------------------
    # Build the graph
    # -----------------------------------------------------------------------

    graph = StateGraph(ResearchState)

    # Add nodes
    graph.add_node("recall", recall_node)
    graph.add_node("research", research_node)
    graph.add_node("synthesize", synthesize_node)

    # Add conditional routing from START
    graph.add_conditional_edges(START, route_query)

    # After recall, go to synthesize
    graph.add_edge("recall", "synthesize")

    # After synthesize, end
    graph.add_edge("synthesize", END)

    # After research, end (the ReAct agent handles its own flow)
    graph.add_edge("research", END)

    compiled = graph.compile()
    return compiled, setup


# ---------------------------------------------------------------------------
# Convenience: Simple single-agent approach (no custom graph needed)
# ---------------------------------------------------------------------------


def create_simple_research_agent(
    moorcheh_api_key: str | None = None,
    openai_api_key: str | None = None,
    agent_id: str = AGENT_ID,
    model_name: str = "gpt-4o-mini",
) -> tuple[CompiledStateGraph, MemantoSetup]:
    """
    Create a simple ReAct agent with Memanto memory tools.

    This is the simplest way to add persistent memory to a LangGraph agent.
    The agent uses memanto_remember to store findings and memanto_recall
    to retrieve them — even from previous sessions.

    Args:
        moorcheh_api_key: Moorcheh API key (defaults to env var).
        openai_api_key: OpenAI API key (defaults to env var).
        agent_id: Memanto agent identifier.
        model_name: OpenAI model to use.

    Returns:
        Tuple of (compiled agent, MemantoSetup for cleanup).
    """
    api_key = moorcheh_api_key or MOORCHEH_API_KEY
    oai_key = openai_api_key or OPENAI_API_KEY

    if not api_key:
        raise ValueError("MOORCHEH_API_KEY is required")

    setup = MemantoSetup(api_key=api_key)
    client = setup.setup(
        agent_id=agent_id,
        pattern="tool",
        description="LangGraph research assistant with persistent Memanto memory",
        duration_hours=6,
    )

    tools = create_memanto_tools(client=client, agent_id=agent_id)

    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model=model_name, api_key=oai_key) if oai_key else None
    if llm is None:
        raise ValueError("OPENAI_API_KEY is required")

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=(
            "You are a research assistant with persistent long-term memory powered by Memanto.\n\n"
            "## Your Memory Tools\n"
            "- **memanto_remember**: Store a memory that persists across sessions. "
            "Use this whenever you discover an important fact, make a decision, or learn something new.\n"
            "- **memanto_recall**: Search your persistent memories. This searches across ALL past sessions — "
            "memories stored yesterday, last week, or months ago are all retrievable.\n"
            "- **memanto_answer**: Get an AI-generated answer grounded in your stored memories (RAG).\n\n"
            "## Cross-Session Recall (Key Feature)\n"
            "Your Memanto memory is NOT tied to the current conversation. When a new session starts, "
            "your LangGraph state is empty, but your Memanto memories persist. This means:\n"
            "1. Always use memanto_recall before starting new research to check what you already know.\n"
            "2. Store every important finding with memanto_remember so future sessions can access it.\n"
            "3. When someone asks 'what did we find yesterday?', use memanto_recall to retrieve it.\n\n"
            "## Memory Storage Best Practices\n"
            "- Use the correct memory type (fact, observation, learning, decision, etc.)\n"
            "- Set confidence appropriately (1.0 for verified facts, 0.7-0.85 for estimates)\n"
            "- Add relevant tags for better future retrieval\n"
            "- Keep each memory atomic — one fact per memory\n"
        ),
    )

    return agent, setup
