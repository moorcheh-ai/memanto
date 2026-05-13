"""State definitions for the LangGraph + Memanto agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any


def merge_dicts(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Merge two dictionaries, b wins on conflict."""
    return {**a, **b}


@dataclass
class AgentState:
    """State for the Memanto-powered LangGraph agent.

    Extends LangGraph's built-in state with Memanto-specific fields
    for seamless long-term memory integration.
    """

    # The conversation history (list of messages)
    messages: list[dict[str, str]] = field(default_factory=list)

    # Which "session" this run belongs to (for cross-session demos)
    session_id: str = "default"

    # The Memanto agent ID (persistent across sessions)
    memanto_agent_id: str = ""

    # The current user input
    user_input: str = ""

    # Agent's internal thoughts / reasoning
    thoughts: str = ""

    # Memories retrieved from Memanto (for display / debugging)
    retrieved_memories: list[dict[str, Any]] = field(default_factory=list)

    # Memory operations performed this turn
    memory_ops: list[dict[str, str]] = field(default_factory=list)

    # Final response to the user
    response: str = ""

    # Accumulator for metadata (merged each step)
    metadata: Annotated[dict[str, Any], merge_dicts] = field(default_factory=dict)
