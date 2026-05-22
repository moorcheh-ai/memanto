"""
Pre-built LangGraph workflow with Memanto persistent memory.

Provides a ready-to-use LangGraph StateGraph that demonstrates the three
Memanto primitives (remember, recall, answer) in a customer-support
workflow with cross-session memory persistence.

Architecture::

    ┌─────────────────────────────────────────────────────┐
    │              LangGraph + Memanto Workflow            │
    │                                                      │
    │  QUERY ──▶ CLASSIFY ──┬──▶ LOOKUP (recall) ──▶ RESPOND │
    │                       │                              │
    │                       ├──▶ SAVE (remember) ──▶ RESPOND │
    │                       │                              │
    │                       └──▶ ANSWER (RAG)    ──▶ RESPOND │
    │                                                      │
    │              Memanto (persistent memory layer)        │
    └─────────────────────────────────────────────────────┘

Usage::

    from langgraph_memanto import create_memanto_agent

    agent = create_memanto_agent(
        moorcheh_api_key="...",
        openai_api_key="...",
        agent_id="support-agent",
    )

    # Session 1: Store customer context
    result = agent.invoke({
        "query": "Customer prefers email communication and has a billing issue",
        "session_id": "session-1",
    })

    # Session 2 (different session): Recall previous context
    result = agent.invoke({
        "query": "What do we know about this customer's preferences?",
        "session_id": "session-2",
    })
"""

from __future__ import annotations

import os
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from memanto.cli.client.sdk_client import SdkClient

from .setup import MemantoSetup
from .tools import create_memanto_tools


# ─── Graph State ───────────────────────────────────────────────


class AgentState(BaseModel):
    """
    State that flows through the LangGraph workflow.

    Note: Memanto memories are NOT stored here — they persist
    in Memanto across sessions. This state is ephemeral per-invoke.
    """

    query: str = Field(default="", description="The user's query/question")
    session_id: str = Field(default="default", description="Current session identifier")
    classification: str = Field(
        default="unknown",
        description="Query classification: recall, remember, or answer",
    )
    tool_result: str = Field(default="", description="Result from Memanto tool invocation")
    final_response: str = Field(default="", description="Final response to user")
    memories_found: int = Field(default=0, description="Number of memories found/recalled")
    memories_stored: int = Field(default=0, description="Number of memories stored this invoke")


# ─── Classification Schema ─────────────────────────────────────


class QueryClassification(BaseModel):
    """Structured output for query classification."""

    action: Literal["recall", "remember", "answer"] = Field(
        description=(
            "Classify the user's intent:\n"
            "- 'recall': User is asking about previously stored information, "
            "requesting history, or looking up past interactions.\n"
            "- 'remember': User is providing new information, preferences, "
            "decisions, facts, or context that should be saved for later.\n"
            "- 'answer': User is asking a complex question that requires "
            "synthesizing information from stored memories (RAG)."
        )
    )


# ─── Node Functions ────────────────────────────────────────────


def _make_classify_node(llm: ChatOpenAI):
    """Create the classify node that determines which Memanto primitive to use."""

    structured_llm = llm.with_structured_output(QueryClassification)

    def classify_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("query", "")

        prompt = [
            SystemMessage(content=(
                "You are a query classifier for a customer support agent with persistent memory. "
                "Classify the user's intent into one of three actions:\n\n"
                "- 'recall': The user is asking about previously stored information, "
                "requesting history, or looking up past interactions. Examples: "
                "'What do we know about this customer?', 'Show me previous decisions', "
                "'What was discussed about X?'\n\n"
                "- 'remember': The user is providing new information that should be saved. "
                "Examples: 'Customer prefers email', 'We decided to use option A', "
                "'The bug was in the auth module', 'Note that the API changed'\n\n"
                "- 'answer': The user is asking a complex question requiring synthesis "
                "of stored memories. Examples: 'What's the best approach given what we know?', "
                "'Summarize our findings on X', 'How should we handle this based on past cases?'"
            )),
            HumanMessage(content=f"Classify this query: {query}"),
        ]

        result = structured_llm.invoke(prompt)
        return {"classification": result.action}

    return classify_node


