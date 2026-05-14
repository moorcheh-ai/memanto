from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from memory_client import MemantoCLI, RememberRequest

load_dotenv()


@dataclass
class MemoryCandidate:
    content: str
    memory_type: str
    tags: str


class SupportState(TypedDict, total=False):
    customer_id: str
    session_label: str
    message: str
    memory_context: str
    extracted_memories: list[MemoryCandidate]
    reply: str
    persisted_count: int
    used_llm: bool


def extract_memories(customer_id: str, message: str) -> list[MemoryCandidate]:
    text = message.strip()
    lowered = text.lower()
    candidates: list[MemoryCandidate] = []

    name_match = re.search(r"(?:i am|i'm|call me)\s+([A-Z][a-zA-Z0-9_-]{1,30})", text)
    if name_match:
        name = name_match.group(1)
        candidates.append(
            MemoryCandidate(
                content=f"Customer {customer_id} prefers to be addressed as {name}.",
                memory_type="preference",
                tags=f"customer,{customer_id},name",
            )
        )

    preference_patterns = [
        (r"prefer[s]? ([^.]+)", "preference"),
        (r"always ([^.]+)", "instruction"),
        (r"timezone is ([^.]+)", "fact"),
    ]
    for pattern, memory_type in preference_patterns:
        for match in re.finditer(pattern, lowered):
            detail = match.group(1).strip(" .")
            if detail:
                candidates.append(
                    MemoryCandidate(
                        content=f"Customer {customer_id} said: {detail}.",
                        memory_type=memory_type,
                        tags=f"customer,{customer_id},{memory_type}",
                    )
                )

    explicit_settings = [
        "dark mode",
        "light mode",
        "weekly email digests",
        "daily updates",
        "slack",
        "email",
        "sms",
    ]
    for phrase in explicit_settings:
        if phrase in lowered:
            candidates.append(
                MemoryCandidate(
                    content=f"Customer {customer_id} mentioned {phrase}.",
                    memory_type="preference",
                    tags=f"customer,{customer_id},preference",
                )
            )

    unique: dict[tuple[str, str], MemoryCandidate] = {}
    for candidate in candidates:
        unique[(candidate.content, candidate.memory_type)] = candidate
    return list(unique.values())


def summarise_memory_context(raw_context: str) -> list[str]:
    lines = [line.strip("-• ") for line in raw_context.splitlines()]
    return [line for line in lines if line and len(line) > 4][:4]


def build_optional_llm():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from langchain_openai import ChatOpenAI
    except Exception:
        return None

    return ChatOpenAI(
        model=os.getenv("LANGGRAPH_DEMO_MODEL", "gpt-4.1-mini"),
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        temperature=0,
    )


def build_graph(memanto: MemantoCLI):
    llm = build_optional_llm()

    def retrieve_context(state: SupportState) -> SupportState:
        query = (
            f"customer {state['customer_id']} preferences, name, delivery habits, "
            f"and anything relevant to: {state['message']}"
        )
        context = memanto.recall(query, limit=5)
        return {
            **state,
            "memory_context": context,
            "extracted_memories": extract_memories(state["customer_id"], state["message"]),
        }

    def draft_reply(state: SupportState) -> SupportState:
        memory_lines = summarise_memory_context(state.get("memory_context", ""))
        if llm:
            prompt = "\n".join(
                [
                    "You are a helpful customer support assistant.",
                    f"Session label: {state['session_label']}",
                    f"Customer ID: {state['customer_id']}",
                    f"Current message: {state['message']}",
                    "Relevant memories:",
                    *(memory_lines or ["No prior memory found."]),
                    "Write a concise reply that uses the memories when they help.",
                ]
            )
            response = llm.invoke(prompt)
            reply_text = getattr(response, "content", str(response)).strip()
            return {**state, "reply": reply_text, "used_llm": True}

        reply_parts = []
        if memory_lines:
            reply_parts.append("From earlier sessions, I remember:")
            reply_parts.extend(f"- {line}" for line in memory_lines)

        if state["extracted_memories"]:
            reply_parts.append("I also captured the new preference you shared for future sessions.")
        elif not memory_lines:
            reply_parts.append("I do not have prior memory for this customer yet, so this turn will establish the baseline.")

        if "remember" in state["message"].lower() or "what do you know" in state["message"].lower():
            reply_parts.append("That is the relevant memory context I would use before responding in a real support flow.")
        else:
            reply_parts.append("How would you like me to use that context on the next step?")

        return {**state, "reply": "\n".join(reply_parts), "used_llm": False}

    def persist_memories(state: SupportState) -> SupportState:
        requests = [
            RememberRequest(
                content=candidate.content,
                memory_type=candidate.memory_type,
                tags=candidate.tags,
                source=f"langgraph-session:{state['session_label']}",
            )
            for candidate in state["extracted_memories"]
        ]
        persisted = memanto.remember_many(requests) if requests else 0
        return {**state, "persisted_count": persisted}

    graph = StateGraph(SupportState)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("draft_reply", draft_reply)
    graph.add_node("persist_memories", persist_memories)
    graph.add_edge(START, "retrieve_context")
    graph.add_edge("retrieve_context", "draft_reply")
    graph.add_edge("draft_reply", "persist_memories")
    graph.add_edge("persist_memories", END)
    return graph.compile()


def run_support_turn(
    *,
    agent_id: str,
    customer_id: str,
    session_label: str,
    message: str,
) -> SupportState:
    memanto = MemantoCLI(agent_id)
    memanto.ensure_agent()
    graph = build_graph(memanto)
    return graph.invoke(
        {
            "customer_id": customer_id,
            "session_label": session_label,
            "message": message,
        }
    )
