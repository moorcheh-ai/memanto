"""
LangGraph + Memanto support agent example.

This example uses Memanto as an external long-term memory layer that is never
stored in LangGraph state. A second run can recall preferences that were stored
in a previous run via the same Memanto agent namespace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from memanto.cli.client.sdk_client import SdkClient


class SupportState(TypedDict, total=False):
    customer_id: str
    message: str
    recall_context: str
    reply: str


@dataclass
class SupportMemorySession:
    """Thin wrapper around Memanto client operations for the example."""

    client: SdkClient
    agent_id: str

    def recall(
        self,
        query: str,
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        """Search Memanto memories using semantic text query."""
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=["fact", "preference", "decision", "observation"],
        )
        return result.get("memories", [])

    def remember(
        self,
        memory_text: str,
        customer_id: str,
    ) -> str:
        """Persist a deterministic customer preference memory."""
        title = f"{customer_id} preference"
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type="preference",
            title=title,
            content=memory_text,
            confidence=0.95,
            tags=["langgraph", "support", customer_id],
            source=customer_id,
            provenance="explicit_statement",
        )
        return result["memory_id"]


def _extract_memory_intent(message: str) -> str | None:
    """
    Extract memory content from explicit remember commands.

    Accepted phrases:
    - "remember: ..."
    - "please remember ..."
    - "store: ..."
    """
    lowered = message.lower().strip()
    for prefix in ("remember:", "store:", "please remember"):
        if lowered.startswith(prefix):
            content = message[len(prefix) :].strip(" -:")
            if content:
                return content

    match = re.search(r"\bremember\s+(?:that\s+)?(?P<content>.+)", lowered)
    if match:
        content = message[match.start("content") :].strip()
        return content

    return None


def _format_memories(memories: list[dict[str, Any]]) -> str:
    """Render memory hits into a readable block for LLM-free replies."""
    if not memories:
        return "No matching memories found."

    formatted = []
    for mem in memories:
        memory_type = mem.get("type", "memory")
        title = mem.get("title", "Untitled")
        content = mem.get("content", "").replace("\n", " ").strip()
        confidence = mem.get("confidence", "N/A")
        formatted.append(
            f"- [{memory_type}] {title} (confidence: {confidence}): {content}"
        )
    return "\n".join(formatted)


def build_support_graph(client: SdkClient, agent_id: str):
    """
    Build a two-node LangGraph graph:
    1) recall memories from Memanto
    2) generate a deterministic support response (+ optionally store new memory)
    """

    memory_session = SupportMemorySession(client=client, agent_id=agent_id)

    def recall_memories(state: SupportState) -> SupportState:
        customer_id = state.get("customer_id", "guest")
        message = state.get("message", "")
        if not message:
            return {"recall_context": "No message to process."}

        query = f"{customer_id}: {message}"
        memories = memory_session.recall(query=query)
        return {"recall_context": _format_memories(memories)}

    def respond(state: SupportState) -> SupportState:
        customer_id = state.get("customer_id", "guest")
        message = state.get("message", "").strip()
        recall_context = state.get("recall_context", "No memory context available.")

        intent = _extract_memory_intent(message)
        lines: list[str] = []
        stored_memory_id: str | None = None

        if intent:
            stored_memory_id = memory_session.remember(intent, customer_id)
            lines.append(
                f"✅ I stored it in long-term memory (id: {stored_memory_id})."
            )

        lines.append(f"📎 Current recall context for '{customer_id}':")
        lines.append(recall_context)

        if not intent and recall_context == "No matching memories found.":
            lines.append(
                "I don't have prior context yet. You can tell me something to remember by "
                "saying 'remember: ...'"
            )

        return {"reply": "\n".join(lines)}

    workflow = StateGraph(SupportState)
    workflow.add_node("recall_memories", recall_memories)
    workflow.add_node("respond", respond)
    workflow.set_entry_point("recall_memories")
    workflow.add_edge("recall_memories", "respond")
    workflow.add_edge("respond", END)

    return workflow.compile()
