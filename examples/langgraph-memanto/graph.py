"""LangGraph support workflow that uses Memanto as long-term memory."""

from __future__ import annotations

import re

from langgraph.graph import END, START, StateGraph
from memory_store import MemoryStore
from state import StoredMemory, SupportState


def build_support_graph(memory_store: MemoryStore):
    """Build a LangGraph StateGraph wired to an external memory store."""
    workflow = StateGraph(SupportState)

    workflow.add_node("recall_context", _recall_context(memory_store))
    workflow.add_node("classify_intent", _classify_intent)
    workflow.add_node("draft_response", _draft_response)
    workflow.add_node("remember_update", _remember_update(memory_store))

    workflow.add_edge(START, "recall_context")
    workflow.add_edge("recall_context", "classify_intent")
    workflow.add_edge("classify_intent", "draft_response")
    workflow.add_edge("draft_response", "remember_update")
    workflow.add_edge("remember_update", END)

    return workflow.compile()


def _recall_context(memory_store: MemoryStore):
    def node(state: SupportState) -> dict[str, object]:
        query = f"{state['customer_id']} {state['message']}"
        return {"recalled_memories": memory_store.recall(query, limit=5)}

    return node


def _classify_intent(state: SupportState) -> dict[str, str]:
    message = state["message"].lower()
    if any(word in message for word in ["remind", "remember", "recall"]):
        intent = "recall"
    elif any(word in message for word in ["broken", "failing", "blocked", "issue"]):
        intent = "triage"
    elif any(word in message for word in ["prefer", "please keep", "always"]):
        intent = "preference"
    else:
        intent = "support"
    return {"intent": intent}


def _draft_response(state: SupportState) -> dict[str, str]:
    memories = state.get("recalled_memories", [])
    intent = state.get("intent", "support")

    if memories:
        remembered = "\n".join(
            f"- {memory['title']}: {memory['content']}" for memory in memories[:3]
        )
        response = (
            f"I found durable context for {state['customer_id']}:\n"
            f"{remembered}\n\n"
            f"Given this is a {intent} request, I would prioritize the OAuth redirect "
            "regression first and keep the answer concise and technical."
        )
    else:
        response = (
            f"I do not have prior long-term memory for {state['customer_id']} yet. "
            "I can store the important facts from this session so the next run can "
            "recall them without relying on LangGraph thread state."
        )

    return {"response": response}


def _remember_update(memory_store: MemoryStore):
    def node(state: SupportState) -> dict[str, list[StoredMemory]]:
        memories = _extract_memory_candidates(state)
        for memory in memories:
            memory_store.remember(
                memory["type"],
                memory["title"],
                memory["content"],
                tags=memory["tags"],
            )
        return {"new_memories": memories}

    return node


def _extract_memory_candidates(state: SupportState) -> list[StoredMemory]:
    message = state["message"].strip()
    customer_id = state["customer_id"]
    memories: list[StoredMemory] = []

    if not message:
        return memories

    preference = _extract_preference(message)
    issue = _extract_issue(message)

    if preference or issue or _looks_persistable(message):
        memories.append(
            {
                "type": "context",
                "title": f"{customer_id} support update",
                "content": _squash(f"{customer_id}: {message}"),
                "tags": [customer_id, state["session_label"], "langgraph"],
            }
        )

    if preference:
        memories.append(
            {
                "type": "preference",
                "title": f"{customer_id} communication preference",
                "content": _squash(preference),
                "tags": [customer_id, "preference"],
            }
        )

    if issue:
        memories.append(
            {
                "type": "fact",
                "title": f"{customer_id} active issue",
                "content": _squash(issue),
                "tags": [customer_id, "issue"],
            }
        )

    return memories


def _extract_preference(message: str) -> str | None:
    match = re.search(r"(prefer|please keep|always)\s+([^.;,]+)", message, re.I)
    if not match:
        return None
    return match.group(0)


def _extract_issue(message: str) -> str | None:
    clauses = re.split(r"[.;]|,\s+|\s+and\s+", message)
    for clause in clauses:
        if re.search(r"\b(failing|broken|blocked|regression)\b", clause, re.I):
            return re.sub(r"^(and|but|or)\s+", "", clause.strip(), flags=re.I)
    return None


def _looks_persistable(message: str) -> bool:
    return bool(re.search(r"\b(i am|i'm|we are|we run|our)\b", message, re.I))


def _squash(text: str, max_length: int = 480) -> str:
    return " ".join(text.split())[:max_length]
