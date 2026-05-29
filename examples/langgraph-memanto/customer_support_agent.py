"""
LangGraph + Memanto Integration: Customer Support Agent

This example demonstrates how Memanto can serve as the long-term memory
layer for a LangGraph stateful agent.

The agent:
1. Maintains a short-term conversation within LangGraph's state
2. Uses Memanto to persist long-term memories across sessions
3. Recalls past interactions to provide personalized support
4. Automatically stores important context (customer preferences, issues, resolutions)

Requirements:
    pip install langgraph memanto
"""

import json
import os
from datetime import datetime
from typing import TypedDict, Literal, Optional

# LangGraph
from langgraph.graph import StateGraph, END
from langgraph.checkpoint import MemorySaver

# Memanto SDK
from memanto import MemantoClient

# ── Configuration ─────────────────────────────────────────────────────

MEMANTO_API_KEY = os.environ.get("MEMANTO_API_KEY", "")
MEMANTO_BRAIN_ID = os.environ.get("MEMANTO_BRAIN_ID", "customer-support-brain")

# ── State Definition ──────────────────────────────────────────────────


class AgentState(TypedDict):
    """State passed between LangGraph nodes."""
    customer_id: str
    query: str
    conversation_history: list[dict]
    context: dict
    response: str
    memories_updated: bool
    ticket_id: Optional[str]


# ── Memanto Client ────────────────────────────────────────────────────

class MemantoMemory:
    """Bridge between LangGraph state and Memanto persistent memory."""

    def __init__(self, api_key: str, brain_id: str):
        self.client = MemantoClient(api_key=api_key)
        self.brain_id = brain_id

    def recall_customer(self, customer_id: str) -> dict:
        """Retrieve all stored memories for a customer."""
        try:
            memories = self.client.query(
                brain_id=self.brain_id,
                query=f"Customer {customer_id} history, preferences, and past issues",
                limit=10,
            )
            return {
                "memories": memories,
                "recalled_at": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"memories": [], "error": str(e)}

    def store_memory(self, customer_id: str, memory: str, tags: list[str] = None):
        """Store a new memory about this customer."""
        try:
            return self.client.store(
                brain_id=self.brain_id,
                content=memory,
                metadata={
                    "customer_id": customer_id,
                    "tags": tags or [],
                    "source": "langgraph-agent",
                },
            )
        except Exception as e:
            return {"error": str(e)}

    def summarize_and_store(
        self, customer_id: str, history: list[dict], resolution: str
    ):
        """Summarize a conversation and store it as a long-term memory."""
        summary_parts = []
        for msg in history[-5:]:  # last 5 messages
            role = msg.get("role", "unknown")
            text = msg.get("text", "")[:200]
            summary_parts.append(f"[{role}]: {text}")

        memory_text = (
            f"Customer {customer_id} interaction summary:\n"
            + "\n".join(summary_parts)
            + f"\nResolution: {resolution}"
        )

        return self.store_memory(
            customer_id=customer_id,
            memory=memory_text,
            tags=["interaction", "support", "resolution"],
        )


# ── Agent Nodes ───────────────────────────────────────────────────────


def analyze_query(state: AgentState) -> dict:
    """Analyze the customer's query to determine intent and sentiment."""
    query = state["query"].lower()
    
    # Simple rule-based intent detection
    if any(w in query for w in ["refund", "return", "cancel", "money"]):
        intent = "billing"
    elif any(w in query for w in ["bug", "error", "crash", "broken", "not working"]):
        intent = "technical"
    elif any(w in query for w in ["account", "login", "password", "access"]):
        intent = "account"
    elif any(w in query for w in ["order", "shipping", "tracking", "delivery"]):
        intent = "order"
    else:
        intent = "general"

    return {
        "context": {
            "intent": intent,
            "sentiment": "negative" if any(w in query for w in ["angry", "frustrated", "annoyed", "terrible", "worst"]) else "neutral",
            "query_type": intent,
            "analyzed_at": datetime.now().isoformat(),
        }
    }


def recall_memories(state: AgentState) -> dict:
    """Recall customer memories from Memanto."""
    memory_system = MemantoMemory(MEMANTO_API_KEY, MEMANTO_BRAIN_ID)
    customer_memories = memory_system.recall_customer(state["customer_id"])

    return {
        "context": {
            **state.get("context", {}),
            "customer_memories": customer_memories,
            "recalled_from_memanto": True,
        }
    }


