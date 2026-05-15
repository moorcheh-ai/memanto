
#!/usr/bin/env python3
"""
LangGraph + Memanto: Cross-Session Memory for AI Agents.

This module defines:
- MemoryClient protocol (abc)
- LocalMemoryClient: JSON-backed adapter for API-key-free review
- MemantoMemoryClient: Real SdkClient adapter for Moorcheh-backed memory
- LangGraph workflow factories for 4 use cases:
  1. Fitness Coach
  2. Blog Writer
  3. Travel Planner
  4. Per-Job Runner (runs all 3)

Architecture:
  User -> [SESSION_1: remember_node] -> Memanto
  User -> [SESSION_2: recall_node -> response_node] -> Memanto

Cross-session recall is demonstrated by starting session 2 with a fresh
LangGraph state that does NOT contain the memories stored in session 1.
"""

from __future__ import annotations

import abc
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# TypedDicts for LangGraph state
# ---------------------------------------------------------------------------

from typing import TypedDict

class AgentState(TypedDict):
    """LangGraph agent state."""
    agent_id: str
    session_id: str
    user_input: str
    memories_stored: list[dict]
    memories_recalled: list[dict]
    response: str
    done: bool


# ---------------------------------------------------------------------------
# MemoryClient Protocol
# ---------------------------------------------------------------------------

