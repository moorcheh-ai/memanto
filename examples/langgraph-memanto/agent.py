"""
LangGraph customer support agent with Memanto persistent memory.

This agent demonstrates:
1. Stateful graph execution with LangGraph
2. Typed memory storage via Memanto
3. Cross-session recall (remembers from "yesterday")

The graph has three nodes:
  - router: classifies intent (store_preference / recall / support)
  - process: handles the intent (stores/retrieves memories)
  - respond: generates the final response
"""
import logging
import os
from typing import Any, Literal, Optional

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph, State
from langgraph.checkpoint import MemorySaver
from typing_extensions import TypedDict

from memory import create_memory, MemantoMemory, MockMemantoMemory

load_dotenv()
logger = logging.getLogger(__name__)


# ── Graph State ──────────────────────────────────────────────────────

class AgentState(TypedDict):
    """State passed through the LangGraph nodes."""
    customer_id: str
    message: str
    intent: Optional[str]
    memory_context: Optional[str]
    response: Optional[str]
    memories_stored: list[dict]
    session_label: str  # e.g., "Session A (Day 1)" or "Session B (Day 2)"


# ── Graph Nodes ──────────────────────────────────────────────────────

def router_node(state: AgentState) -> dict:
    """Classify the customer message into an intent.

    Uses rule-based classification (no LLM call needed for demo).
    """
    msg = state["message"].lower()

    if any(w in msg for w in ["remember", "note", "store", "save", "i am", "my name", "i like", "i prefer", "i want"]):
        intent = "store_preference"
    elif any(w in msg for w in ["recall", "what do you know", "remember me", "who am i", "my info", "context"]):
        intent = "recall"
    elif any(w in msg for w in ["help", "support", "problem", "issue", "question", "how do"]):
        intent = "support"
    else:
        intent = "support"

    logger.info(f"[{state['session_label']}] Classified as: {intent}")
    return {"intent": intent}


def process_node(state: AgentState) -> dict:
    """Process the intent: store/recall memories via Memanto."""
    memory = state.get("_memory")
    if memory is None:
        memory = create_memory()

    customer_id = state["customer_id"]
    intent = state["intent"]
    msg = state["message"]
    stored = []
    context = ""

    if intent == "store_preference":
        # Extract and store typed memories from the message
        _store_customer_info(memory, customer_id, msg, stored)
        logger.info(f"[{state['session_label']}] Stored {len(stored)} memories for {customer_id}")

    elif intent == "recall":
        # Retrieve memories across sessions
        context = memory.get_context_string(f"customer {customer_id}", limit=10)
        logger.info(f"[{state['session_label']}] Recalled context for {customer_id}")

    elif intent == "support":
        # For support queries, first recall context, then handle
        context = memory.get_context_string(f"customer {customer_id}", limit=5)
        logger.info(f"[{state['session_label']}] Support query with {len(context)} chars of context")

    return {
        "memory_context": context,
        "memories_stored": stored,
    }


def _store_customer_info(
    memory: MemantoMemory | MockMemantoMemory,
    customer_id: str,
    message: str,
    stored: list,
):
    """Parse a customer intro message and store typed memories."""
    msg_lower = message.lower()

    # Name
    if "my name is" in msg_lower or "i am " in msg_lower or "i'm " in msg_lower:
        memory.remember(
            f"Customer {customer_id}: {message}",
            memory_type="fact",
            confidence=0.95,
            tags=f"customer,{customer_id},identity",
        )
        stored.append({"type": "fact", "content": message})

    # Preferences
    if "i like" in msg_lower:
        memory.remember(
            f"Customer {customer_id}: {message}",
            memory_type="preference",
            confidence=0.85,
            tags=f"customer,{customer_id},preference",
        )
        stored.append({"type": "preference", "content": message})

    if "i prefer" in msg_lower:
        memory.remember(
            f"Customer {customer_id}: {message}",
            memory_type="preference",
            confidence=0.9,
            tags=f"customer,{customer_id},preference",
        )
        stored.append({"type": "preference", "content": message})

    # Goals
    if "i want" in msg_lower or "i need" in msg_lower or "goal" in msg_lower:
        memory.remember(
            f"Customer {customer_id}: {message}",
            memory_type="goal",
            confidence=0.8,
            tags=f"customer,{customer_id},goal",
        )
        stored.append({"type": "goal", "content": message})

    # Relationship
    if any(w in msg_lower for w in ["team", "company", "work at", "works for"]):
        memory.remember(
            f"Customer {customer_id}: {message}",
            memory_type="relationship",
            confidence=0.85,
            tags=f"customer,{customer_id},relationship",
        )
        stored.append({"type": "relationship", "content": message})

    # Store as event for every interaction
    memory.remember(
        f"Session interaction: Customer {customer_id} said: {message}",
        memory_type="event",
        confidence=0.95,
        tags=f"customer,{customer_id},interaction",
    )

    if not stored:
        # Generic fallback
        memory.remember(
            f"Customer {customer_id} information: {message}",
            memory_type="fact",
            confidence=0.7,
            tags=f"customer,{customer_id}",
        )
        stored.append({"type": "fact", "content": message})

    # Also store the fact that this session happened — proves cross-session recall
    memory.remember(
        f"Customer {customer_id} was active in this session.",
        memory_type="event",
        confidence=0.99,
        tags=f"customer,{customer_id},session,{state.session_label.replace(' ', '_').lower() if hasattr(state, '__getitem__') else 'session'}",
    )


