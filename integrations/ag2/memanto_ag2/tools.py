"""AG2-compatible Memanto tool functions (module-level callables for JSON schema generation)."""

import functools
import re
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Annotated, Any

from memanto.app.utils.errors import SessionError
from memanto.cli.client.sdk_client import SdkClient
from memanto_ag2.lifecycle import AgentSessionBinder

_MEMORY_TYPE_PATTERN = re.compile(
    r"^(fact|preference|goal|decision|artifact|learning|event|instruction|"
    r"relationship|context|observation|commitment|error)$"
)

_MEMORY_TYPE_DESCRIPTION = (
    "Semantic memory type: fact, preference, goal, decision, artifact, learning, "
    "event, instruction, relationship, context, observation, commitment, or error."
)


def _tool_field(description: str) -> Any:
    """AG2 0.14+ tool schema metadata (``autogen.tools.dependency_injection.Field``)."""
    try:
        from autogen.tools.dependency_injection import Field as ToolField

        return ToolField(description)
    except ImportError:
        return description


@dataclass
class _ToolRuntime:
    session: AgentSessionBinder
    client: SdkClient
    agent_id: str
    source: str
    recall_limit: int


_runtime: ContextVar[_ToolRuntime | None] = ContextVar(
    "memanto_ag2_runtime", default=None
)


def _with_session(operation: Callable[[], Any]) -> Any:
    runtime = _runtime.get()
    if runtime is None:
        raise RuntimeError("Memanto AG2 tools are not bound to a client/agent_id")
    try:
        return runtime.session.call(operation)
    except SessionError:
        return runtime.session.call(operation)


def memanto_remember(
    memory_type: Annotated[str, _tool_field(_MEMORY_TYPE_DESCRIPTION)],
    title: Annotated[str, _tool_field("Short title (1-100 chars).")],
    content: Annotated[str, _tool_field("Memory body (1-10000 chars). Keep atomic.")],
    confidence: Annotated[float, _tool_field("Certainty from 0.0 to 1.0.")],
    tags: Annotated[
        str, _tool_field("Comma-separated tags, e.g. 'ag2,preference'.")
    ] = "",
) -> str:
    """Store a structured memory in Memanto for long-term cross-session persistence."""
    runtime = _runtime.get()
    if runtime is None:
        raise RuntimeError("Memanto AG2 tools are not bound to a client/agent_id")

    if not _MEMORY_TYPE_PATTERN.match(memory_type):
        return f"Invalid memory_type '{memory_type}'. Use one of the documented semantic types."

    title = title.strip()
    content = content.strip()
    if not title or len(title) > 100:
        return "title must be 1-100 characters."
    if not content or len(content) > 10_000:
        return "content must be 1-10000 characters."

    if not 0.0 <= confidence <= 1.0:
        return "confidence must be between 0.0 and 1.0."

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    result = _with_session(
        lambda: runtime.client.remember(
            agent_id=runtime.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tag_list,
            source=runtime.source,
            provenance="explicit_statement",
        )
    )
    return (
        f"Memory stored successfully.\n"
        f"  ID: {result['memory_id']}\n"
        f"  Type: {memory_type}\n"
        f"  Title: {title}"
    )


def memanto_recall(
    query: Annotated[str, _tool_field("Natural language search over stored memories.")],
    limit: Annotated[
        int | None,
        _tool_field("Max memories to return (1-100). Omit for configured default."),
    ] = None,
    memory_types: Annotated[
        str,
        _tool_field(
            "Optional comma-separated types to filter (e.g. 'fact,preference'). Empty = all."
        ),
    ] = "",
) -> str:
    """Search Memanto for relevant memories ranked by semantic similarity."""
    runtime = _runtime.get()
    if runtime is None:
        raise RuntimeError("Memanto AG2 tools are not bound to a client/agent_id")

    if limit is None:
        limit_val = max(1, min(100, runtime.recall_limit))
    else:
        limit_val = max(1, min(100, limit))

    type_list = (
        [t.strip() for t in memory_types.split(",") if t.strip()]
        if memory_types
        else None
    )
    result = _with_session(
        lambda: runtime.client.recall(
            agent_id=runtime.agent_id,
            query=query,
            limit=limit_val,
            type=type_list,
        )
    )
    memories = result.get("memories", [])
    if not memories:
        return f"No memories found for query: '{query}'"

    lines = [f"Found {len(memories)} memories for '{query}':\n"]
    for i, mem in enumerate(memories, 1):
        m_title = mem.get("title", "Untitled")
        m_content = mem.get("content", "")
        m_type = mem.get("type", "unknown")
        m_conf = mem.get("confidence", "N/A")
        m_tags = mem.get("tags", [])
        tag_str = f" [tags: {', '.join(m_tags)}]" if m_tags else ""
        lines.append(
            f"  {i}. [{m_type}] {m_title} (confidence: {m_conf}){tag_str}\n"
            f"     {m_content}\n"
        )
    return "\n".join(lines)


def memanto_answer(
    question: Annotated[
        str, _tool_field("Question to answer using RAG over stored memories.")
    ],
) -> str:
    """Synthesize an answer from Memanto memories (similar to reflect-style tools)."""
    runtime = _runtime.get()
    if runtime is None:
        raise RuntimeError("Memanto AG2 tools are not bound to a client/agent_id")

    result = _with_session(
        lambda: runtime.client.answer(agent_id=runtime.agent_id, question=question)
    )
    answer = result.get("answer", "No answer could be generated.")
    sources = result.get("sources", [])
    output = f"Answer: {answer}"
    if sources:
        output += f"\n\nBased on {len(sources)} memory source(s)."
    return output


def _with_runtime(runtime: _ToolRuntime, fn: Callable[..., str]) -> Callable[..., str]:
    @functools.wraps(fn)
    def bound(*args: Any, **kwargs: Any) -> str:
        token = _runtime.set(runtime)
        try:
            return fn(*args, **kwargs)
        finally:
            _runtime.reset(token)

    return bound


def create_memanto_tools(
    client: SdkClient,
    agent_id: str,
    *,
    source: str = "ag2-agent",
    recall_limit: int = 10,
    include_remember: bool = True,
    include_recall: bool = True,
    include_answer: bool = True,
) -> list[Callable[..., str]]:
    """
    Return Memanto tool callables for AG2 registration.

    Each returned callable binds its own runtime at invocation time.
    """
    runtime = _ToolRuntime(
        session=AgentSessionBinder(client, agent_id),
        client=client,
        agent_id=agent_id,
        source=source,
        recall_limit=recall_limit,
    )

    selected: list[Callable[..., str]] = []
    if include_remember:
        selected.append(_with_runtime(runtime, memanto_remember))
    if include_recall:
        selected.append(_with_runtime(runtime, memanto_recall))
    if include_answer:
        selected.append(_with_runtime(runtime, memanto_answer))
    return selected
