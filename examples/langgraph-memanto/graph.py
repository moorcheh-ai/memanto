from __future__ import annotations

import os
from typing import Protocol, TypedDict

from langgraph.graph import END, StateGraph


class MemoryClient(Protocol):
    def recall(
        self, query: str, *, limit: int = 5, memory_type: str | None = None
    ) -> str: ...

    def remember(
        self,
        content: str,
        *,
        memory_type: str = "fact",
        tags: list[str] | None = None,
        confidence: float = 0.8,
        provenance: str = "explicit_statement",
    ) -> str: ...


class SupportState(TypedDict, total=False):
    user_id: str
    user_message: str
    recalled_context: str
    reply: str
    memories_written: list[str]


def build_support_graph(memory: MemoryClient):
    """Build a LangGraph workflow that reads and writes Memanto memories."""

    def recall_user_context(state: SupportState) -> SupportState:
        user_id = state["user_id"]
        query = (
            f"{user_id} support preferences timezone account open issue "
            "communication yesterday"
        )
        recalled_context = memory.recall(query, limit=6)
        return {"recalled_context": recalled_context}

    def draft_response(state: SupportState) -> SupportState:
        user_message = state["user_message"]
        recalled_context = state.get("recalled_context", "").strip()

        if recalled_context:
            memory_block = recalled_context
        else:
            memory_block = "No memories were recalled. Run seed_yesterday.py first."

        reply = f"""I checked Memanto before answering today's message.

Today's message:
{user_message}

Long-term memory recalled by Memanto:
{memory_block}

Support response:
Yesterday we were working on your solar monitoring dashboard, especially the inverter issue and your preferred update style. I will keep today's update concise, use email rather than SMS, and treat the previously recalled issue as the continuity point for this support thread."""
        return {"reply": reply}

    def remember_today_followup(state: SupportState) -> SupportState:
        user_id = state["user_id"]
        content = (
            f"{user_id} returned in a later LangGraph session asking for a recap. "
            "The agent recalled prior preferences from Memanto and responded with "
            "a concise email-first support update."
        )
        memory.remember(
            content,
            memory_type="event",
            tags=["langgraph", "cross-session", "support"],
            confidence=0.9,
            provenance="observed",
        )
        return {"memories_written": [content]}

    workflow = StateGraph(SupportState)
    workflow.add_node("recall_user_context", recall_user_context)
    workflow.add_node("draft_response", draft_response)
    workflow.add_node("remember_today_followup", remember_today_followup)

    workflow.set_entry_point("recall_user_context")
    workflow.add_edge("recall_user_context", "draft_response")
    workflow.add_edge("draft_response", "remember_today_followup")
    workflow.add_edge("remember_today_followup", END)

    return workflow.compile()


def default_initial_state() -> SupportState:
    return {
        "user_id": os.environ.get("MEMANTO_DEMO_USER_ID", "maya-rivera"),
        "user_message": os.environ.get(
            "MEMANTO_DEMO_MESSAGE",
            "Can you remind me what we were working on yesterday and how I prefer updates?",
        ),
    }
