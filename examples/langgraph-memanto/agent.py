"""
LangGraph + Memanto: Customer Support Agent with Persistent Memory

Graph topology
──────────────
  START
    │
    ▼
  recall_context   ── queries Memanto for memories relevant to the user's message
    │                  (cross-session: survives process restarts and new threads)
    ▼
  generate_response ─ LLM call enriched with recalled context + conversation history
    │
    ▼
  persist_memories ── LLM extracts atomic facts from this turn → stored in Memanto
    │
    ▼
   END

What lives where
────────────────
  LangGraph MemorySaver → within-session conversation history only
  Memanto               → cross-session long-term memories (the "permanent brain")
"""

from __future__ import annotations

import json
import logging
import re
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from memanto_memory import MemantoMemory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------


class SupportState(TypedDict):
    """State carried through the support-agent graph."""

    messages: Annotated[list, add_messages]  # full conversation; accumulated by MemorySaver
    user_id: str                             # logical user identifier
    recalled_context: str                    # formatted Memanto memories injected into prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_memories(memories: list[dict]) -> str:
    """Render a list of Memanto memory dicts into a readable context block."""
    if not memories:
        return ""
    lines: list[str] = []
    for mem in memories:
        mem_type = mem.get("type", "fact")
        title = mem.get("title", "")
        content = mem.get("content", "")
        confidence = mem.get("confidence", 0.8)
        lines.append(
            f"  • [{mem_type}] {title} ({float(confidence):.0%} confidence): {content}"
        )
    return "\n".join(lines)


def _parse_json_array(raw: str) -> list[dict]:
    """Extract a JSON array from an LLM response (tolerates markdown fences)."""
    # Strip ```json ... ``` fences
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if not match:
        return []
    try:
        parsed = json.loads(match.group())
        return [item for item in parsed if isinstance(item, dict)]
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def build_support_agent(
    api_key: str,
    agent_id: str,
    llm_model: str = "gpt-4o-mini",
    openai_base_url: str | None = None,
) -> tuple:
    """
    Construct and compile the LangGraph support agent with Memanto memory.

    Returns:
        (compiled_app, MemantoMemory) — callers must invoke memory.close()
        when the session ends to cleanly deactivate the Memanto session token.
    """
    memory = MemantoMemory(api_key=api_key, agent_id=agent_id)

    llm_kwargs: dict = {"model": llm_model, "temperature": 0.4}
    if openai_base_url:
        llm_kwargs["base_url"] = openai_base_url
    llm = ChatOpenAI(**llm_kwargs)

    # ── Node 1: recall_context ───────────────────────────────────────────────
    def recall_context(state: SupportState) -> dict:
        """
        Query Memanto for memories relevant to the user's latest message.

        This node fires BEFORE the LLM so that long-term memories can be
        injected into the system prompt for every turn.
        """
        last_human = next(
            (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            None,
        )
        if not last_human:
            return {"recalled_context": ""}

        raw_memories = memory.recall(query=last_human.content, limit=6)
        formatted = _format_memories(raw_memories)

        if formatted:
            logger.debug(
                "Recalled %d memories for query: %s",
                len(raw_memories),
                last_human.content[:60],
            )

        return {"recalled_context": formatted}

    # ── Node 2: generate_response ────────────────────────────────────────────
    def generate_response(state: SupportState) -> dict:
        """
        Generate an agent response using the conversation history plus any
        Memanto memories injected into the system prompt.
        """
        recalled = state.get("recalled_context", "")

        system_parts = [
            "You are Alex, a friendly and knowledgeable customer support agent. "
            "You have a persistent memory of past interactions and always "
            "personalise your responses based on what you know about the user.",
        ]

        if recalled:
            system_parts += [
                "\n## Memories recalled from previous sessions:",
                recalled,
                "\nUse this context naturally — don't mechanically recite it. "
                "Reference relevant details to demonstrate you remember the user.",
            ]
        else:
            system_parts.append(
                "\nThis user has no prior interaction history with you. "
                "Greet them warmly and gather useful context."
            )

        system_msg = SystemMessage(content="\n".join(system_parts))
        response = llm.invoke([system_msg] + list(state["messages"]))
        return {"messages": [response]}

    # ── Node 3: persist_memories ─────────────────────────────────────────────
    def persist_memories(state: SupportState) -> dict:
        """
        Extract memorable facts from the latest conversation turn and persist
        them in Memanto so they are available in ALL future sessions.
        """
        msgs = list(state["messages"])

        last_human = next(
            (m for m in reversed(msgs) if isinstance(m, HumanMessage)), None
        )
        last_ai = next(
            (m for m in reversed(msgs) if isinstance(m, AIMessage)), None
        )

        if not last_human or not last_ai:
            return {}

        turn_text = (
            f"User: {last_human.content}\n"
            f"Agent: {last_ai.content}"
        )

        extraction_response = llm.invoke([
            SystemMessage(content=(
                "You are a memory extraction assistant.\n"
                "Extract 0–3 concise, atomic memories from this support conversation "
                "turn that would help the agent assist this user in a FUTURE session.\n"
                "Focus on: user preferences, personal/device details, product issues, "
                "commitments made, and important decisions.\n"
                "Return ONLY a valid JSON array — no markdown fences, no extra text. "
                "Each element must have exactly these fields:\n"
                '  "type":       one of: fact | preference | event | commitment | observation\n'
                '  "title":      short label, max 60 chars\n'
                '  "content":   concise content, max 200 chars\n'
                '  "confidence": float 0.0–1.0\n'
                '  "tags":       array of lowercase strings\n'
                "If nothing is worth remembering long-term, return []."
            )),
            HumanMessage(content=f"Conversation turn:\n{turn_text}"),
        ])

        extracted = _parse_json_array(extraction_response.content)

        stored = 0
        for item in extracted:
            mem_id = memory.remember(
                memory_type=item.get("type", "fact"),
                title=str(item.get("title", ""))[:100],
                content=str(item.get("content", ""))[:500],
                confidence=float(item.get("confidence", 0.8)),
                tags=[str(t) for t in item.get("tags", [])],
            )
            if mem_id:
                stored += 1

        if stored:
            logger.debug("Persisted %d/%d extracted memories", stored, len(extracted))

        return {}

    # ── Assemble graph ────────────────────────────────────────────────────────
    builder = StateGraph(SupportState)

    builder.add_node("recall_context", recall_context)
    builder.add_node("generate_response", generate_response)
    builder.add_node("persist_memories", persist_memories)

    builder.add_edge(START, "recall_context")
    builder.add_edge("recall_context", "generate_response")
    builder.add_edge("generate_response", "persist_memories")
    builder.add_edge("persist_memories", END)

    # MemorySaver keeps the conversation history within this Python session.
    # Memanto keeps memories across ALL sessions (the core demo point).
    checkpointer = MemorySaver()
    app = builder.compile(checkpointer=checkpointer)

    return app, memory