def _make_recall_node(memanto_tools: dict[str, Any]):
    """Create the recall node that searches Memanto for relevant memories."""

    recall_tool = memanto_tools["recall"]

    def recall_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("query", "")

        result = recall_tool.invoke({"query": query, "limit": 5})

        # Count memories found
        count = 0
        if "Found" in result:
            try:
                count = int(result.split("Found")[1].split("memories")[0].strip())
            except (ValueError, IndexError):
                count = 0

        return {"tool_result": result, "memories_found": count}

    return recall_node


def _make_remember_node(llm: ChatOpenAI, memanto_tools: dict[str, Any]):
    """Create the remember node that extracts and stores memories from the query."""

    remember_tool = memanto_tools["remember"]

    def remember_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("query", "")

        # Use LLM to extract structured memories from the query
        prompt = [
            SystemMessage(content=(
                "You are a memory extraction assistant. Given a user's message, "
                "extract the key information that should be stored as a persistent memory. "
                "Determine the most appropriate memory type, a concise title, and the "
                "full content. Also assign a confidence score (0.0-1.0).\n\n"
                "Memory types:\n"
                "- fact: Objective truths or data\n"
                "- preference: User/customer likes or dislikes\n"
                "- decision: Choices made or agreed upon\n"
                "- observation: Trends, patterns, or notices\n"
                "- instruction: How-tos or directives\n"
                "- commitment: Promises or next steps\n"
                "- context: Background information\n"
                "- event: Occurrences or meetings\n"
                "- error: Failures or mistakes\n"
                "- learning: Insights or lessons learned\n\n"
                "Respond with a JSON object containing:\n"
                '{"memory_type": "...", "title": "...", "content": "...", "confidence": 0.0-1.0, "tags": "..."}'
            )),
            HumanMessage(content=f"Extract memory from this message: {query}"),
        ]

        response = llm.invoke(prompt)

        # Parse the LLM response
        try:
            import json
            text = response.content
            # Try to extract JSON from the response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            memory_data = json.loads(text.strip())
        except (json.JSONDecodeError, IndexError):
            # Fallback: store the raw query as a fact
            memory_data = {
                "memory_type": "fact",
                "title": query[:80],
                "content": query,
                "confidence": 0.7,
                "tags": "auto-extracted",
            }

        # Store in Memanto
        result = remember_tool.invoke({
            "memory_type": memory_data.get("memory_type", "fact"),
            "title": memory_data.get("title", query[:80]),
            "content": memory_data.get("content", query),
            "confidence": memory_data.get("confidence", 0.8),
            "tags": memory_data.get("tags", ""),
        })

        return {"tool_result": result, "memories_stored": 1}

    return remember_node


def _make_answer_node(memanto_tools: dict[str, Any]):
    """Create the answer node that generates RAG answers from Memanto."""

    answer_tool = memanto_tools["answer"]

    def answer_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("query", "")

        result = answer_tool.invoke({"question": query})

        return {"tool_result": result}

    return answer_node


def _make_respond_node(llm: ChatOpenAI):
    """Create the respond node that generates a final user-facing response."""

    def respond_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("query", "")
        classification = state.get("classification", "unknown")
        tool_result = state.get("tool_result", "")

        prompt = [
            SystemMessage(content=(
                "You are a helpful customer support agent with persistent memory. "
                "You have access to a long-term memory system that stores information "
                "across sessions. Based on the memory operation result below, "
                "generate a clear, helpful response to the user.\n\n"
                "If memories were recalled, reference them naturally. "
                "If a memory was stored, confirm it was saved. "
                "If an answer was generated from memories, present it clearly. "
                "Always be conversational and helpful."
            )),
            HumanMessage(content=(
                f"Query: {query}\n"
                f"Action taken: {classification}\n"
                f"Memory operation result:\n{tool_result}\n\n"
                "Generate a helpful response for the user."
            )),
        ]

        response = llm.invoke(prompt)
        return {"final_response": response.content}

    return respond_node


