"""
Memanto Tools for Pydantic AI

Wraps Memanto's SdkClient as Pydantic AI tools (recall/remember/answer) and a
dynamic instruction that injects relevant memories into every run, so a
Pydantic AI agent gets persistent, cross-session memory. Mirrors the pattern
already used for CrewAI, LangGraph, and the other Python integrations.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Annotated, Any, get_args

from pydantic import Field
from pydantic_ai import ModelRetry, RunContext, Tool

from memanto.app.constants import MemoryType
from memanto.app.utils.errors import AgentAlreadyExistsError
from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

_VALID_MEMORY_TYPES = set(get_args(MemoryType))

# Mirrors InputLimits in memanto.app.utils.validation (the REST API's limits).
_MAX_QUERY_LENGTH = 1000
_MAX_CONTENT_LENGTH = 10000

DEFAULT_MEMORY_PREFIX = (
    "Relevant memories from long-term memory (most relevant first; they may be "
    "outdated, so prefer what the user says in this conversation):"
)

# memory_instructions() caches one recall per run; keep the most recent runs.
_INSTRUCTIONS_CACHE_SIZE = 256


class MemantoSetup:
    """
    Manages Memanto agent lifecycle for the Pydantic AI integration.

    Handles agent creation, session activation, and teardown so a Pydantic AI
    script can focus on the agent's actual task.

    A Memanto client holds one session for one agent at a time, so use one
    ``MemantoSetup`` per Memanto agent (for example, one per end user).
    """

    def __init__(self, api_key: str | None = None) -> None:
        api_key = api_key or os.environ.get("MOORCHEH_API_KEY")
        if not api_key:
            raise ValueError(
                "No Moorcheh API key: pass api_key=... or set the "
                "MOORCHEH_API_KEY environment variable."
            )
        self.client = SdkClient(api_key=api_key)

    def setup(
        self,
        agent_id: str,
        pattern: str = "tool",
        description: str | None = None,
        duration_hours: int = 6,
    ) -> SdkClient:
        """Create agent (if needed) and activate a session."""
        active = self.client.agent_id
        if active is not None and active != agent_id:
            raise ValueError(
                f"This MemantoSetup already has an active session for agent "
                f"'{active}'. A Memanto client serves one agent at a time: call "
                f"teardown('{active}') first, or use a separate MemantoSetup "
                f"for '{agent_id}'."
            )

        try:
            self.client.create_agent(
                agent_id=agent_id,
                pattern=pattern,
                description=description,
            )
            logger.info("Created Memanto agent '%s'", agent_id)
        except AgentAlreadyExistsError:
            logger.info("Memanto agent '%s' already exists, reusing", agent_id)
        except Exception as e:
            logger.error("Failed to create agent '%s': %s", agent_id, e)
            raise

        self.client.activate_agent(agent_id, duration_hours=duration_hours)
        logger.info("Activated session for agent '%s'", agent_id)
        return self.client

    def teardown(self, agent_id: str) -> None:
        """Deactivate the agent session."""
        try:
            self.client.deactivate_agent(agent_id)
            logger.info("Deactivated session for agent '%s'", agent_id)
        except Exception as e:
            logger.warning("Failed to deactivate agent '%s': %s", agent_id, e)


def _ensure_client_bound(client: SdkClient, agent_id: str) -> None:
    """Fail at construction time, not on the model's first tool call, when the
    client has no session for ``agent_id`` (a client serves one agent)."""
    active = client.agent_id
    if active == agent_id:
        return
    if active is None:
        raise ValueError(
            f"The Memanto client has no active session. Call "
            f"MemantoSetup.setup('{agent_id}') (or client.activate_agent("
            f"'{agent_id}')) before creating the tools."
        )
    raise ValueError(
        f"The Memanto client's active session is for agent '{active}', not "
        f"'{agent_id}'. A client serves one agent at a time: use a separate "
        f"MemantoSetup per agent."
    )


def _format_date(timestamp: Any) -> str:
    """'2026-10-02T15:04:05Z' -> '2026-10-02'; empty when missing."""
    return str(timestamp)[:10] if timestamp else ""


def create_memanto_tools(
    client: SdkClient,
    agent_id: str,
    *,
    include_remember: bool = True,
    include_recall: bool = True,
    include_answer: bool = True,
) -> list[Tool]:
    """
    Create Memanto tools for a Pydantic AI agent, bound to a specific client
    and agent. Pass the result straight into ``Agent(tools=...)``:

    ```python
    from pydantic_ai import Agent
    from memanto_pydantic_ai import MemantoSetup, create_memanto_tools

    client = MemantoSetup().setup("my-agent")

    agent = Agent(
        "openai:gpt-4o",
        tools=create_memanto_tools(client, agent_id="my-agent"),
    )
    ```

    The client and agent id are captured by the tool functions (matching the
    CrewAI/LangGraph integrations), so the model never has to pass either one
    itself — its only inputs are the memory content/query it's reasoning about.

    Use the ``include_*`` flags to expose a subset, e.g.
    ``include_remember=False`` for a read-only agent.

    Raises:
        ValueError: If ``client`` has no active session for ``agent_id``, or
            every tool is excluded.
    """
    if not (include_remember or include_recall or include_answer):
        raise ValueError("At least one Memanto tool must be included.")
    _ensure_client_bound(client, agent_id)

    def memanto_remember(
        memory_type: MemoryType,
        title: Annotated[str, Field(min_length=1, max_length=100)],
        content: Annotated[str, Field(min_length=1, max_length=_MAX_CONTENT_LENGTH)],
        confidence: Annotated[float, Field(ge=0.0, le=1.0)],
        tags: str = "",
    ) -> str:
        """Store a structured memory in Memanto for long-term persistence.

        Use this to save facts, observations, decisions, preferences, or any
        information that should be available in future sessions.

        Args:
            memory_type: The semantic type of memory to store. Must be exactly
                one of: fact (objective truths/data), preference (user
                likes/dislikes), goal (objectives/targets), decision (choices
                made/agreed upon), artifact (files/code/deliverables), learning
                (insights/lessons learned), event (occurrences/meetings),
                instruction (how-tos/directives), relationship (connections
                between entities), context (background info/state),
                observation (trends/patterns/notices), commitment (promises/
                next steps), or error (failures/mistakes).
            title: Short title for the memory (1-100 characters).
            content: The memory content to store (1-10000 characters). Be
                concise and atomic.
            confidence: Confidence score from 0.0 to 1.0. Use 1.0 for verified
                explicit facts, 0.7-0.85 for observations/estimates, and lower
                for unverified information.
            tags: Comma-separated tags for categorization (e.g. 'market,ai,trend').
                Use lowercase.
        """
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

        try:
            result = client.remember(
                agent_id=agent_id,
                memory_type=memory_type,
                title=title,
                content=content,
                confidence=confidence,
                tags=tag_list,
                source="pydantic-ai-agent",
                provenance="explicit_statement",
            )
        except ValueError as e:
            # Invalid input from the model: let it fix the call and retry
            # instead of failing the whole agent run.
            raise ModelRetry(str(e)) from e

        return (
            f"Memory stored successfully.\n"
            f"  ID: {result['memory_id']}\n"
            f"  Type: {memory_type}\n"
            f"  Title: {title}\n"
            f"  Confidence: {confidence}"
        )

    def memanto_recall(
        query: Annotated[str, Field(min_length=1, max_length=_MAX_QUERY_LENGTH)],
        limit: Annotated[int, Field(ge=1, le=100)] = 10,
        memory_types: str = "",
        min_similarity: Annotated[float | None, Field(ge=0.0, le=1.0)] = None,
    ) -> str:
        """Search Memanto's persistent memory database using natural language.

        Returns stored memories ranked by semantic relevance. Use this to
        retrieve facts, research findings, decisions, or any previously
        stored information. Memories marked (expired) are no longer current.

        Args:
            query: Natural language search query to find relevant memories.
            limit: Maximum number of memories to retrieve (1-100).
            memory_types: Comma-separated memory types to filter by (e.g.
                'fact,observation'). Each must be one of the memory types
                accepted by memanto_remember. Leave empty for all types.
            min_similarity: Minimum similarity score from 0.0 to 1.0 to filter
                low-relevance memories.
        """
        type_list = (
            [t.strip() for t in memory_types.split(",") if t.strip()]
            if memory_types
            else None
        )
        invalid_types = sorted(set(type_list or []) - _VALID_MEMORY_TYPES)
        if invalid_types:
            raise ModelRetry(
                f"Invalid memory_types: {', '.join(invalid_types)}. "
                f"Must be from: {', '.join(sorted(_VALID_MEMORY_TYPES))}"
            )

        try:
            result = client.recall(
                agent_id=agent_id,
                query=query,
                limit=limit,
                type=type_list,
                min_similarity=min_similarity,
            )
        except ValueError as e:
            raise ModelRetry(str(e)) from e

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
            created = _format_date(mem.get("created_at"))
            date_str = f" [saved: {created}]" if created else ""
            expired_str = " (expired)" if mem.get("status") == "expired" else ""

            lines.append(
                f"  {i}. [{mem_type}] {title}{expired_str} "
                f"(confidence: {confidence}){tag_str}{date_str}\n"
                f"     {content}\n"
            )

        return "\n".join(lines)

    def memanto_answer(question: Annotated[str, Field(min_length=1)]) -> str:
        """Get an AI-generated answer grounded in stored memories (RAG).

        Use this to synthesize insights from multiple stored memories into a
        coherent answer, instead of returning raw search results.

        Args:
            question: The question to answer from memory.
        """
        try:
            result = client.answer(agent_id=agent_id, question=question)
        except ValueError as e:
            raise ModelRetry(str(e)) from e

        answer = result.get("answer", "No answer could be generated.")
        sources = result.get("sources", [])

        output = f"Answer: {answer}"
        if sources:
            output += f"\n\nBased on {len(sources)} memory source(s)."

        return output

    tools: list[Tool] = []
    if include_remember:
        tools.append(Tool(memanto_remember, name="memanto_remember", takes_ctx=False))
    if include_recall:
        tools.append(Tool(memanto_recall, name="memanto_recall", takes_ctx=False))
    if include_answer:
        tools.append(Tool(memanto_answer, name="memanto_answer", takes_ctx=False))
    return tools


def _prompt_text(prompt: str | Sequence[Any] | None) -> str:
    """The text of the run's user prompt; non-text parts (images, files) are
    skipped."""
    if prompt is None:
        return ""
    if isinstance(prompt, str):
        return prompt
    return "\n".join(part for part in prompt if isinstance(part, str))


def memory_instructions(
    client: SdkClient,
    agent_id: str,
    *,
    limit: int = 5,
    min_similarity: float | None = None,
    prefix: str = DEFAULT_MEMORY_PREFIX,
) -> Callable[[RunContext[Any]], str]:
    """
    Create a dynamic instruction that recalls the memories most relevant to
    the user's prompt and adds them to the agent's instructions on every run,
    so the agent uses its memory even when the model doesn't call a tool:

    ```python
    agent = Agent(
        "openai:gpt-4o",
        tools=create_memanto_tools(client, agent_id="my-agent"),
        instructions=memory_instructions(client, agent_id="my-agent"),
    )
    ```

    The run's user prompt is the recall query, and only active (non-expired)
    memories are injected. Recall runs once per agent run: Pydantic AI
    re-evaluates instructions before every model request, so the result is
    cached for the rest of the run.

    A recall failure (network, auth, backend) is logged as a warning and the
    run continues without injected memories, so a memory outage never takes
    the agent down. The memory tools still raise those errors normally.

    Args:
        client: Memanto client with an active session for ``agent_id``.
        agent_id: Memanto agent whose memories to inject.
        limit: Maximum number of memories to inject (1-100).
        min_similarity: Minimum similarity score from 0.0 to 1.0; defaults
            to Memanto's configured recall threshold.
        prefix: Text placed before the injected memories.

    Raises:
        ValueError: If ``client`` has no active session for ``agent_id``, or
            ``limit`` or ``min_similarity`` is out of range.
    """
    if not 1 <= limit <= 100:
        raise ValueError(f"limit must be between 1 and 100, got {limit}")
    if min_similarity is not None and not 0.0 <= min_similarity <= 1.0:
        raise ValueError(
            f"min_similarity must be between 0.0 and 1.0, got {min_similarity}"
        )
    _ensure_client_bound(client, agent_id)

    cache: OrderedDict[str, str] = OrderedDict()
    lock = threading.Lock()

    def recall_for_prompt(prompt: str) -> str:
        query = prompt.strip()[:_MAX_QUERY_LENGTH]
        if not query:
            return ""
        try:
            result = client.recall(
                agent_id=agent_id,
                query=query,
                limit=limit,
                min_similarity=min_similarity,
                status="active",
            )
        except Exception:
            logger.warning(
                "Memanto recall for agent '%s' failed; running without "
                "injected memories",
                agent_id,
                exc_info=True,
            )
            return ""

        lines = []
        for mem in result.get("memories", []):
            created = _format_date(mem.get("created_at"))
            date_str = f" (saved {created})" if created else ""
            lines.append(
                f"- [{mem.get('type', 'unknown')}] {mem.get('title', 'Untitled')}"
                f"{date_str}: {mem.get('content', '')}"
            )
        if not lines:
            return ""
        return prefix + "\n" + "\n".join(lines)

    def memanto_memories(ctx: RunContext[Any]) -> str:
        run_id = ctx.run_id
        if run_id is not None:
            with lock:
                if run_id in cache:
                    return cache[run_id]

        text = recall_for_prompt(_prompt_text(ctx.prompt))

        if run_id is not None:
            with lock:
                cache[run_id] = text
                while len(cache) > _INSTRUCTIONS_CACHE_SIZE:
                    cache.popitem(last=False)
        return text

    return memanto_memories