def respond_node(state: AgentState) -> dict:
    """Generate the agent's response based on intent and memory context."""
    customer_id = state["customer_id"]
    intent = state["intent"]
    context = state.get("memory_context", "")
    msg = state["message"]
    session = state["session_label"]

    if intent == "store_preference":
        stored_count = len(state.get("memories_stored", []))
        response = (
            f"✅ Thanks, {customer_id}! I've stored {stored_count} memory/memories "
            f"about you — preferences, facts, and goals are saved as typed semantic memories. "
            f"Next time we talk, I'll remember everything! 📝"
        )

    elif intent == "recall":
        if context:
            response = (
                f"🧠 Here's what I remember about you, {customer_id}:\n\n"
                f"{context}\n\n"
                f"All of this persisted across sessions via Memanto! "
                f"(This session: {session})"
            )
        else:
            response = (
                f"🤔 I don't have any stored memories for {customer_id} yet. "
                f"Tell me about yourself and I'll remember!"
            )

    elif intent == "support":
        if context:
            response = (
                f"👋 Welcome back, {customer_id}! I remember you from before.\n\n"
                f"{context}\n\n"
                f"Now, how can I help you today?"
            )
        else:
            response = f"👋 Hi {customer_id}! How can I help you today?"

    else:
        response = f"👋 Hello {customer_id}! How can I assist you today?"

    logger.info(f"[{session}] Response generated ({len(response)} chars)")
    return {"response": response}


# ── Build Graph ──────────────────────────────────────────────────────

def build_agent() -> StateGraph:
    """Build the LangGraph state machine.

    Graph structure:
        START → router → process → respond → END
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    workflow.add_node("process", process_node)
    workflow.add_node("respond", respond_node)

    workflow.set_entry_point("router")
    workflow.add_edge("router", "process")
    workflow.add_edge("process", "respond")
    workflow.add_edge("respond", END)

    return workflow.compile()


# ── Convenience Runner ───────────────────────────────────────────────

def run_agent(
    customer_id: str,
    message: str,
    session_label: str = "Session",
    memory: MemantoMemory | MockMemantoMemory | None = None,
) -> AgentState:
    """Run the LangGraph agent with a customer message.

    Args:
        customer_id: Unique customer identifier.
        message: Customer's message.
        session_label: Label for logging (e.g., "Session A (Day 1)").
        memory: Pre-configured Memanto instance (or None to auto-create).

    Returns:
        Final AgentState dict with response and memory context.
    """
    agent = build_agent()

    initial_state: AgentState = {
        "customer_id": customer_id,
        "message": message,
        "intent": None,
        "memory_context": None,
        "response": None,
        "memories_stored": [],
        "session_label": session_label,
        "_memory": memory or create_memory(),
    }

    result = agent.invoke(initial_state)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    memory = create_memory()
    result = run_agent(
        customer_id="test-user",
        message="Hi, my name is Alex and I like dark mode interfaces",
        session_label="Test Run",
        memory=memory,
    )
    print(f"\nAgent: {result['response']}")
    print(f"Memories stored: {len(result['memories_stored'])}")
