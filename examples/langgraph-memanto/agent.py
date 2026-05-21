"""
LangGraph Customer Support Agent with Memanto Long-Term Memory

This module defines a LangGraph StateGraph workflow that uses Memanto as
its persistent memory layer. The agent can:

  1. Recall past customer interactions from memory
  2. Generate contextual responses using recalled history
  3. Store new learnings (preferences, issues, resolutions) for future use

Architecture:
    ┌──────────┐    ┌──────────────┐    ┌────────────────┐
    │  START   │───>│ recall_memory│───>│ generate_reply │
    └──────────┘    └──────────────┘    └────────────────┘
                                                │
                                    ┌───────────┴───────────┐
                                    │                       │
                                    v                       v
                            ┌──────────────┐        ┌──────────┐
                            │ store_memory │        │   END    │
                            └──────────────┘        └──────────┘
                                    │
                                    v
                              ┌──────────┐
                              │   END    │
                              └──────────┘

The "should_store" edge checks whether the conversation revealed new
information worth persisting (preferences, issues, resolutions).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from memanto_tools import MemantoToolkit, format_memories_for_context

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class SupportAgentState:
    """
    State for the customer support agent graph.

    Attributes:
        messages: Conversation message history (auto-reduced by LangGraph).
        customer_id: Identifier for the customer (used as Memanto agent_id).
        recalled_memories: Memories recalled from Memanto for context.
        memory_context: Formatted string of recalled memories for the LLM.
        should_store: Whether the latest exchange should be persisted.
        store_payload: Structured data to store in Memanto.
    """

    messages: Annotated[list[BaseMessage], add_messages] = field(default_factory=list)
    customer_id: str = ""
    recalled_memories: list[dict[str, Any]] = field(default_factory=list)
    memory_context: str = ""
    should_store: bool = False
    store_payload: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def make_recall_node(toolkit: MemantoToolkit):
    """
    Create a node that recalls relevant memories from Memanto.

    Uses the latest user message as the recall query. Injects recalled
    memories into state as context for the reply generator.
    """

    def recall_memory(state: SupportAgentState) -> dict[str, Any]:
        messages = state.messages
        if not messages:
            return {"recalled_memories": [], "memory_context": ""}

        # Use the latest user message as the recall query
        last_user_msg = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                last_user_msg = msg.content
                break

        if not last_user_msg:
            return {"recalled_memories": [], "memory_context": ""}

        logger.info("Recalling memories for query: %s", last_user_msg[:80])
        result = toolkit.recall(query=last_user_msg, limit=5)
        memories = result.get("memories", [])
        context = format_memories_for_context(memories)

        logger.info("Recalled %d memories", len(memories))
        return {
            "recalled_memories": memories,
            "memory_context": context,
        }

    return recall_memory


def make_generate_reply_node(toolkit: MemantoToolkit, llm: ChatOpenAI):
    """
    Create a node that generates a support reply using the LLM.

    The LLM receives:
      - A system prompt explaining its role
      - Recalled memory context
      - The conversation history
    """

    def generate_reply(state: SupportAgentState) -> dict[str, Any]:
        memory_context = state.memory_context or "No prior context available."

        system_prompt = (
            "You are a helpful, empathetic customer support agent. "
            "You have access to the customer's history and preferences "
            "from previous interactions.\n\n"
            "## Customer Memory Context\n"
            f"{memory_context}\n\n"
            "## Instructions\n"
            "- Use the memory context to personalize your responses.\n"
            "- If you see past issues or preferences, acknowledge them.\n"
            "- Be concise, friendly, and solution-oriented.\n"
            "- If no memory context is available, respond naturally and "
            "ask clarifying questions."
        )

        llm_messages = [SystemMessage(content=system_prompt)]
        llm_messages.extend(state.messages)

        logger.info("Generating reply with %d recalled memories", len(state.recalled_memories))
        response = llm.invoke(llm_messages)

        return {"messages": [response]}

    return generate_reply


def make_classify_node(llm: ChatOpenAI):
    """
    Create a node that classifies whether the conversation contains
    information worth storing in long-term memory.

    Returns a dict with 'should_store' and 'store_payload'.
    """

    def classify_and_store(state: SupportAgentState) -> dict[str, Any]:
        # Build a summary of the conversation for classification
        conversation = []
        for msg in state.messages[-6:]:  # Last 6 messages
            role = "User" if isinstance(msg, HumanMessage) else "Agent"
            conversation.append(f"{role}: {msg.content}")

        conversation_text = "\n".join(conversation)

        classify_prompt = (
            "Analyze this customer support conversation and determine if it "
            "contains information worth remembering for future interactions.\n\n"
            "Worth remembering includes:\n"
            "- Customer preferences (communication style, product preferences)\n"
            "- Reported issues and their resolutions\n"
            "- Important decisions or commitments\n"
            "- Customer feedback or sentiments\n\n"
            "NOT worth remembering:\n"
            "- Generic greetings or small talk\n"
            "- Already-known information\n"
            "- Vague or unhelpful statements\n\n"
            f"Conversation:\n{conversation_text}\n\n"
            "Respond with JSON only:\n"
            '{"should_store": true/false, "memory_type": "type", '
            '"title": "short title", "content": "what to remember", '
            '"confidence": 0.0-1.0, "tags": ["tag1", "tag2"]}\n\n'
            "If nothing is worth storing, set should_store to false and "
            "leave other fields empty."
        )

        response = llm.invoke([HumanMessage(content=classify_prompt)])
        raw = response.content.strip()

        # Parse JSON from response (handle markdown code blocks)
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to parse classification response: %s", raw[:200])
            return {"should_store": False, "store_payload": {}}

        should_store = parsed.get("should_store", False)

        if should_store:
            payload = {
                "memory_type": parsed.get("memory_type", "observation"),
                "title": parsed.get("title", "Customer interaction"),
                "content": parsed.get("content", ""),
                "confidence": parsed.get("confidence", 0.8),
                "tags": parsed.get("tags", []),
            }
            logger.info("Classification: store memory '%s'", payload["title"])
            return {"should_store": True, "store_payload": payload}

        logger.info("Classification: nothing worth storing")
        return {"should_store": False, "store_payload": {}}

    return classify_and_store


def make_store_node(toolkit: MemantoToolkit):
    """
    Create a node that stores classified information in Memanto.
    Only executes if should_store is True.
    """

    def store_memory(state: SupportAgentState) -> dict[str, Any]:
        if not state.should_store or not state.store_payload:
            return {}

        payload = state.store_payload
        logger.info(
            "Storing memory: [%s] %s",
            payload.get("memory_type"),
            payload.get("title"),
        )

        result = toolkit.remember(
            memory_type=payload.get("memory_type", "observation"),
            title=payload.get("title", "Customer interaction"),
            content=payload.get("content", ""),
            confidence=payload.get("confidence", 0.8),
            tags=payload.get("tags", []),
        )

        logger.info("Memory stored with ID: %s", result.get("memory_id"))
        return {}

    return store_memory


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------


def should_store(state: SupportAgentState) -> Literal["store_memory", "__end__"]:
    """Decide whether to store new memories or end."""
    if state.should_store and state.store_payload:
        return "store_memory"
    return "__end__"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_support_agent_graph(
    toolkit: MemantoToolkit,
    model: str = "gpt-4o-mini",
    openai_api_key: str | None = None,
    openai_base_url: str | None = None,
) -> StateGraph:
    """
    Build the LangGraph customer support agent workflow.

    Args:
        toolkit: Initialized MemantoToolkit (call setup() first).
        model: OpenAI model name.
        openai_api_key: OpenAI API key (falls back to OPENAI_API_KEY env).
        openai_base_url: Optional base URL for OpenAI-compatible APIs.

    Returns:
        Compiled StateGraph ready to invoke.
    """
    # Initialize LLM
    llm_kwargs: dict[str, Any] = {"model": model, "temperature": 0.3}
    if openai_api_key:
        llm_kwargs["api_key"] = openai_api_key
    if openai_base_url:
        llm_kwargs["base_url"] = openai_base_url

    llm = ChatOpenAI(**llm_kwargs)

    # Build graph
    graph = StateGraph(SupportAgentState)

    # Add nodes
    graph.add_node("recall_memory", make_recall_node(toolkit))
    graph.add_node("generate_reply", make_generate_reply_node(toolkit, llm))
    graph.add_node("classify_exchange", make_classify_node(llm))
    graph.add_node("store_memory", make_store_node(toolkit))

    # Add edges
    graph.add_edge(START, "recall_memory")
    graph.add_edge("recall_memory", "generate_reply")
    graph.add_edge("generate_reply", "classify_exchange")
    graph.add_conditional_edges(
        "classify_exchange",
        should_store,
        {
            "store_memory": "store_memory",
            "__end__": END,
        },
    )
    graph.add_edge("store_memory", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------


def run_conversation(
    graph,
    customer_id: str,
    user_message: str,
    existing_messages: list[BaseMessage] | None = None,
) -> list[BaseMessage]:
    """
    Run a single conversation turn through the graph.

    Args:
        graph: Compiled LangGraph graph.
        customer_id: Customer identifier.
        user_message: The user's message.
        existing_messages: Previous conversation messages for continuity.

    Returns:
        Updated message list including the new exchange.
    """
    messages = list(existing_messages or [])
    messages.append(HumanMessage(content=user_message))

    result = graph.invoke(
        {
            "messages": messages,
            "customer_id": customer_id,
        }
    )

    return result["messages"]
