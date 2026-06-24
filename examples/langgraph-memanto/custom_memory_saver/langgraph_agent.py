"""
LangGraph + Memanto: Customer Support Agent with Persistent Memory

This agent demonstrates Cross-Session Recall:
  Session 1: User shares preferences → Agent stores them as Memanto memories
  Session 2: User returns → Agent recalls those memories automatically

Architecture:
  ┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
  │  User Input │ ──▶ │  recall_memory   │ ──▶ │ agent_node   │
  └─────────────┘     └──────────────────┘     └──────────────┘
                                                     │
                ┌──────────────────────────┐         │
                │ remember_memory          │ ◀───────┘
                │ (store new info)         │
                └──────────────────────────┘
                           │
                           ▼
                ┌──────────────────────────┐
                │ End / loop back          │
                └──────────────────────────┘

Run with:
    python run_demo.py          # Quick demo (both sessions)
    python run_demo.py --session 1   # Session 1 only
    python run_demo.py --session 2   # Session 2 only (proves persistence!)
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from memanto.cli.client.sdk_client import SdkClient

load_dotenv()

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    """The LangGraph state for our customer-support agent."""

    messages: Annotated[list, add_messages]
    user_id: str
    session_id: str
    memories_recalled: bool  # whether we've already recalled memories this session
    memories_stored: bool  # whether we've stored memories this session


# ---------------------------------------------------------------------------
# LLM setup  (provider-agnostic — swap in your preferred client)
# ---------------------------------------------------------------------------


def _get_llm():
    """Return an LLM instance.

    Respects the LLM_MODEL env var.  Falls back to a simple HTTP wrapper
    so the example works without langchain LLM packages.
    """
    model = os.getenv("LLM_MODEL", "openrouter/openai/gpt-4o-mini")
    provider, _, model_name = model.partition("/")

    # ---- OpenRouter (default) ----
    if provider == "openrouter":
        return _OpenRouterLLM(model_name)
    # ---- OpenAI ----
    if provider == "openai":
        return _OpenAILLM(model_name)
    # ---- Anthropic ----
    if provider == "anthropic":
        return _AnthropicLLM(model_name)

    # Fallback: raw HTTP with OpenRouter-style API
    return _OpenRouterLLM(model_name)


class _OpenRouterLLM:
    """Minimal LLM wrapper using OpenRouter's chat completions API."""

    def __init__(self, model: str = "openai/gpt-4o-mini"):
        self.model = model
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")

    def invoke(self, messages: list[dict]) -> str:
        import httpx

        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.3,
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


class _OpenAILLM:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.api_key = os.getenv("OPENAI_API_KEY", "")

    def invoke(self, messages: list[dict]) -> str:
        import httpx

        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "messages": messages, "temperature": 0.3},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


class _AnthropicLLM:
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")

    def invoke(self, messages: list[dict]) -> str:
        import httpx

        # Convert OpenAI-style messages to Anthropic format
        system_msg = None
        anthropic_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                anthropic_messages.append(
                    {
                        "role": "assistant" if m["role"] == "assistant" else "user",
                        "content": m["content"],
                    }
                )

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": anthropic_messages,
        }
        if system_msg:
            payload["system"] = system_msg

        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]


# ---------------------------------------------------------------------------
# Memanto initialisation
# ---------------------------------------------------------------------------


def get_client() -> SdkClient:
    """Create a Memanto SdkClient instance."""
    api_key = os.getenv("MOORCHEH_API_KEY", "")
    return SdkClient(api_key=api_key)


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def recall_memory_node(state: AgentState, client: SdkClient) -> dict:
    """Recall relevant memories from previous sessions and inject them as context."""
    if state.get("memories_recalled"):
        return {}

    # Extract the user's query from the latest message
    latest = state["messages"][-1] if state["messages"] else None
    query = latest.content if latest and hasattr(latest, "content") else ""

    # Ensure agent is initialized and session is active
    try:
        client.create_agent("langgraph-customer-support", pattern="tool")
    except Exception:
        pass
    client.activate_agent("langgraph-customer-support")

    # Search Memanto for relevant memories
    res = client.recall(agent_id="langgraph-customer-support", query=query, limit=10)
    memories = res.get("memories", [])

    if memories:
        lines = []
        for i, m in enumerate(memories, 1):
            lines.append(
                f"  [{i}] ({m.get('type', 'fact')}, confidence={m.get('confidence', 'N/A')}) {m.get('content', '')}"
            )
        context = "\n".join(lines)

        context_msg = SystemMessage(
            content=(
                "The following information was recalled from the user's long-term memory "
                "(stored in previous sessions). Use it to personalise your response:\n\n"
                f"{context}"
            )
        )
        return {"messages": [context_msg], "memories_recalled": True}

    return {"memories_recalled": True}


