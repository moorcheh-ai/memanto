"""LangGraph-compatible tools wrapping Memanto's memory operations."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from memanto.cli.client.sdk_client import SdkClient


def _get_client(
    api_key: Optional[str] = None,
    agent_id: Optional[str] = None,
    auto_create: bool = True,
    pattern: str = "tool",
) -> SdkClient:
    """Return a configured SdkClient (singleton per agent_id in simple caching)."""
    key = api_key or os.getenv("MOORCHEH_API_KEY")
    if not key:
        raise ValueError("MOORCHEH_API_KEY must be provided or set in environment")
    agent = agent_id or os.getenv("MEMANTO_DEFAULT_AGENT_ID") or "langgraph-agent"
    return SdkClient(
        api_key=key,
        agent_id=agent,
        auto_create=auto_create,
        pattern=pattern,
    )


def remember(
    memory: str,
    memory_type: str = "fact",
    tags: Optional[List[str]] = None,
    confidence: Optional[float] = None,
    provenance: Optional[str] = None,
    api_key: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Store a memory into the Memanto agent's semantic database.

    Args:
        memory: The text to remember.
        memory_type: One of Memanto's 13 types (fact, preference, goal...).
        tags: Optional list of tags for filtering.
        confidence: 0.0–1.0 level of certainty.
        provenance: e.g. explicit_statement, inferred, observed.
        api_key: Override API key (falls back to env).
        agent_id: Override agent ID (falls back to env or default).

    Returns:
        Dict with status and memory_id.
    """
    client = _get_client(api_key=api_key, agent_id=agent_id)
    payload = {
        "memory": memory,
        "memory_type": memory_type,
    }
    if tags:
        payload["tags"] = tags
    if confidence is not None:
        payload["confidence"] = confidence
    if provenance:
        payload["provenance"] = provenance
    # Ensure session is active
    client.activate_session()
    return client.remember(**payload)


def recall(
    query: str,
    limit: int = 10,
    memory_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    confidence_min: Optional[float] = None,
    api_key: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search memories by semantic similarity.

    Args:
        query: Natural language query.
        limit: Maximum number of results.
        memory_type: Filter by a specific memory type.
        tags: Filter by tags.
        confidence_min: Minimum confidence threshold (0.0–1.0).

    Returns:
        List of matching memory dicts.
    """
    client = _get_client(api_key=api_key, agent_id=agent_id)
    filters = {}
    if memory_type:
        filters["memory_type"] = memory_type
    if tags:
        filters["tags"] = tags
    if confidence_min is not None:
        filters["confidence_min"] = confidence_min
    client.activate_session()
    result = client.recall(query=query, filters=filters, limit=limit)
    return result.get("memories", [])


def answer(
    question: str,
    api_key: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> str:
    """Generate a grounded answer from memory (RAG).

    Args:
        question: The question to answer based on stored memories.

    Returns:
        The answer text.
    """
    client = _get_client(api_key=api_key, agent_id=agent_id)
    client.activate_session()
    result = client.answer(question=question)
    return result.get("answer", "")


def batch_remember(
    memories: List[Dict[str, Any]],
    api_key: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Store multiple memories in one call.

    Args:
        memories: List of dicts, each with 'memory' and optional
                  'memory_type', 'tags', 'confidence', 'provenance'.

    Returns:
        Dict with status.
    """
    client = _get_client(api_key=api_key, agent_id=agent_id)
    client.activate_session()
    return client.batch_remember(memories=memories)


def create_memanto_tools(
    api_key: Optional[str] = None,
    agent_id: Optional[str] = None,
    auto_create: bool = True,
    pattern: str = "tool",
) -> Dict[str, Any]:
    """Return a dict of callable tools bound to the given agent.

    Usage inside a LangGraph node:
        tools = create_memanto_tools(agent_id="my-agent")
        tools["remember"]("The user likes dark mode")
        results = tools["recall"]("What theme does the user like?")

    Returns a dict with keys: "remember", "recall", "answer", "batch_remember".
    """
    # Partially apply the api_key and agent_id
    return {
        "remember": lambda memory, memory_type="fact", tags=None, confidence=None, provenance=None: remember(
            memory=memory,
            memory_type=memory_type,
            tags=tags,
            confidence=confidence,
            provenance=provenance,
            api_key=api_key,
            agent_id=agent_id,
        ),
        "recall": lambda query, limit=10, memory_type=None, tags=None, confidence_min=None: recall(
            query=query,
            limit=limit,
            memory_type=memory_type,
            tags=tags,
            confidence_min=confidence_min,
            api_key=api_key,
            agent_id=agent_id,
        ),
        "answer": lambda question: answer(
            question=question,
            api_key=api_key,
            agent_id=agent_id,
        ),
        "batch_remember": lambda memories: batch_remember(
            memories=memories,
            api_key=api_key,
            agent_id=agent_id,
        ),
    }