def generate_response(state: AgentState) -> dict:
    """Generate a personalized response based on context and memories."""
    context = state.get("context", {})
    memories = context.get("customer_memories", {}).get("memories", [])
    intent = context.get("intent", "general")
    sentiment = context.get("sentiment", "neutral")
    history = state.get("conversation_history", [])

    # Build personalized greeting if we have memory
    greeting = "Hello! How can I help you today?"
    if memories:
        greeting = f"Welcome back! I see you've contacted us before. Let me review your history and help you out."

    # Intent-specific response templates
    responses = {
        "billing": f"{greeting} I can help you with billing questions. Let me look into the details for you.",
        "technical": f"{greeting} I understand you're experiencing a technical issue. Let me help you troubleshoot.",
        "account": f"{greeting} I can help with account-related questions. Please give me a moment to check.",
        "order": f"{greeting} I'll help you track your order. Let me look that up for you.",
        "general": f"{greeting} I'm here to help! What can I assist you with?",
    }

    # Sentiment-adjusted responses
    if sentiment == "negative":
        responses[intent] = (f"I understand this is frustrating. "
                             f"{responses[intent]} I'll prioritize your case.")

    return {
        "response": responses.get(intent, greeting),
        "conversation_history": history + [
            {"role": "customer", "text": state["query"]},
            {"role": "agent", "text": responses.get(intent, greeting)},
        ],
    }


def store_memories(state: AgentState) -> dict:
    """Store new memories from this interaction into Memanto."""
    memory_system = MemantoMemory(MEMANTO_API_KEY, MEMANTO_BRAIN_ID)
    history = state.get("conversation_history", [])

    result = memory_system.summarize_and_store(
        customer_id=state["customer_id"],
        history=history,
        resolution=state.get("response", "No resolution provided"),
    )

    return {
        "memories_updated": "error" not in result,
        "ticket_id": f"TKT-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
    }


def route_after_response(state: AgentState) -> Literal["store_memories", END]:
    """Route to memory storage or end the workflow."""
    if state.get("response"):
        return "store_memories"
    return END


# ── Build LangGraph ───────────────────────────────────────────────────


def build_agent():
    """Build the LangGraph agent with Memanto memory integration."""

    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("analyze_query", analyze_query)
    workflow.add_node("recall_memories", recall_memories)
    workflow.add_node("generate_response", generate_response)
    workflow.add_node("store_memories", store_memories)

    # Set entry point
    workflow.set_entry_point("analyze_query")

    # Define edges
    workflow.add_edge("analyze_query", "recall_memories")
    workflow.add_edge("recall_memories", "generate_response")
    workflow.add_conditional_edges(
        "generate_response",
        route_after_response,
        {"store_memories": "store_memories", END: END},
    )
    workflow.add_edge("store_memories", END)

    # Add memory persistence
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


# ── Usage Example ─────────────────────────────────────────────────────


def main():
    """Run the customer support agent with Memanto memory."""

    print("=" * 60)
    print("LangGraph + Memanto: Customer Support Agent")
    print("=" * 60)
    print()

    agent = build_agent()

    # Simulate multiple customer interactions to demonstrate memory persistence
    interactions = [
        {
            "customer_id": "cust_001",
            "query": "I need a refund for my last order. It arrived damaged.",
        },
        {
            "customer_id": "cust_001",
            "query": "Have you processed my refund yet? I'm still waiting.",
        },
        {
            "customer_id": "cust_002",
            "query": "I can't log into my account. It says invalid password.",
        },
        {
            "customer_id": "cust_001",
            "query": "I'd like to place a new order. Can you recommend something?",
        },
    ]

    for interaction in interactions:
        print(f"\n{'─' * 40}")
        print(f"👤 Customer: {interaction['customer_id']}")
        print(f"💬 Query: {interaction['query']}")
        print(f"{'─' * 40}")

        # Initialize state
        initial_state: AgentState = {
            "customer_id": interaction["customer_id"],
            "query": interaction["query"],
            "conversation_history": [],
            "context": {},
            "response": "",
            "memories_updated": False,
            "ticket_id": None,
        }

        # Run the agent
        result = agent.invoke(initial_state, {"configurable": {"thread_id": f"session_{interaction['customer_id']}"}})

        print(f"🤖 Response: {result.get('response', 'No response')}")
        print(f"🧠 Memanto memories updated: {result.get('memories_updated', False)}")
        print(f"🎫 Ticket: {result.get('ticket_id', 'N/A')}")

        # Show what Memanto would store
        if result.get("memories_updated"):
            print(f"💾 Memory stored in Memanto brain '{MEMANTO_BRAIN_ID}'")

    print(f"\n{'=' * 60}")
    print("✅ Demonstration complete!")
    print("Memanto persists memories across LangGraph sessions,")
    print("enabling the agent to remember past interactions.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
