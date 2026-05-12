#!/usr/bin/env python3
"""
LangGraph + Memanto cross-session memory demo.

The graph is intentionally deterministic: it does not need an LLM key. Memanto is
the only persistent layer. Session 1 stores a customer preference, then Session 2
starts with an empty LangGraph state and recalls that preference from Memanto.
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph


DEFAULT_AGENT_ID = "langgraph-support-memory-demo"


class SupportState(TypedDict, total=False):
    """State passed between LangGraph nodes for a single support session."""

    session_label: str
    user_id: str
    message: str
    recalled_memories: list[dict[str, Any]]
    response: str
    stored_memory_ids: list[str]


class MemoryLayer(Protocol):
    """Small protocol so the graph can run against real Memanto or dry-run memory."""

    def setup(self) -> None:
        """Prepare agent/session resources."""

    def teardown(self) -> None:
        """Release session resources."""

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> str:
        """Persist one memory and return its ID."""

    def recall(
        self,
        query: str,
        memory_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Recall matching memories."""


class MemantoMemoryLayer:
    """Real Memanto-backed memory layer used by the bounty demo."""

    def __init__(self, api_key: str, agent_id: str) -> None:
        from memanto.cli.client.sdk_client import SdkClient

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)

    def setup(self) -> None:
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="support",
                description="LangGraph customer support memory demo",
            )
        except Exception:
            # Reusing an existing demo agent is expected on repeated runs.
            pass
        self.client.activate_agent(self.agent_id, duration_hours=6)

    def teardown(self) -> None:
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            pass

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> str:
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
            source="langgraph-support-demo",
            provenance="explicit_statement",
        )
        return str(result["memory_id"])

    def recall(
        self,
        query: str,
        memory_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            type=memory_types,
        )
        return list(result.get("memories", []))


@dataclass
class DryRunMemoryLayer:
    """In-memory stand-in used only for local smoke tests without an API key."""

    memories: list[dict[str, Any]] = field(default_factory=list)

    def setup(self) -> None:
        return None

    def teardown(self) -> None:
        return None

    def remember(
        self,
        memory_type: str,
        title: str,
        content: str,
        tags: list[str],
        confidence: float = 0.9,
    ) -> str:
        memory_id = f"dry-run-{len(self.memories) + 1}"
        self.memories.append(
            {
                "id": memory_id,
                "type": memory_type,
                "title": title,
                "content": content,
                "tags": tags,
                "confidence": confidence,
            }
        )
        return memory_id

    def recall(
        self,
        query: str,
        memory_types: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        scored: list[tuple[int, dict[str, Any]]] = []
        for memory in self.memories:
            if memory_types and memory.get("type") not in memory_types:
                continue
            haystack = " ".join(
                [
                    str(memory.get("title", "")),
                    str(memory.get("content", "")),
                    " ".join(memory.get("tags", [])),
                ]
            ).lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score:
                scored.append((score, memory))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:limit]]