# ─── Graph Construction ────────────────────────────────────────


def build_memanto_graph(
    llm: ChatOpenAI,
    memanto_tools: dict[str, Any],
) -> StateGraph:
    """
    Build the LangGraph workflow with Memanto memory integration.

    The graph follows this flow:
        CLASSIFY → [recall | remember | answer] → RESPOND

    Args:
        llm: A ChatOpenAI instance for LLM calls.
        memanto_tools: Dict of Memanto tools from ``create_memanto_tools()``.

    Returns:
        A compiled LangGraph StateGraph ready for ``.invoke()``.
    """

    # Create the graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("classify", _make_classify_node(llm))
    graph.add_node("recall", _make_recall_node(memanto_tools))
    graph.add_node("remember", _make_remember_node(llm, memanto_tools))
    graph.add_node("answer", _make_answer_node(memanto_tools))
    graph.add_node("respond", _make_respond_node(llm))

    # Set entry point
    graph.set_entry_point("classify")

    # Add conditional edges from classify
    def route_by_classification(state: dict[str, Any]) -> str:
        classification = state.get("classification", "recall")
        if classification == "remember":
            return "remember"
        elif classification == "answer":
            return "answer"
        else:
            return "recall"

    graph.add_conditional_edges(
        "classify",
        route_by_classification,
        {
            "recall": "recall",
            "remember": "remember",
            "answer": "answer",
        },
    )

    # All tool nodes flow to respond
    graph.add_edge("recall", "respond")
    graph.add_edge("remember", "respond")
    graph.add_edge("answer", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


# ─── Factory ───────────────────────────────────────────────────


def create_memanto_agent(
    moorcheh_api_key: str | None = None,
    openai_api_key: str | None = None,
    model: str = "gpt-4o-mini",
    agent_id: str = "langgraph-support-agent",
    pattern: str = "support",
    scope_id: str = "support",
    session_duration_hours: int = 6,
) -> Any:
    """
    Create and return a compiled LangGraph agent with Memanto memory.

    This is the main entry point. It handles:
    1. Creating/activating the Memanto agent
    2. Building the LangGraph workflow
    3. Returning a ready-to-use compiled graph

    Args:
        moorcheh_api_key: Moorcheh API key (or set MOORCHEH_API_KEY env var).
        openai_api_key: OpenAI API key (or set OPENAI_API_KEY env var).
        model: LLM model to use for classification and response generation.
        agent_id: Unique agent identifier for Memanto.
        pattern: Memanto agent pattern ('support', 'project', or 'tool').
        scope_id: Memory scope for isolation.
        session_duration_hours: Session lifetime in hours.

    Returns:
        Compiled LangGraph agent ready for ``.invoke()``.

    Example::

        agent = create_memanto_agent(
            agent_id="billing-support",
            pattern="support",
        )

        # Session 1: Store customer info
        result = agent.invoke({
            "query": "Customer Alice prefers phone contact and has a billing dispute",
        })

        # Session 2 (different process, next day): Recall
        result = agent.invoke({
            "query": "What are Alice's communication preferences?",
        })
    """
    # Resolve API keys
    moorcheh_key = moorcheh_api_key or os.environ.get("MOORCHEH_API_KEY", "")
    openai_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")

    if not moorcheh_key:
        raise ValueError(
            "MOORCHEH_API_KEY is required. Set it in .env or pass moorcheh_api_key."
        )

    # Initialize LLM
    llm = ChatOpenAI(
        model=model,
        api_key=openai_key,
        temperature=0.3,
    )

    # Setup Memanto agent
    setup = MemantoSetup(api_key=moorcheh_key)
    client = setup.setup(
        agent_id=agent_id,
        pattern=pattern,
        duration_hours=session_duration_hours,
    )

    # Create Memanto tools
    memanto_tools = create_memanto_tools(client, agent_id)

    # Build and return the graph
    return build_memanto_graph(llm, memanto_tools)
