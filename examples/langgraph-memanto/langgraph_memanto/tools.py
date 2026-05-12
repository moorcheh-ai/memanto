"""Memanto tool functions for LangGraph agents.

These are plain Python functions that wrap SdkClient operations.
They can be used directly in LangGraph nodes or bound to an LLM via
`bind_tools` for tool-calling agents.
"""

from __future__ import annotations

from memanto.cli.client.sdk_client import SdkClient

VALID_MEMORY_TYPES = frozenset(
    {
        "fact",
        "preference",
        "goal",
        "decision",
        "artifact",
        "learning",
        "event",
        "instruction",
        "relationship",
        "context",
        "observation",
        "commitment",
        "error",
    }
)


def memanto_remember(
    client: SdkClient,
    agent_id: str,
    memory_type: str,
    title: str,
    content: str,
    confidence: float = 0.85,
    tags: list[str] | None = None,
) -> str:
    """Store a structured memory in Memanto.

    Args:
        client: Active SdkClient instance.
        agent_id: Namespace / agent identifier.
        memory_type: One of the VALID_MEMORY_TYPES.
        title: Short title (max 100 characters).
        content: Atomic memory content (max 500 characters).
        confidence: 0.0-1.0 confidence score.
        tags: Optional list of categorization tags.

    Returns:
        Confirmation string with memory id and type.
    """
    if memory_type not in VALID_MEMORY_TYPES:
        valid = ", ".join(sorted(VALID_MEMORY_TYPES))
        return f"Error: invalid memory_type '{memory_type}'. Must be one of: {valid}"

    result = client.remember(
        agent_id=agent_id,
        memory_type=memory_type,
        title=title,
        content=content,
        confidence=confidence,
        tags=tags or [],
        source="langgraph-agent",
        provenance="explicit_statement",
    )

    mem_id = result.get("memory_id", "unknown")
    return (
        f"Memory stored successfully.\n"
        f"  ID: {mem_id}\n"
        f"  Type: {memory_type}\n"
        f"  Title: {title}"
    )


def memanto_recall(
    client: SdkClient,
    agent_id: str,
    query: str,
    limit: int = 5,
    memory_types: list[str] | None = None,
) -> str:
    """Search Memanto memories with natural language.

    Args:
        client: Active SdkClient instance.
        agent_id: Namespace / agent identifier.
        query: Natural language search query.
        limit: Max memories to retrieve (1-20).
        memory_types: Optional filter by memory type(s).

    Returns:
        Formatted string with retrieved memories.
    """
    result = client.recall(
        agent_id=agent_id,
        query=query,
        limit=min(limit, 20),
        type=memory_types,
    )

    memories = result.get("memories", [])
    if not memories:
        return f"No memories found for query: '{query}'"

    lines = [f"Found {len(memories)} memories for '{query}':\n"]
    for i, mem in enumerate(memories, 1):
        title = mem.get("title", "Untitled")
        content = mem.get("content", "")
        mem_type = mem.get("type", "unknown")
        confidence = mem.get("confidence", "N/A")
        tags = mem.get("tags", [])
        tag_str = f" [tags: {', '.join(tags)}]" if tags else ""
        lines.append(
            f"  {i}. [{mem_type}] {title} (confidence: {confidence}){tag_str}\n"
            f"     {content}"
        )

    return "\n".join(lines)


def memanto_answer(
    client: SdkClient,
    agent_id: str,
    question: str,
) -> str:
    """Get an AI-generated answer grounded in stored memories (RAG).

    Args:
        client: Active SdkClient instance.
        agent_id: Namespace / agent identifier.
        question: Question to answer from memory.

    Returns:
        Answer string with optional source count.
    """
    result = client.answer(
        agent_id=agent_id,
        question=question,
    )

    answer = result.get("answer", "No answer could be generated.")
    sources = result.get("sources", [])
    output = f"Answer: {answer}"
    if sources:
        output += f"\n\nBased on {len(sources)} memory source(s)."
    return output


def create_memanto_tools(
    client: SdkClient,
    agent_id: str,
) -> dict[str, object]:
    """Return a dict of Memanto tool functions bound to *client* and *agent_id*.

    Because LangGraph tool-calling expects functions that receive only the
    arguments defined in the schema, this factory returns thin wrappers that
    close over *client* and *agent_id*.

    Returns:
        Dict with keys ``remember``, ``recall``, ``answer``.
    """

    def _remember(
        memory_type: str,
        title: str,
        content: str,
        confidence: float = 0.85,
        tags: list[str] | None = None,
    ) -> str:
        return memanto_remember(
            client=client,
            agent_id=agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
        )

    def _recall(
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> str:
        return memanto_recall(
            client=client,
            agent_id=agent_id,
            query=query,
            limit=limit,
            memory_types=memory_types,
        )

    def _answer(question: str) -> str:
        return memanto_answer(
            client=client,
            agent_id=agent_id,
            question=question,
        )

    return {
        "remember": _remember,
        "recall": _recall,
        "answer": _answer,
    }
