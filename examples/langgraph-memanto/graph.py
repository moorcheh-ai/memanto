"""
LangGraph workflow with Memanto as the long-term memory layer.

The graph is intentionally small so the wiring is obvious:

    recall  -->  respond  -->  extract  -->  END

* ``recall``  reads the latest user message, queries Memanto, and stashes
  the rendered memories in the graph state.
* ``respond`` calls the LLM with system prompt + recalled memories + the
  conversation so far.
* ``extract`` asks the LLM (in JSON mode) to pull any *durable* facts /
  preferences out of the new user turn and writes them back to Memanto.

Only the user's turn is mined for memories -- the assistant's answer is
ephemeral. This keeps storage tight and prevents the LLM from
hallucinating "facts" into long-term memory.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Any, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from memanto_memory import MemantoMemory, Memory

logger = logging.getLogger(__name__)

VALID_MEMORY_TYPES = {
    "fact",
    "preference",
    "goal",
    "decision",
    "commitment",
    "relationship",
    "context",
    "event",
    "observation",
    "instruction",
    "artifact",
    "learning",
    "error",
}

SYSTEM_PROMPT = """You are a helpful customer support concierge with persistent long-term memory.

You have access to memories carried over from previous sessions with this user. \
When relevant memories appear under "Relevant memories", treat them as known \
facts about the user and reference them naturally -- do NOT say "I don't \
remember" if the answer is in the memory block. If a memory is missing, ask a \
short clarifying question rather than guessing.

Keep responses concise (3-5 sentences). Be warm but direct.
"""

EXTRACTION_PROMPT = """You are a memory extraction module. Read the user's latest message and \
extract any DURABLE facts about the user that should be remembered across \
sessions (preferences, goals, decisions, commitments, biographical facts, \
relationships).

Rules:
- Skip ephemeral things ("I'm running late today", "thanks!", "ok").
- One memory per atomic fact. Do NOT merge unrelated facts.
- Title <= 80 chars. Content <= 400 chars. Phrase content as a third-person \
  statement about the user ("User prefers X").
- Confidence: 0.95 for explicit statements, 0.75 for clear implications.
- Return STRICT JSON: {{"memories": [{{"type": ..., "title": ..., "content": ..., "confidence": ..., "tags": [...]}}, ...]}}
- type MUST be one of: fact, preference, goal, decision, commitment, \
  relationship, context, event, observation, instruction, artifact, learning, error.
- If nothing is worth remembering, return {{"memories": []}}.

User message:
\"\"\"{user_text}\"\"\"
"""


class GraphState(TypedDict):
    """State threaded through the graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    recalled: list[Memory]
    stored_ids: list[str]


def _build_llm(model: str | None = None, temperature: float = 0.2) -> ChatOpenAI:
    """Build a ChatOpenAI client pointed at OpenRouter by default."""
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY (or OPENAI_API_KEY) is not set. "
            "Copy .env.example to .env and fill it in."
        )
    base_url = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    resolved_model = (
        model
        or os.environ.get("LANGGRAPH_LLM_MODEL")
        or "openai/gpt-4o-mini"
    )
    return ChatOpenAI(
        model=resolved_model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
    )


def _latest_user_text(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


def build_graph(memory: MemantoMemory, model: str | None = None) -> Any:
    """Compile a LangGraph workflow bound to a Memanto memory instance."""

    llm = _build_llm(model=model)
    extractor_llm = _build_llm(model=model, temperature=0.0)

    def recall_node(state: GraphState) -> dict[str, Any]:
        user_text = _latest_user_text(state["messages"])
        if not user_text:
            return {"recalled": []}
        recalled = memory.recall(user_text, limit=6)
        logger.info("Recalled %d memories for query=%r", len(recalled), user_text)
        return {"recalled": recalled}

    def respond_node(state: GraphState) -> dict[str, Any]:
        rendered = MemantoMemory.render_memories(state.get("recalled", []))
        system = SystemMessage(
            content=(
                f"{SYSTEM_PROMPT}\n\n"
                f"User id: {state['user_id']}\n\n"
                f"Relevant memories from prior sessions:\n{rendered}"
            )
        )
        reply = llm.invoke([system, *state["messages"]])
        return {"messages": [reply]}

    def extract_node(state: GraphState) -> dict[str, Any]:
        user_text = _latest_user_text(state["messages"])
        if not user_text:
            return {"stored_ids": []}

        prompt = EXTRACTION_PROMPT.format(user_text=user_text.replace('"""', "'''"))
        raw = extractor_llm.invoke([HumanMessage(content=prompt)]).content
        text = raw if isinstance(raw, str) else str(raw)

        try:
            payload = json.loads(_strip_json_fence(text))
            candidates = payload.get("memories", [])
            if not isinstance(candidates, list):
                candidates = []
        except json.JSONDecodeError as exc:
            logger.warning("Memory extraction returned non-JSON: %s (%s)", text, exc)
            candidates = []

        stored: list[str] = []
        for cand in candidates:
            if not isinstance(cand, dict):
                continue
            mem_type = str(cand.get("type", "")).strip().lower()
            title = str(cand.get("title", "")).strip()
            content = str(cand.get("content", "")).strip()
            confidence = float(cand.get("confidence", 0.85) or 0.85)
            tags = [str(t).strip() for t in cand.get("tags", []) if str(t).strip()]
            if mem_type not in VALID_MEMORY_TYPES or not title or not content:
                logger.debug("Skipping malformed memory candidate: %r", cand)
                continue
            mem_id = memory.remember(
                memory_type=mem_type,
                title=title,
                content=content,
                confidence=max(0.0, min(1.0, confidence)),
                tags=tags,
            )
            stored.append(mem_id)

        return {"stored_ids": stored}

    builder = StateGraph(GraphState)
    builder.add_node("recall", recall_node)
    builder.add_node("respond", respond_node)
    builder.add_node("extract", extract_node)

    builder.set_entry_point("recall")
    builder.add_edge("recall", "respond")
    builder.add_edge("respond", "extract")
    builder.add_edge("extract", END)

    return builder.compile()


def _strip_json_fence(text: str) -> str:
    """Strip ```json ... ``` fences if the model wrapped its reply."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def initial_state(user_id: str, user_text: str) -> GraphState:
    """Convenience constructor for a single-turn graph invocation."""
    return GraphState(
        messages=[HumanMessage(content=user_text)],
        user_id=user_id,
        recalled=[],
        stored_ids=[],
    )


def assistant_reply(state: GraphState) -> str:
    """Extract the last assistant reply from a finished graph state."""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""
