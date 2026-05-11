"""Customer support LangGraph workflow backed by durable Memanto memory."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, StateGraph

from memory_backends import Memory, MemoryBackend, stable_memory_id


class SupportState(TypedDict):
    """Graph state for one support turn."""

    thread_id: str
    session_label: str
    customer_message: str
    recalled_memories: list[Memory]
    response: str
    new_memories: list[Memory]
    persisted_memory_ids: list[str]


@dataclass(frozen=True)
class SupportAgent:
    """Compiled support workflow plus its durable memory backend."""

    memory: MemoryBackend

    def graph(self):
        workflow = StateGraph(SupportState)
        workflow.add_node("recall_context", self.recall_context)
        workflow.add_node("draft_response", self.draft_response)
        workflow.add_node("extract_memories", self.extract_memories)
        workflow.add_node("persist_memories", self.persist_memories)
        workflow.set_entry_point("recall_context")
        workflow.add_edge("recall_context", "draft_response")
        workflow.add_edge("draft_response", "extract_memories")
        workflow.add_edge("extract_memories", "persist_memories")
        workflow.add_edge("persist_memories", END)
        return workflow.compile()

    def recall_context(self, state: SupportState) -> SupportState:
        query = (
            f"{state['customer_message']} customer identity preference vendor "
            "approval PHI SMS safety support policy"
        )
        recalled = self.memory.recall(query=query, limit=6)
        return {**state, "recalled_memories": recalled}

    def draft_response(self, state: SupportState) -> SupportState:
        memories = state["recalled_memories"]
        message = state["customer_message"]
        customer = _first_memory(memories, "relationship")
        preference = _first_memory(memories, "preference")
        policy = _first_memory(memories, "instruction")
        vendor = _first_memory(memories, "fact")

        name = _extract_after(customer.content, "Customer is ") if customer else "there"
        channel = "SMS" if preference and "SMS" in preference.content else "the requested channel"
        vendor_name = _extract_after(vendor.content, "Vendor is ") if vendor else "the vendor"

        guardrail = (
            f" I will avoid PHI and get approval first because I remember: {policy.content}"
            if policy
            else ""
        )
        response = (
            f"Hi {name}, I can help with that. I will use {channel} for updates "
            f"and reference {vendor_name} only at a non-sensitive level.{guardrail} "
            f"New thread {state['thread_id']} had no in-graph history, so this context "
            "came from durable Memanto memory."
        )
        if "yesterday" in message.lower() or "remember" in message.lower():
            response += " Yes, I remember the details you shared yesterday."

        return {**state, "response": response}

    def extract_memories(self, state: SupportState) -> SupportState:
        message = state["customer_message"]
        session = state["session_label"]
        memories: list[Memory] = []

        customer_match = re.search(
            r"\b(?:i am|i'm|this is)\s+([A-Z][a-zA-Z]+)", message, re.IGNORECASE
        )
        organization_match = re.search(
            r"from\s+([A-Z][A-Za-z ]+?)(?:\.|,| and|$)", message, re.IGNORECASE
        )
        if customer_match:
            name = customer_match.group(1)
            org = organization_match.group(1).strip() if organization_match else "unknown org"
            memories.append(
                _memory(
                    session,
                    "relationship",
                    "Customer identity",
                    f"Customer is {name} from {org}.",
                    ["customer", "identity", "support"],
                )
            )

        if "sms" in message.lower():
            memories.append(
                _memory(
                    session,
                    "preference",
                    "Preferred channel",
                    "Customer prefers SMS updates over email or phone.",
                    ["sms", "preference", "support"],
                )
            )

        vendor_match = re.search(r"vendor\s+(?:is|=)\s+([A-Z][A-Za-z0-9_-]+)", message)
        if vendor_match:
            vendor = vendor_match.group(1)
            memories.append(
                _memory(
                    session,
                    "fact",
                    "Support vendor",
                    f"Vendor is {vendor}.",
                    ["vendor", "support"],
                )
            )

        if "phi" in message.lower() or "approval" in message.lower():
            memories.append(
                _memory(
                    session,
                    "instruction",
                    "Safety and approval rule",
                    "Never include PHI in replies and ask Dr. Rao for approval before escalation.",
                    ["policy", "phi", "approval"],
                )
            )

        return {**state, "new_memories": memories}

    def persist_memories(self, state: SupportState) -> SupportState:
        ids = [self.memory.remember(memory) for memory in state["new_memories"]]
        return {**state, "persisted_memory_ids": ids}


def run_support_turn(
    agent: SupportAgent,
    thread_id: str,
    session_label: str,
    customer_message: str,
) -> SupportState:
    """Run one isolated LangGraph thread against durable memory."""

    initial: SupportState = {
        "thread_id": thread_id,
        "session_label": session_label,
        "customer_message": customer_message,
        "recalled_memories": [],
        "response": "",
        "new_memories": [],
        "persisted_memory_ids": [],
    }
    return agent.graph().invoke(initial)


def _memory(
    source_session: str,
    memory_type: str,
    title: str,
    content: str,
    tags: list[str],
) -> Memory:
    return Memory(
        memory_id=stable_memory_id(source_session, title),
        memory_type=memory_type,
        title=title,
        content=content,
        confidence=0.92,
        tags=tags,
        source_session=source_session,
    )


def _first_memory(memories: list[Memory], memory_type: str) -> Memory | None:
    return next((memory for memory in memories if memory.memory_type == memory_type), None)


def _extract_after(text: str, marker: str) -> str:
    if marker not in text:
        return text
    value = text.split(marker, 1)[1].split(".", 1)[0]
    return value.strip()
