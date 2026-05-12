"""
Agent: LangGraph + Memanto Integration

A LangGraph customer support agent that uses Memanto as its
long-term memory layer for cross-session recall.
"""

import logging
import os
from typing import Any, Literal, Optional

import requests
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from typing_extensions import TypedDict

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("langgraph-memanto")

# ── Types ────────────────────────────────────────────────────────────────────


class AgentState(TypedDict):
    """The state passed between LangGraph nodes."""

    messages: list[dict[str, str]]
    user_id: str
    session_id: str
    memories_recalled: list[dict[str, Any]]
    new_memories: list[dict[str, Any]]
    output: str


# ── Memanto Memory Client ────────────────────────────────────────────────────


class MemantoMemory:
    """Long-term memory backed by Memanto REST API.

    This client wraps Memanto's three core primitives:
    - remember()  → store a memory
    - recall()    → semantic search over memories
    - answer()    → LLM-grounded response from memory

    Memanto stores memories outside the LangGraph state, so they
    persist across sessions — enabling true cross-session recall.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
    ):
        self.base_url = os.environ.get("MEMANTO_BASE_URL", base_url).rstrip("/")
        self.api_key = api_key or os.environ.get("MOORCHEH_API_KEY", "")
        self._session_token: str | None = None
        self._agent_id: str | None = None

    # ------------------------------------------------------------------
    # Agent lifecycle
    # ------------------------------------------------------------------

    def create_agent(self, name: str = "langgraph-agent") -> str:
        """Register an agent with Memanto and get its ID."""
        resp = requests.post(
            f"{self.base_url}/api/v2/agents",
            json={
                "name": name,
                "description": "LangGraph agent with Memanto long-term memory",
            },
            headers={"X-API-Key": self.api_key},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._agent_id = data["agent_id"]
        logger.info("Created Memanto agent: %s", self._agent_id)
        return self._agent_id

    def activate_agent(self) -> str:
        """Start a session and get a session token."""
        assert self._agent_id, "Create the agent first with create_agent()"
        resp = requests.post(
            f"{self.base_url}/api/v2/agents/{self._agent_id}/activate",
            headers={"X-API-Key": self.api_key},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._session_token = data["session_token"]
        logger.info("Activated agent, got session token")
        return self._session_token

    # ------------------------------------------------------------------
    # Memory primitives
    # ------------------------------------------------------------------

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        title: str | None = None,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> str:
        """Store a memory. Returns the memory ID."""
        assert self._session_token, "Activate the agent first"
        payload: dict[str, Any] = {
            "type": memory_type,
            "title": title or content[:80],
            "content": content,
            "confidence": confidence,
        }
        if tags:
            payload["tags"] = tags

        resp = requests.post(
            f"{self.base_url}/api/v2/agents/{self._agent_id}/remember",
            headers={
                "X-Session-Token": self._session_token,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        memory_id = result.get("id", "")
        logger.info("Remembered [%s]: %s", memory_type, content[:60])
        return memory_id

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve memories by semantic similarity. The core of cross-session recall!"""
        assert self._session_token, "Activate the agent first"
        payload: dict[str, Any] = {"query": query, "limit": limit}
        if memory_types:
            payload["type"] = memory_types

        resp = requests.post(
            f"{self.base_url}/api/v2/agents/{self._agent_id}/recall",
            headers={
                "X-Session-Token": self._session_token,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        memories = result.get("results", [])
        logger.info("Recalled %d memories for: %s", len(memories), query[:50])
        return memories

    def answer(self, query: str) -> str:
        """Get an LLM-grounded answer synthesized from your memories."""
        assert self._session_token, "Activate the agent first"
        resp = requests.post(
            f"{self.base_url}/api/v2/agents/{self._agent_id}/answer",
            headers={
                "X-Session-Token": self._session_token,
                "Content-Type": "application/json",
            },
            json={"query": query},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("answer", "")

    def close(self):
        """Clean up session."""
        self._session_token = None


# ── LangGraph Nodes ──────────────────────────────────────────────────────────


def recall_memories(state: AgentState, memory: MemantoMemory) -> dict:
    """Retrieve relevant memories from Memanto for the current conversation."""
    query = state["messages"][-1]["content"] if state["messages"] else ""
    memories = memory.recall(query=query, limit=5)

    return {
        "memories_recalled": [
            {
                "content": m.get("content", ""),
                "type": m.get("memory_type", "unknown"),
                "confidence": m.get("confidence", 0.0),
                "created_at": m.get("created_at", ""),
            }
            for m in memories
        ]
    }


def process_with_memories(state: AgentState) -> dict:
    """Simulate processing user input with recalled context.

    In a production system, this would be an LLM call with:
      system_prompt + recalled_memories + user_message → response

    Here we demonstrate the architecture pattern clearly.
    """
    memories = state["memories_recalled"]
    user_msg = state["messages"][-1]["content"] if state["messages"] else ""

    # Build context from recalled memories
    memory_context = ""
    if memories:
        memory_lines = []
        for m in memories:
            memory_lines.append(
                f"  - [{m['type']}] (confidence: {m['confidence']:.0%}): {m['content']}"
            )
        memory_context = "I recall from past sessions:\n" + "\n".join(memory_lines)

    # Simulated response (in production, use an LLM call here)
    if memory_context:
        output = (
            f"[RECALLING MEMORIES FROM PREVIOUS SESSION]\n{memory_context}\n\n"
            f"Based on what I know about you and what you just said "
            f"('{user_msg[:50]}...'), I can help with that!"
        )
    else:
        output = (
            f"[NO PRIOR MEMORIES — This is the first session]\n"
            f"You said: '{user_msg[:60]}...'\n"
            f"Let me learn about you so I can help better next time!"
        )

    return {"output": output}


def store_memories(state: AgentState, memory: MemantoMemory) -> dict:
    """Extract important information and store as memories.

    In production, this would use an LLM to extract structured memories.
    Here we extract key facts from the conversation.
    """
    user_msg = state["messages"][-1]["content"] if state["messages"] else ""
    new_ids = []

    # Extract facts from user messages (simulated — use LLM extraction in prod)
    fact_prefixes = [
        "my name is",
        "i am",
        "i like",
        "i prefer",
        "i need",
        "my email",
        "i work",
    ]

    msg_lower = user_msg.lower()
    for prefix in fact_prefixes:
        if prefix in msg_lower:
            idx = msg_lower.index(prefix)
            fact = user_msg[idx : idx + 100].split(".")[0].strip()
            mid = memory.remember(
                content=fact,
                memory_type="fact" if "name" in prefix or "email" in prefix else "preference",
                confidence=0.85,
                tags=["extracted", "user-profile"],
            )
            new_ids.append(mid)

    return {"new_memories": [{"id": mid} for mid in new_ids]}


# ── Graph Construction ───────────────────────────────────────────────────────


def build_agent(memory: MemantoMemory) -> CompiledStateGraph:
    """Build the LangGraph agent with Memanto memory integration."""

    # Wrapper functions to inject the memory client
    def _recall(state: AgentState) -> dict:
        return recall_memories(state, memory)

    def _store(state: AgentState) -> dict:
        return store_memories(state, memory)

    workflow = StateGraph(AgentState)

    # Nodes
    workflow.add_node("recall_memories", _recall)
    workflow.add_node("process", process_with_memories)
    workflow.add_node("store_memories", _store)

    # Edges
    workflow.set_entry_point("recall_memories")
    workflow.add_edge("recall_memories", "process")
    workflow.add_edge("process", "store_memories")
    workflow.add_edge("store_memories", END)

    return workflow.compile()
