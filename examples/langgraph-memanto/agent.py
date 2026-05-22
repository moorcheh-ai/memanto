"""
LangGraph Research Agent with Memanto Persistent Memory.

Workflow:
  QUERY → RESEARCH → EVALUATE → RESPOND

- RESEARCH: Simulates information gathering (web search + knowledge)
- EVALUATE: Checks Memanto for prior memories, stores new findings
- RESPOND: Generates final answer enriched with recalled context
"""

import os
import json
from typing import Any, TypedDict, Annotated
from datetime import datetime

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from memanto_tool import MemantoTool


# ─── Graph State ───────────────────────────────────────────────

class AgentState(TypedDict):
    """State that flows through the LangGraph workflow.

    Note: Memanto memories are NOT stored here — they persist
    in Memanto across sessions. This state is ephemeral.
    """
    query: str
    session_id: str
    research_notes: list[str]
    recalled_memories: list[dict[str, Any]]
    new_memories: list[dict[str, Any]]
    final_answer: str


# ─── Nodes ─────────────────────────────────────────────────────

def research_node(state: AgentState, *, llm: ChatOpenAI) -> dict:
    """Gather information on the query using the LLM as a research assistant."""
    query = state["query"]

    prompt = [
        SystemMessage(content=(
            "You are a research assistant. Given a query, provide detailed findings "
            "as a numbered list of key facts, observations, and decisions. "
            "Be thorough and specific. Include sources where possible."
        )),
        HumanMessage(content=f"Research this topic: {query}"),
    ]

    response = llm.invoke(prompt)
    notes = [line.strip() for line in response.content.split("\n") if line.strip()]

    return {"research_notes": notes}


def evaluate_node(state: AgentState, *, memanto: MemantoTool) -> dict:
    """Check Memanto for prior memories and store new findings."""
    query = state["query"]
    notes = state.get("research_notes", [])

    # 1. Recall relevant memories from previous sessions
    recalled = memanto.recall(query=query, limit=5)

    # 2. Store new findings as typed memories
    new_memories = []
    for i, note in enumerate(notes[:5]):  # Store top 5 findings
        # Determine memory type based on content
        memory_type = _classify_note(note)
        confidence = 0.85 + (0.05 * (len(note) > 100))  # Longer notes get slightly higher confidence
        confidence = min(confidence, 0.95)

        try:
            result = memanto.remember(
                content=note,
                title=f"Research finding: {query[:40]}...",
                memory_type=memory_type,
                confidence=confidence,
                tags=["research", state.get("session_id", "default")],
            )
            new_memories.append(result)
        except Exception as e:
            new_memories.append({"error": str(e), "note": note[:50]})

    return {
        "recalled_memories": recalled,
        "new_memories": new_memories,
    }


def respond_node(state: AgentState, *, llm: ChatOpenAI) -> dict:
    """Generate a final answer enriched with recalled memories."""
    query = state["query"]
    notes = state.get("research_notes", [])
    recalled = state.get("recalled_memories", [])

    # Build context from recalled memories
    memory_context = ""
    if recalled:
        memory_context = "\n\n## Prior Knowledge (from Memanto memory):\n"
        for m in recalled[:5]:
            memory_context += (
                f"- [{m.get('type', 'unknown').upper()}] {m.get('content', '')} "
                f"(confidence: {m.get('confidence', 0):.2f})\n"
            )

    prompt = [
        SystemMessage(content=(
            "You are a knowledgeable research assistant with persistent memory. "
            "Synthesize the research notes and any prior knowledge into a comprehensive answer. "
            "If prior knowledge is available, explicitly reference it to show continuity "
            "across sessions."
        )),
        HumanMessage(content=(
            f"Query: {query}\n\n"
            f"## Research Notes:\n" + "\n".join(notes[:10]) + "\n"
            f"{memory_context}\n\n"
            "Please provide a comprehensive answer that incorporates both the new research "
            "and any prior knowledge. Make it clear when you're referencing information "
            "from previous sessions."
        )),
    ]

    response = llm.invoke(prompt)

    return {"final_answer": response.content}


# ─── Helper ────────────────────────────────────────────────────

def _classify_note(note: str) -> str:
    """Classify a research note into a Memanto memory type."""
    note_lower = note.lower()

    if any(kw in note_lower for kw in ["decided", "chose", "selected", "prefer", "recommend"]):
        return "decision"
    if any(kw in note_lower for kw in ["goal", "objective", "aim", "target"]):
        return "goal"
    if any(kw in note_lower for kw in ["should", "must", "always", "never", "rule"]):
        return "instruction"
    if any(kw in note_lower for kw in ["observed", "noticed", "found that", "discovered"]):
        return "observation"
    if any(kw in note_lower for kw in ["plan", "strategy", "approach", "method"]):
        return "goal"
    # Default to fact
    return "fact"


# ─── Graph Construction ────────────────────────────────────────

def build_graph(llm: ChatOpenAI, memanto: MemantoTool) -> StateGraph:
    """Build the LangGraph research agent workflow."""

    graph = StateGraph(AgentState)

    # Add nodes with bound dependencies
    graph.add_node("research", lambda state: research_node(state, llm=llm))
    graph.add_node("evaluate", lambda state: evaluate_node(state, memanto=memanto))
    graph.add_node("respond", lambda state: respond_node(state, llm=llm))

    # Define edges
    graph.set_entry_point("research")
    graph.add_edge("research", "evaluate")
    graph.add_edge("evaluate", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


# ─── Factory ───────────────────────────────────────────────────

def create_agent(
    moorcheh_api_key: str | None = None,
    openai_api_key: str | None = None,
    model: str = "gpt-4o-mini",
    agent_id: str = "langgraph-research-agent",
    scope_id: str = "research",
) -> Any:
    """Create and return a compiled LangGraph agent with Memanto memory.

    Args:
        moorcheh_api_key: Moorcheh API key (or set MOORCHEH_API_KEY env var)
        openai_api_key: OpenAI API key (or set OPENAI_API_KEY env var)
        model: LLM model to use
        agent_id: Unique agent identifier for Memanto
        scope_id: Memory scope for isolation

    Returns:
        Compiled LangGraph agent
    """
    llm = ChatOpenAI(
        model=model,
        api_key=openai_api_key or os.environ.get("OPENAI_API_KEY"),
        temperature=0.3,
    )

    memanto = MemantoTool(
        agent_id=agent_id,
        scope_id=scope_id,
        moorcheh_api_key=moorcheh_api_key,
    )

    return build_graph(llm, memanto)
