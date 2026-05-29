"""Create LangChain Tool objects wrapping Memanto operations."""

from typing import Dict, List, Optional

from langchain_core.tools import Tool

from .client import MemantoClient


def create_memanto_tools(
    api_key: Optional[str] = None,
    agent_id: str = "langgraph-default",
    agent_pattern: str = "tool",
    agent_auto_create: bool = True,
    session_duration_hours: int = 6,
) -> Dict[str, Tool]:
    """Create a dictionary of LangChain Tool objects backed by Memanto.

    Returns a dict keyed by tool name so callers can pick the ones they want:

        tools = create_memanto_tools(agent_id="demo")
        graph = create_react_agent(model, [tools["memanto_recall"]])

    The returned dict always contains at least:
        - memanto_remember
        - memanto_recall
        - memanto_answer
        - memanto_recall_recent
        - memanto_recall_as_of
        - memanto_recall_changed_since
    """
    client = MemantoClient(
        api_key=api_key,
        agent_id=agent_id,
        agent_pattern=agent_pattern,
        agent_auto_create=agent_auto_create,
        session_duration_hours=session_duration_hours,
    )

    def _remember(memory: str, **kwargs) -> str:
        result = client.remember(memory=memory, **kwargs)
        return str(result)

    def _recall(query: str, **kwargs) -> str:
        result = client.recall(query=query, **kwargs)
        return str(result)

    def _answer(question: str) -> str:
        result = client.answer(question=question)
        return str(result)

    def _recall_recent(top_k: int = 10) -> str:
        result = client.recall_recent(top_k=top_k)
        return str(result)

    def _recall_as_of(iso_date: str, query: str = "", top_k: int = 10) -> str:
        result = client.recall_as_of(iso_date=iso_date, query=query, top_k=top_k)
        return str(result)

    def _recall_changed_since(iso_datetime: str, top_k: int = 10) -> str:
        result = client.recall_changed_since(iso_datetime=iso_datetime, top_k=top_k)
        return str(result)

    return {
        "memanto_remember": Tool(
            name="memanto_remember",
            description=(
                "Store a durable fact, preference, decision, goal, or instruction "
                "into long-term memory. Accepts 'memory' (string), optional "
                "'memory_type' (one of: fact, preference, goal, decision, "
                "artifact, learning, event, instruction, relationship, context, "
                "observation, commitment, error), optional 'confidence' (0.0-1.0), "
                "and 'provenance' (explicit_statement, inferred, corrected, "
                "validated, observed, imported). Returns confirmation."
            ),
            func=_remember,
        ),
        "memanto_recall": Tool(
            name="memanto_recall",
            description=(
                "Search long-term memory by semantic similarity. "
                "Accepts 'query' (string), optional 'memory_type' to filter, "
                "and optional 'top_k' (int, default 10). "
                "Returns a list of relevant memories with metadata."
            ),
            func=_recall,
        ),
        "memanto_answer": Tool(
            name="memanto_answer",
            description=(
                "Answer a question using only the agent's stored memories (RAG). "
                "Accepts 'question' (string). Returns a grounded string answer."
            ),
            func=_answer,
        ),
        "memanto_recall_recent": Tool(
            name="memanto_recall_recent",
            description=(
                "Fetch the most recent memories without a search query. "
                "Accepts optional 'top_k' (int, default 10). "
                "Useful for quickly seeing what was just discussed."
            ),
            func=_recall_recent,
        ),
        "memanto_recall_as_of": Tool(
            name="memanto_recall_as_of",
            description=(
                "Point-in-time recall: retrieve memories as they existed on "
                "a given date. Accepts 'iso_date' (string, e.g. '2025-11-01'), "
                "optional 'query' (string), optional 'top_k' (int, default 10)."
            ),
            func=_recall_as_of,
        ),
        "memanto_recall_changed_since": Tool(
            name="memanto_recall_changed_since",
            description=(
                "Differential recall: retrieve memories created or modified "
                "after a given ISO datetime. Accepts 'iso_datetime' (string), "
                "optional 'top_k' (int, default 10)."
            ),
            func=_recall_changed_since,
        ),
    }


__all__ = ["create_memanto_tools"]
