"""
LangGraph support-agent workflow backed by Memanto memory.

The graph deliberately keeps only current-turn information in state. Stable
customer facts and preferences are stored in and recalled from Memanto.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from memory_adapter import MemoryBackend


CUSTOMER_ID = "acme-001"
DAY_1_MESSAGE = (
    "Hi, this is Priya from Acme Robotics. We are on the enterprise plan, "
    "work in Pacific time, and prefer concise bullet updates. If checkout "
    "latency crosses 300ms, escalate to Sam on the platform team."
)
DAY_2_MESSAGE = (
    "Can you help me prepare a status reply about checkout latency?"
)


class SupportState(TypedDict, total=False):
    """Current-turn LangGraph state."""

    customer_id: str
    message: str
    recalled_memories: list[dict[str, Any]]
    memories_to_store: list[dict[str, Any]]
    response: str
    stored_memory_ids: list[str]


def extract_memories(state: SupportState) -> SupportState:
    """Extract stable facts from the current message."""
    message = state["message"]
    memories: list[dict[str, Any]] = []

    if "Priya" in message:
        memories.append(
            {
                "type": "fact",
                "title": "Primary contact is Priya",
                "content": "Priya is the primary support contact for Acme Robotics.",
                "confidence": 0.98,
                "tags": ["customer", "contact", "acme"],
            }
        )

    if "enterprise plan" in message:
        memories.append(
            {
                "type": "fact",
                "title": "Acme Robotics plan",
                "content": "Acme Robotics is on the enterprise plan.",
                "confidence": 0.95,
                "tags": ["customer", "plan", "acme"],
            }
        )

    if "Pacific time" in message:
        memories.append(
            {
                "type": "preference",
                "title": "Acme timezone",
                "content": "Acme Robotics works in Pacific time.",
                "confidence": 0.9,
                "tags": ["customer", "timezone", "acme"],
            }
        )

    if "concise bullet updates" in message:
        memories.append(
            {
                "type": "preference",
                "title": "Acme communication style",
                "content": "Acme Robotics prefers concise bullet updates.",
                "confidence": 0.93,
                "tags": ["customer", "communication", "acme"],
            }
        )

    if "checkout latency crosses 300ms" in message:
        memories.append(
            {
                "type": "instruction",
                "title": "Checkout latency escalation",
                "content": (
                    "If checkout latency crosses 300ms for Acme Robotics, "
                    "escalate to Sam on the platform team."
                ),
                "confidence": 0.97,
                "tags": ["customer", "latency", "escalation", "acme"],
            }
        )

    return {"memories_to_store": memories}


def make_store_memories(memory: MemoryBackend):
    """Create a LangGraph node that stores extracted memories."""

    def store_memories(state: SupportState) -> SupportState:
        stored_ids: list[str] = []
        for item in state.get("memories_to_store", []):
            result = memory.remember(
                memory_type=item["type"],
                title=item["title"],
                content=item["content"],
                confidence=item["confidence"],
                tags=item["tags"],
            )
            stored_ids.append(str(result.get("memory_id", "unknown")))
        return {"stored_memory_ids": stored_ids}

    return store_memories


def make_recall_customer_context(memory: MemoryBackend):
    """Create a LangGraph node that recalls long-term customer context."""

    def recall_customer_context(state: SupportState) -> SupportState:
        query = (
            f"Customer {state['customer_id']} contact plan timezone communication "
            "preference checkout latency escalation"
        )
        memories = memory.recall(
            query=query,
            limit=6,
            memory_types=["fact", "preference", "instruction"],
        )
        return {"recalled_memories": memories}

    return recall_customer_context


def draft_response(state: SupportState) -> SupportState:
    """Draft a deterministic support reply from recalled memories."""
    memories = state.get("recalled_memories", [])
    memory_text = " ".join(memory.get("content", "") for memory in memories)

    contact = "there"
    if "Priya" in memory_text:
        contact = "Priya"

    style = "a concise update"
    if "concise bullet updates" in memory_text:
        style = "concise bullets"

    escalation = ""
    if "Sam on the platform team" in memory_text:
        escalation = " I will escalate to Sam if latency crosses 300ms."

    plan = ""
    if "enterprise plan" in memory_text:
        plan = " I see Acme is on the enterprise plan."

    response = (
        f"Hi {contact}, here is {style} for checkout latency.{plan}{escalation} "
        "Current status: I will verify the latest latency numbers and share next "
        "steps in Pacific time."
    )
    return {"response": response}


def build_support_graph(memory: MemoryBackend):
    """Build the LangGraph workflow used by the demo scripts."""
    builder = StateGraph(SupportState)
    builder.add_node("extract_memories", extract_memories)
    builder.add_node("store_memories", make_store_memories(memory))
    builder.add_node("recall_customer_context", make_recall_customer_context(memory))
    builder.add_node("draft_response", draft_response)

    builder.add_edge(START, "extract_memories")
    builder.add_edge("extract_memories", "store_memories")
    builder.add_edge("store_memories", "recall_customer_context")
    builder.add_edge("recall_customer_context", "draft_response")
    builder.add_edge("draft_response", END)
    return builder.compile()


def print_run_summary(label: str, result: SupportState) -> None:
    """Pretty-print the demo result without requiring Rich."""
    print(f"\n{'=' * 72}")
    print(label)
    print(f"{'=' * 72}")
    print(f"Stored memory IDs: {result.get('stored_memory_ids', [])}")
    print("\nRecalled memories:")
    for memory in result.get("recalled_memories", []):
        print(f"- [{memory.get('type', 'unknown')}] {memory.get('title', 'Untitled')}")
        print(f"  {memory.get('content', '')}")
    print("\nAgent response:")
    print(result.get("response", ""))