def agent_node(state: AgentState, llm, client: SdkClient) -> dict:
    """The main agent node that chats with the user."""
    # Build message list for the LLM
    system_prompt = (
        "You are a helpful customer support agent with access to long-term memory.\n\n"
        "Guidelines:\n"
        "1. Use any recalled memories to personalise your response.\n"
        "2. If the user shares preferences, personal info, or issues,\n"
        "   note them so they can be stored as memories.\n"
        "3. Be concise and friendly.\n"
        "4. Keep track of the user's name, preferences, and ongoing issues\n"
        "   so you never ask the same question twice.\n"
    )

    messages_for_llm = [{"role": "system", "content": system_prompt}]
    for msg in state["messages"]:
        if hasattr(msg, "type") and msg.type == "system":
            # Forward injected recall context to the model
            messages_for_llm.append({"role": "system", "content": str(msg.content)})
            continue
        role = "user" if getattr(msg, "type", "") == "human" else "assistant"
        messages_for_llm.append({"role": role, "content": str(msg.content)})

    # Get LLM response
    response_text = llm.invoke(messages_for_llm)
    response_msg = AIMessage(content=response_text)

    return {"messages": [response_msg]}


def remember_memory_node(state: AgentState, client: SdkClient) -> dict:
    """Extract key information from the conversation and store as memories."""
    if state.get("memories_stored"):
        return {}

    memories_stored_this_cycle = []

    # Look through all messages for user-provided facts worth remembering
    for msg in state["messages"]:
        if hasattr(msg, "type") and msg.type == "human":
            content = str(msg.content)

            # Detect and store preferences
            if any(
                kw in content.lower()
                for kw in [
                    "prefer",
                    "like",
                    "love",
                    "hate",
                    "don't like",
                    "my name is",
                    "i am ",
                    "i'm ",
                    "my email",
                    "contact me",
                    "issue",
                    "problem",
                    "bug",
                ]
            ):
                memories_stored_this_cycle.append(
                    {
                        "content": content[:500],
                        "type": "preference",
                        "title": "Observation",
                        "source": "langgraph-agent",
                        "confidence": 0.85,
                    }
                )

            # Detect explicit facts
            if any(
                kw in content.lower()
                for kw in ["fact:", "remember that", "note that", "important:"]
            ):
                memories_stored_this_cycle.append(
                    {
                        "content": content[:500],
                        "type": "fact",
                        "title": "Observation",
                        "source": "langgraph-agent",
                        "confidence": 0.85,
                    }
                )

    # Also store the key takeaway from the agent's response
    for msg in reversed(state["messages"]):
        if hasattr(msg, "type") and msg.type == "ai" and msg.content:
            memories_stored_this_cycle.append(
                {
                    "content": f"Agent helped with: {msg.content[:300]}",
                    "type": "learning",
                    "title": "Observation",
                    "source": "langgraph-agent",
                    "confidence": 0.85,
                }
            )
            break

    if memories_stored_this_cycle:
        client.batch_remember(
            agent_id="langgraph-customer-support", memories=memories_stored_this_cycle
        )

    return {"memories_stored": True}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_agent() -> tuple:
    """Build the compiled LangGraph + Memanto agent.

    Returns:
        (compiled_graph, client)
    """
    llm = _get_llm()
    client = get_client()

    # Define graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("recall_memory", lambda s: recall_memory_node(s, client))
    workflow.add_node("agent", lambda s: agent_node(s, llm, client))
    workflow.add_node("remember_memory", lambda s: remember_memory_node(s, client))

    # Flow: START → recall_memory → agent → remember_memory → END
    workflow.add_edge("recall_memory", "agent")
    workflow.add_edge("agent", "remember_memory")
    workflow.add_edge("remember_memory", END)

    workflow.add_edge(START, "recall_memory")

    # In-memory checkpointer for LangGraph persistence
    checkpointer = MemorySaver()

    return workflow.compile(checkpointer=checkpointer), client


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def run_session(
    user_id: str,
    session_id: str,
    messages: list[tuple[str, str]],
    thread_id: str | None = None,
) -> list[str]:
    """Run a sequence of user messages through the agent.

    Args:
        user_id: A unique identifier for the user.
        session_id: A unique identifier for this session.
        messages: List of (role, content) tuples. Role is 'human' or 'assistant'.
        thread_id: Optional LangGraph thread ID (use same ID for multi-turn convos).

    Returns:
        List of AI response texts.
    """
    app, client = build_agent()

    responses = []
    current_thread = thread_id or f"{user_id}-{session_id}"

    for role, content in messages:
        if role == "human":
            # Reset memory-stored flag for each new user turn
            initial_state = {
                "messages": [HumanMessage(content=content)],
                "user_id": user_id,
                "session_id": session_id,
                "memories_recalled": False,
                "memories_stored": False,
            }

            config = {"configurable": {"thread_id": current_thread}}
            result = app.invoke(initial_state, config=config)

            # Extract the last AI message
            for msg in reversed(result["messages"]):
                if hasattr(msg, "type") and msg.type == "ai":
                    responses.append(str(msg.content))
                    break

    try:
        client.deactivate_agent("langgraph-customer-support")
    except Exception:
        pass
    return responses
