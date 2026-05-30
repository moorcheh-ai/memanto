"""
Pre/Post Execution Hooks for Memory Injection.

Provides hook functions that can be used outside of LangGraph nodes
for integrating Memanto memory into existing workflows:

- pre_execution_hook: Recall memories and format for LLM system prompt
- post_execution_hook: Extract signals from I/O and store to Memanto

These hooks enable cross-session memory recall across different
conversation threads that share the same Memanto backend.
"""

from __future__ import annotations

import os
from typing import Any

from memory_backend import LocalBackend, MemoryBackend, get_backend
from memory_nodes import (
    extract_from_file_references,
    extract_signals,
    format_memory_context,
)


def pre_execution_hook(
    user_input: str,
    session_id: str = "default",
    stage: str | None = None,
    backend: MemoryBackend | None = None,
) -> str:
    """Pre-execution hook: recall relevant memories and return formatted context.

    This should be called BEFORE the LLM processes user input. The returned
    context string should be injected into the LLM's system prompt.

    Args:
        user_input: The user's input text.
        session_id: Session identifier for cross-session recall.
        stage: Optional workflow stage tag.
        backend: MemoryBackend instance. Uses default if None.

    Returns:
        Formatted memory context string for LLM injection.
    """
    _backend = backend or get_backend()

    # Build query from user input
    query_parts = [user_input[:200]]
    if session_id and session_id != "default":
        query_parts.append(session_id)
    if stage:
        query_parts.append(stage)
    query = " ".join(query_parts)

    # Recall memories
    memories = _backend.recall(query=query, limit=5)

    # Also recall stage-specific memories
    if stage:
        from memory_nodes import _STAGE_TAG_MAP
        stage_tags = _STAGE_TAG_MAP.get(stage, [])
        stage_memories = _backend.recall(query=stage, limit=3, tags=stage_tags)
        seen_ids = {m.get("id") for m in memories}
        for m in stage_memories:
            if m.get("id") not in seen_ids:
                memories.append(m)
                seen_ids.add(m.get("id"))

    context = format_memory_context(memories)

    # Set env var for downstream consumption
    if context:
        os.environ["MEMANTO_LANGGRAPH_CONTEXT"] = context

    return context


def post_execution_hook(
    user_input: str,
    assistant_output: str,
    session_id: str = "default",
    stage: str | None = None,
    backend: MemoryBackend | None = None,
) -> list[str]:
    """Post-execution hook: extract signals and store to Memanto.

    This should be called AFTER the LLM produces output. It scans the
    combined input/output for engineering signals and stores them.

    Args:
        user_input: The original user input text.
        assistant_output: The LLM's output text.
        session_id: Session identifier for tagging memories.
        stage: Optional workflow stage tag.
        backend: MemoryBackend instance. Uses default if None.

    Returns:
        List of memory IDs that were stored.
    """
    _backend = backend or get_backend()
    full_text = f"{user_input}\n\n{assistant_output}"

    # Extract signals
    signals = extract_signals(full_text, stage)
    signals.extend(extract_from_file_references(full_text, stage))

    # Add session metadata
    for signal in signals:
        if session_id and session_id != "default":
            signal.setdefault("tags", [])
            if f"session:{session_id}" not in signal["tags"]:
                signal["tags"].append(f"session:{session_id}")

    # Store signals
    memory_ids = []
    for signal in signals:
        try:
            mid = _backend.store(signal)
            memory_ids.append(mid)
        except Exception:
            pass

    return memory_ids


def wrap_execution(
    user_input: str,
    assistant_output: str,
    session_id: str = "default",
    stage: str | None = None,
    backend: MemoryBackend | None = None,
) -> dict[str, Any]:
    """Convenience: run both pre and post hooks around an execution.

    This is useful for simple integrations where you want to both recall
    context before and store signals after a single LLM call.

    Args:
        user_input: The user's input text.
        assistant_output: The LLM's output text.
        session_id: Session identifier for cross-session recall.
        stage: Optional workflow stage tag.
        backend: MemoryBackend instance. Uses default if None.

    Returns:
        Dict with recalled_context, stored_memory_ids, and count.
    """
    context = pre_execution_hook(user_input, session_id, stage, backend)
    memory_ids = post_execution_hook(user_input, assistant_output, session_id, stage, backend)

    return {
        "recalled_context": context,
        "stored_memory_ids": memory_ids,
        "memories_stored_count": len(memory_ids),
    }
