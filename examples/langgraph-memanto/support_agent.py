#!/usr/bin/env python3
"""
LangGraph + Memanto support agent demo.

This example shows a two-session support workflow where LangGraph state is
intentionally reset between sessions, while user preferences survive in
Memanto as the external long-term memory layer.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypedDict, cast

from dotenv import load_dotenv

warnings.filterwarnings(
    "ignore",
    message="The default value of `allowed_objects` will change.*",
)
try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
except Exception:
    pass

from langgraph.graph import END, START, StateGraph

from memanto.cli.client.sdk_client import SdkClient

DEFAULT_AGENT_ID = "langgraph-support-agent"
DEFAULT_MOCK_STORE = Path("/tmp/memanto-langgraph-support-memory.json")


class SupportState(TypedDict, total=False):
    """State that LangGraph passes between nodes for one support session."""

    user_id: str
    session_id: str
    message: str
    recalled_memories: list[dict[str, Any]]
    reply: str
    stored_memory_id: str


class MemoryGateway(Protocol):
    """Minimal memory contract used by the LangGraph nodes."""

    def remember_preference(self, user_id: str, content: str, tags: list[str]) -> str:
        """Persist a support preference outside the LangGraph state."""

    def recall_user_context(self, user_id: str, query: str) -> list[dict[str, Any]]:
        """Retrieve support memories for a user from outside the current state."""

    def close(self) -> None:
        """Release any session resources."""


@dataclass
class MemantoGateway:
    """Production gateway backed by Memanto's SDK client."""

    api_key: str
    agent_id: str

    def __post_init__(self) -> None:
        self.client = SdkClient(api_key=self.api_key)
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="langgraph",
                description=(
                    "LangGraph customer support agent with Memanto long-term memory"
                ),
            )
        except Exception:
            # Reusing an existing agent is expected when replaying the demo.
            pass
        self.client.activate_agent(self.agent_id, duration_hours=6)

    def remember_preference(self, user_id: str, content: str, tags: list[str]) -> str:
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type="preference",
            title=f"Support preferences for {user_id}",
            content=content[:500],
            confidence=0.95,
            tags=["langgraph", "support", user_id, *tags],
            source="langgraph-support-demo",
            provenance="explicit_statement",
        )
        return str(result["memory_id"])

    def recall_user_context(self, user_id: str, query: str) -> list[dict[str, Any]]:
        result = self.client.recall(
            agent_id=self.agent_id,
            query=f"{user_id}: {query}",
            limit=5,
            type=["preference", "fact", "context"],
            tags=[user_id],
        )
        return list(result.get("memories", []))

    def close(self) -> None:
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            pass


@dataclass
class FileMemoryGateway:
    """
    Offline demo gateway that mirrors Memanto's contract.

    It writes to a JSON file so reviewers can run the example without a
    Moorcheh API key while still seeing that memory lives outside LangGraph
    state and survives the session reset.
    """

    store_path: Path

    def __post_init__(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self.store_path.write_text("[]\n", encoding="utf-8")

    def _read(self) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            json.loads(self.store_path.read_text(encoding="utf-8")),
        )

    def _write(self, memories: list[dict[str, Any]]) -> None:
        self.store_path.write_text(json.dumps(memories, indent=2) + "\n", "utf-8")

    def remember_preference(self, user_id: str, content: str, tags: list[str]) -> str:
        memories = self._read()
        memory_id = f"mock-{len(memories) + 1}"
        memories.append(
            {
                "id": memory_id,
                "type": "preference",
                "title": f"Support preferences for {user_id}",
                "content": content[:500],
                "confidence": 0.95,
                "tags": ["langgraph", "support", user_id, *tags],
            }
        )
        self._write(memories)
        return memory_id

    def recall_user_context(self, user_id: str, query: str) -> list[dict[str, Any]]:
        query_terms = {term.lower() for term in query.replace("?", "").split()}
        matches = []
        for memory in self._read():
            if user_id not in memory.get("tags", []):
                continue
            content_terms = set(memory.get("content", "").lower().split())
            title_terms = set(memory.get("title", "").lower().split())
            score = len(query_terms & (content_terms | title_terms))
            matches.append((score, memory))
        matches.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in matches[:5]]

    def close(self) -> None:
        return None