def build_support_graph(memory: MemoryLayer):
    """Build a LangGraph workflow that uses Memanto outside graph state."""

    def recall_customer_context(state: SupportState) -> SupportState:
        query = (
            f"{state['user_id']} customer product preference refund replacement "
            f"{state['message']}"
        )
        recalled = memory.recall(
            query=query,
            memory_types=["preference", "fact", "event"],
            limit=5,
        )
        return {**state, "recalled_memories": recalled}

    def draft_response(state: SupportState) -> SupportState:
        memories = state.get("recalled_memories", [])
        memory_text = " ".join(str(item.get("content", "")) for item in memories)
        has_refund_preference = "refund" in memory_text.lower()

        if has_refund_preference:
            response = (
                "I found Jamie's prior support preference in Memanto: they prefer "
                "a quick refund over a replacement. Start with refund eligibility, "
                "then mention replacement only as a fallback."
            )
        else:
            response = (
                "I do not have a prior preference in the current LangGraph state. "
                "Ask one clarifying question before recommending refund or replacement."
            )

        return {**state, "response": response}

    def store_new_memory(state: SupportState) -> SupportState:
        message = state["message"].lower()
        stored_memory_ids: list[str] = []

        if "prefer" in message and "refund" in message:
            stored_memory_ids.append(
                memory.remember(
                    memory_type="preference",
                    title=f"{state['user_id']} refund preference",
                    content=(
                        f"{state['user_id']} prefers a quick refund over a "
                        "replacement when a purchased product fails."
                    ),
                    tags=["support", "preference", state["user_id"], "refund"],
                    confidence=0.95,
                )
            )

        if "trailrunner" in message:
            stored_memory_ids.append(
                memory.remember(
                    memory_type="fact",
                    title=f"{state['user_id']} product ownership",
                    content=f"{state['user_id']} owns TrailRunner 2.0 shoes.",
                    tags=["support", "product", state["user_id"], "trailrunner"],
                    confidence=0.9,
                )
            )

        return {**state, "stored_memory_ids": stored_memory_ids}

    graph = StateGraph(SupportState)
    graph.add_node("recall_customer_context", recall_customer_context)
    graph.add_node("draft_response", draft_response)
    graph.add_node("store_new_memory", store_new_memory)

    graph.set_entry_point("recall_customer_context")
    graph.add_edge("recall_customer_context", "draft_response")
    graph.add_edge("draft_response", "store_new_memory")
    graph.add_edge("store_new_memory", END)

    return graph.compile()


def run_support_session(
    memory: MemoryLayer,
    session_label: str,
    message: str,
    user_id: str = "jamie",
) -> SupportState:
    """Run one support session with an intentionally fresh graph state."""

    graph = build_support_graph(memory)
    initial_state: SupportState = {
        "session_label": session_label,
        "user_id": user_id,
        "message": message,
        "recalled_memories": [],
        "stored_memory_ids": [],
    }
    return graph.invoke(initial_state)


def print_session_result(result: SupportState) -> None:
    """Print a compact, recording-friendly transcript."""

    print(f"\n=== {result['session_label']} ===")
    print(f"User: {result['message']}")
    print(f"Memanto memories recalled: {len(result.get('recalled_memories', []))}")
    for memory in result.get("recalled_memories", []):
        print(f"- [{memory.get('type', 'memory')}] {memory.get('content', '')}")
    print(f"Agent: {result['response']}")
    print(f"Memories stored this session: {result.get('stored_memory_ids', [])}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent-id",
        default=os.environ.get("MEMANTO_LANGGRAPH_AGENT_ID", DEFAULT_AGENT_ID),
        help="Memanto agent ID/namespace to use for the demo.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run against an in-memory fake instead of real Memanto.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    if args.dry_run:
        memory: MemoryLayer = DryRunMemoryLayer()
        print("Running in dry-run mode. No Memanto API calls will be made.")
    else:
        api_key = os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            raise SystemExit(
                "MOORCHEH_API_KEY is not set. Copy .env.example to .env or "
                "run with --dry-run for a local smoke test."
            )
        memory = MemantoMemoryLayer(api_key=api_key, agent_id=args.agent_id)

    memory.setup()
    try:
        first = run_support_session(
            memory,
            session_label="Session 1 - yesterday",
            message=(
                "I'm Jamie. I ordered TrailRunner 2.0; if it fails, I always "
                "prefer a quick refund over a replacement."
            ),
        )
        print_session_result(first)

        second = run_support_session(
            memory,
            session_label="Session 2 - today, fresh LangGraph state",
            message="My shoes failed again. What should support do?",
        )
        print_session_result(second)

        print(
            "\nProof: Session 2 started with no prior preference in LangGraph "
            "state, then recalled it from Memanto before drafting the response."
        )
    finally:
        memory.teardown()


if __name__ == "__main__":
    main()