class MemoryClient(abc.ABC):
    """Protocol that LangGraph nodes consume for memory operations."""

    @abc.abstractmethod
    def remember(
        self,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> dict:
        ...

    @abc.abstractmethod
    def recall(
        self,
        agent_id: str,
        query: str,
        limit: int = 5,
        type: list[str] | None = None,
    ) -> dict:
        ...

    @abc.abstractmethod
    def answer(
        self,
        agent_id: str,
        question: str,
        limit: int = 5,
    ) -> dict:
        ...


# ---------------------------------------------------------------------------
# LocalMemoryClient - JSON fallback for API-key-free review
# ---------------------------------------------------------------------------

@dataclass
class LocalMemoryClient(MemoryClient):
    """Stores memories in a local JSON file for offline review."""

    file_path: str = "local_memories.json"
    _memories: list[dict] = field(default_factory=list, init=False)

    def __post_init__(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r", encoding="utf-8") as f:
                self._memories = json.load(f)
        self._counter = len(self._memories) + 1

    def remember(
        self,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> dict:
        mem = {
            "id": f"local_{self._counter}",
            "agent_id": agent_id,
            "type": memory_type,
            "title": title,
            "content": content,
            "confidence": confidence,
            "tags": tags or [],
            "created_at": datetime.now().isoformat(),
        }
        self._memories.append(mem)
        self._counter += 1
        self._save()
        return {"memory_id": mem["id"], "agent_id": agent_id, "status": "stored"}

    def recall(
        self,
        agent_id: str,
        query: str,
        limit: int = 5,
        type: list[str] | None = None,
    ) -> dict:
        # Simple substring match recall (for local testing)
        query_lower = query.lower()
        results = []
        for m in self._memories:
            if m["agent_id"] != agent_id:
                continue
            if type and m["type"] not in type:
                continue
            score = 0
            for word in query_lower.split():
                if word in m["title"].lower():
                    score += 3
                if word in m["content"].lower():
                    score += 1
            if score > 0:
                results.append((score, m))
        results.sort(key=lambda x: x[0], reverse=True)
        memories = [m for _, m in results[:limit]]

        # Format for LangChain compatibility
        formatted = []
        for m in memories:
            formatted.append({
                "id": m["id"],
                "title": m["title"],
                "content": m["content"],
                "type": m["type"],
                "confidence": m["confidence"],
                "tags": m["tags"],
                "created_at": m["created_at"],
            })

        return {
            "agent_id": agent_id,
            "query": query,
            "memories": formatted,
            "count": len(formatted),
        }

    def answer(
        self,
        agent_id: str,
        question: str,
        limit: int = 5,
    ) -> dict:
        recalled = self.recall(agent_id, question, limit=limit)
        mems = recalled["memories"]
        if mems:
            answer = f"[Local answer based on {len(mems)} memories] "
            answer += " | ".join(m["title"] for m in mems)
        else:
            answer = "No relevant memories found."
        return {
            "agent_id": agent_id,
            "question": question,
            "answer": answer,
            "sources": [m["id"] for m in mems],
        }

    def _save(self):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self._memories, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# MemantoMemoryClient - Real SdkClient adapter
# ---------------------------------------------------------------------------

class MemantoMemoryClient(MemoryClient):
    """Wraps Memanto's SdkClient for use in LangGraph nodes."""

    def __init__(self, sdk_client, session_token: str | None = None):
        self._client = sdk_client
        self._session_token = session_token

    def remember(
        self,
        agent_id: str,
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.9,
        tags: list[str] | None = None,
    ) -> dict:
        return self._client.remember(
            agent_id=agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
        )

    def recall(
        self,
        agent_id: str,
        query: str,
        limit: int = 5,
        type: list[str] | None = None,
    ) -> dict:
        return self._client.recall(
            agent_id=agent_id,
            query=query,
            limit=limit,
            type=type,
        )

    def answer(
        self,
        agent_id: str,
        question: str,
        limit: int = 5,
    ) -> dict:
        return self._client.answer(
            agent_id=agent_id,
            question=question,
            limit=limit,
        )


# ---------------------------------------------------------------------------
# LangGraph Node Factories
# ---------------------------------------------------------------------------

def make_remember_node(memory: MemoryClient):
    """Create a LangGraph node that stores a memory.
    
    Expects state to have: agent_id, user_input (parsed as TYPE|TITLE|CONTENT)
    """
    def remember_node(state: AgentState) -> dict:
        agent_id = state["agent_id"]
        user_input = state["user_input"]

        # Parse input: TYPE|TITLE|CONTENT
        parts = user_input.split("|", 2)
        if len(parts) >= 3:
            mem_type, title, content = parts[0].strip(), parts[1].strip(), parts[2].strip()
            result = memory.remember(
                agent_id=agent_id,
                memory_type=mem_type,
                title=title,
                content=content,
            )
            state["memories_stored"].append(result)
            state["response"] = f"Stored: [{result['memory_id']}] {title}"
        else:
            state["response"] = "Invalid input format. Use: TYPE|TITLE|CONTENT"

        state["done"] = True
        return state

    return remember_node


def make_recall_node(memory: MemoryClient):
    """Create a LangGraph node that recalls memories."""
    def recall_node(state: AgentState) -> dict:
        agent_id = state["agent_id"]
        query = state["user_input"]

        result = memory.recall(agent_id=agent_id, query=query, limit=5)
        state["memories_recalled"] = result["memories"]
        state["response"] = f"Recalled {result['count']} memories for query: {query}"
        state["done"] = True
        return state

    return recall_node


def make_answer_node(memory: MemoryClient):
    """Create a LangGraph node that answers a question based on memories."""
    def answer_node(state: AgentState) -> dict:
        agent_id = state["agent_id"]
        question = state["user_input"]

        result = memory.answer(agent_id=agent_id, question=question, limit=5)
        state["response"] = result["answer"]
        state["done"] = True
        return state

    return answer_node


# ---------------------------------------------------------------------------
# MemoryClient Factory
# ---------------------------------------------------------------------------

def create_memory_client(mode: str = "local", **kwargs) -> MemoryClient:
    """Factory that returns the right MemoryClient based on mode.

    Args:
        mode: "local" or "real"
        **kwargs: Passed to the client constructor
    """
    if mode == "real":
        from memanto.cli.client.sdk_client import SdkClient
        from memanto.cli.config.manager import ConfigManager

        api_key = kwargs.get("api_key") or os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            raise ValueError("MOORCHEH_API_KEY required for real mode")

        sdk = SdkClient(api_key=api_key)
        return MemantoMemoryClient(sdk)

    return LocalMemoryClient(**kwargs)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("This module is a library. Run run_demo.py instead.")
    sys.exit(0)