def build_support_graph(memory: MemoryGateway):
    """Create the LangGraph workflow with Memanto-backed memory nodes."""

    def recall_context(state: SupportState) -> SupportState:
        memories = memory.recall_user_context(
            user_id=state["user_id"],
            query="support style preferences and technical detail preferences",
        )
        return {"recalled_memories": memories}

    def draft_reply(state: SupportState) -> SupportState:
        memories = state.get("recalled_memories", [])
        style_hint = "No prior preferences found."
        if memories:
            style_hint = memories[0].get("content", style_hint)

        reply = (
            f"Session {state['session_id']} reply for {state['user_id']}:\n"
            f"- Remembered context: {style_hint}\n"
            "- Answer: Use exponential backoff with jitter, cap retries, and log "
            "the final failure reason."
        )
        return {"reply": reply}

    def persist_new_preferences(state: SupportState) -> SupportState:
        message = state["message"].lower()
        tags: list[str] = []
        preferences: list[str] = []

        if "concise" in message:
            preferences.append("prefers concise support answers")
            tags.append("concise")
        if "technical" in message or "links" in message:
            preferences.append("wants technical detail links when useful")
            tags.append("technical")

        if not preferences:
            return {}

        content = f"{state['user_id']} " + " and ".join(preferences) + "."
        memory_id = memory.remember_preference(
            user_id=state["user_id"],
            content=content,
            tags=tags,
        )
        return {"stored_memory_id": memory_id}

    graph = StateGraph(SupportState)
    graph.add_node("recall_context", recall_context)
    graph.add_node("draft_reply", draft_reply)
    graph.add_node("persist_new_preferences", persist_new_preferences)

    graph.add_edge(START, "recall_context")
    graph.add_edge("recall_context", "draft_reply")
    graph.add_edge("draft_reply", "persist_new_preferences")
    graph.add_edge("persist_new_preferences", END)
    return graph.compile()


def run_demo(memory: MemoryGateway) -> None:
    """Run two isolated sessions to prove cross-session recall."""

    graph = build_support_graph(memory)

    print("\nSession 1: capture an explicit preference")
    first_state: SupportState = {
        "user_id": "alex",
        "session_id": "2026-05-10",
        "message": (
            "I am Alex. For future support, keep answers concise but include "
            "technical links when they matter."
        ),
    }
    first_result = graph.invoke(first_state)
    print(first_result["reply"])
    print(f"Stored memory id: {first_result.get('stored_memory_id', 'none')}")

    print("\n--- LangGraph state reset between sessions ---")
    print("Session 2 only includes user_id and the new question.")

    second_state: SupportState = {
        "user_id": "alex",
        "session_id": "2026-05-11",
        "message": "How should I configure retries for the API client?",
    }
    second_result = graph.invoke(second_state)
    print(second_result["reply"])
    print(
        "Recalled memory titles:",
        [memory["title"] for memory in second_result.get("recalled_memories", [])],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mock-memory",
        action="store_true",
        help="Use the offline JSON memory gateway instead of the Memanto SDK.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear the offline memory store before running the mock demo.",
    )
    parser.add_argument(
        "--mock-store",
        type=Path,
        default=DEFAULT_MOCK_STORE,
        help=f"Path for --mock-memory persistence. Default: {DEFAULT_MOCK_STORE}",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    if args.mock_memory:
        if args.reset and args.mock_store.exists():
            args.mock_store.unlink()
        memory: MemoryGateway = FileMemoryGateway(args.mock_store)
    else:
        api_key = os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            raise SystemExit(
                "MOORCHEH_API_KEY is required. Copy .env.example to .env, "
                "or rerun with --mock-memory for the offline demo."
            )
        memory = MemantoGateway(
            api_key=api_key,
            agent_id=os.environ.get(
                "MEMANTO_LANGGRAPH_AGENT_ID",
                DEFAULT_AGENT_ID,
            ),
        )

    try:
        run_demo(memory)
    finally:
        memory.close()


if __name__ == "__main__":
    main()
