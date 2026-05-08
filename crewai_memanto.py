"""
Memanto ↔ CrewAI Integration
=============================
A CrewAI-compatible memory backend powered by Memanto's typed semantic
memory engine.

This module provides:
  - ``MemantoCrewMemory`` — a ``BaseMemory`` subclass that delegates
    reads/writes to a Memanto agent session.
  - ``MemantoCrewAdapter`` — a simpler wrapper that exposes
    ``remember`` / ``recall`` / ``answer`` directly for use inside
    CrewAI task callbacks or custom tools.
  - Configuration helpers and usage examples.

Requirements
------------
* ``memanto`` (>= 0.1.0)  — pip install memanto
* ``crewai`` (>= 0.100.0) — pip install crewai
* A valid Moorcheh API key (set ``MOORCHEH_API_KEY`` env var or pass
  directly).

Quick-start
-----------
.. code-block:: python

    import os
    from memanto.crewai_memanto import MemantoCrewMemory

    memory = MemantoCrewMemory(
        api_key=os.environ["MOORCHEH_API_KEY"],
        agent_id="my-crew-agent",
    )

    # Use inside a CrewAI agent:
    agent = Agent(
        role="Researcher",
        goal="Research topics and remember findings",
        backstory="I use Memanto for persistent memory.",
        memory=memory,
    )
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, ClassVar

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports — Memanto's SDK is heavy; we only load it when the class is
# first instantiated.
# ---------------------------------------------------------------------------

_MEMANTO_CLIENT_CACHE: dict[str, Any] = {}

_SUPPORTED_MEMORY_TYPES: tuple[str, ...] = (
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
)


def _get_memanto_client(api_key: str, use_sdk: bool = True) -> Any:
    """Return a cached Memanto client instance.

    Args:
        api_key: Moorcheh API key.
        use_sdk: If ``True`` use ``SdkClient`` (requires moorcheh_sdk),
            otherwise use ``DirectClient`` (pure urllib).

    Returns:
        A Memanto client instance.
    """
    cache_key = f"{use_sdk}:{api_key}"
    if cache_key in _MEMANTO_CLIENT_CACHE:
        return _MEMANTO_CLIENT_CACHE[cache_key]

    if use_sdk:
        from memanto.cli.client.sdk_client import SdkClient

        client: Any = SdkClient(api_key)
    else:
        from memanto.cli.client.direct_client import DirectClient

        client = DirectClient(api_key)

    _MEMANTO_CLIENT_CACHE[cache_key] = client
    return client


# ---------------------------------------------------------------------------
# MemantoCrewAdapter — lightweight wrapper
# ---------------------------------------------------------------------------


class MemantoCrewAdapter:
    """A simple Memanto wrapper for direct use inside CrewAI agents.

    Unlike ``MemantoCrewMemory`` this class does **not** subclass CrewAI's
    ``BaseMemory``.  Use it when you want fine-grained control inside task
    callbacks or custom CrewAI tools.

    Usage::

        adapter = MemantoCrewAdapter(api_key="...", agent_id="my-agent")
        adapter.create_agent_if_missing()

        adapter.remember("fact", "User prefers dark mode",
                         "The user explicitly requested a dark UI theme.")

        results = adapter.recall("What theme does the user want?")
        answer  = adapter.answer("Should we enable dark mode?")
    """

    def __init__(
        self,
        api_key: str | None = None,
        agent_id: str = "crewai-default-agent",
        pattern: str = "tool",
        auto_activate: bool = True,
        use_sdk: bool = True,
    ) -> None:
        """Initialise the adapter.

        Args:
            api_key: Moorcheh API key.  Falls back to ``MOORCHEH_API_KEY``
                env var.
            agent_id: Memanto agent name to use / create.
            pattern: Agent pattern (``"support"``, ``"project"``, or
                ``"tool"``).
            auto_activate: If ``True``, automatically create the agent and
                start a session on first memory operation.
            use_sdk: If ``True`` use the moorcheh_sdk-based client.

        Raises:
            ValueError: If no API key is provided or found in env.
        """
        self.api_key = api_key or os.environ.get("MOORCHEH_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Memanto requires a Moorcheh API key. "
                "Pass it as api_key= or set the MOORCHEH_API_KEY env var."
            )

        self.agent_id = agent_id
        self.pattern = pattern
        self.auto_activate = auto_activate
        self._client = _get_memanto_client(self.api_key, use_sdk=use_sdk)
        self._activated = False

    # -- Lifecycle ---------------------------------------------------------

    def create_agent_if_missing(self) -> dict[str, Any]:
        """Create the Memanto agent if it doesn't already exist.

        Returns:
            Agent info dict.
        """
        try:
            return self._client.get_agent(self.agent_id)
        except Exception:
            logger.info("Creating Memanto agent '%s'", self.agent_id)
            return self._client.create_agent(self.agent_id, pattern=self.pattern)

    def activate(self) -> dict[str, Any]:
        """Start (or renew) a Memanto session for the configured agent.

        Returns:
            Session info dict.
        """
        self.create_agent_if_missing()
        result = self._client.activate_agent(self.agent_id)
        self._activated = True
        return result

    def _ensure_ready(self) -> None:
        """Activate automatically if ``auto_activate`` is on."""
        if self.auto_activate and not self._activated:
            self.activate()

    # -- Memory operations -------------------------------------------------

    def remember(
        self,
        memory_type: str = "fact",
        title: str | None = None,
        content: str = "",
        confidence: float = 0.8,
        tags: list[str] | None = None,
        source: str = "agent",
        provenance: str | None = None,
    ) -> dict[str, Any]:
        """Store a memory.

        Args:
            memory_type: One of the 13 Memanto memory types (e.g.
                ``"fact"``, ``"preference"``, ``"decision"``).
            title: Short title (auto-generated from content if omitted).
            content: The memory text content.
            confidence: Confidence score 0.0–1.0.
            tags: Optional list of tags.
            source: Source identifier (default ``"agent"``).
            provenance: Provenance type (default ``"explicit_statement"``).

        Returns:
            Dict with ``memory_id``, ``status``, etc.
        """
        self._ensure_ready()

        if memory_type not in _SUPPORTED_MEMORY_TYPES:
            raise ValueError(
                f"Unknown memory type '{memory_type}'. "
                f"Supported: {', '.join(_SUPPORTED_MEMORY_TYPES)}"
            )

        resolved_title = title or (content[:47] + "..." if len(content) > 50 else content)

        return self._client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=resolved_title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source=source,
            provenance=provenance,
        )

    def recall(
        self,
        query: str,
        limit: int = 10,
        memory_types: list[str] | None = None,
        tags: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search memories by semantic similarity.

        Args:
            query: Natural-language query.
            limit: Maximum number of results (1–100).
            memory_types: Optional filter by memory types.
            tags: Optional filter by tags.
            min_confidence: Minimum confidence threshold.

        Returns:
            List of matching memory dicts.
        """
        self._ensure_ready()

        result = self._client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            memory_types=memory_types,
            tags=tags,
            min_confidence=min_confidence,
        )
        return result.get("memories", [])

    def recall_current(
        self,
        query: str,
        limit: int = 10,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Current-state recall (supersession-aware).

        Only returns memories that haven't been superseded or deleted.

        Args:
            query: Natural-language query.
            limit: Maximum results.
            memory_types: Optional type filter.

        Returns:
            List of current (non-superseded) memory dicts.
        """
        self._ensure_ready()

        result = self._client.recall_current(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            memory_types=memory_types,
        )
        return result.get("memories", [])

    def recall_as_of(
        self,
        query: str,
        as_of: str | datetime,
        limit: int = 10,
        memory_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Point-in-time recall: what was true at a given moment?

        Args:
            query: Natural-language query.
            as_of: ISO-8601 date/datetime string or ``datetime`` object.
            limit: Maximum results.
            memory_types: Optional type filter.

        Returns:
            List of memories that were active at the specified time.
        """
        self._ensure_ready()

        if isinstance(as_of, datetime):
            as_of = as_of.isoformat()

        result = self._client.recall_as_of(
            agent_id=self.agent_id,
            query=query,
            as_of=as_of,
            limit=limit,
            memory_types=memory_types,
        )
        return result.get("memories", [])

    def answer(
        self,
        question: str,
        limit: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate a grounded RAG answer from the agent's memories.

        Args:
            question: The question to answer.
            limit: Number of memory chunks to use as context.
            temperature: LLM temperature.

        Returns:
            The generated answer text.
        """
        self._ensure_ready()

        result = self._client.answer(
            agent_id=self.agent_id,
            question=question,
            limit=limit,
            temperature=temperature,
        )
        return result.get("answer", "No answer generated.")

    def list_memories(
        self,
        query: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Convenience: list recent memories with an optional broad query.

        Args:
            query: Optional search term (empty string lists broadly).
            limit: Max results.

        Returns:
            List of memory dicts.
        """
        return self.recall(query=query or ".*", limit=limit)

    def delete_agent(self) -> dict[str, Any]:
        """Permanently delete the agent and all its memories.

        .. warning::

            This operation is irreversible.
        """
        return self._client.delete_agent(self.agent_id)


# ---------------------------------------------------------------------------
# MemantoCrewMemory — CrewAI BaseMemory subclass
# ---------------------------------------------------------------------------


class MemantoCrewMemory:
    """CrewAI-compatible memory backed by Memanto.

    This class is designed to be passed as the ``memory`` argument to
    a CrewAI ``Agent``, giving the agent persistent, typed, semantic
    memory powered by Memanto.

    CrewAI's memory interface expects ``save()`` and ``search()`` (or
    ``remember()`` / ``recall()`` depending on the version).  This
    implementation supports both conventions.

    Example::

        from crewai import Agent, Task, Crew
        from memanto.crewai_memanto import MemantoCrewMemory

        memory = MemantoCrewMemory(
            api_key="moorch...key",
            agent_id="research-agent",
        )

        researcher = Agent(
            role="Senior Researcher",
            goal="Uncover groundbreaking insights",
            backstory="An expert analyst with perfect memory.",
            memory=memory,           # <-- Memanto-backed memory
            verbose=True,
        )

        task = Task(
            description="Research quantum computing trends",
            expected_output="A detailed report",
            agent=researcher,
        )

        crew = Crew(
            agents=[researcher],
            tasks=[task],
        )
        crew.kickoff()
    """

    #: Default memory type used when no explicit type is given.
    default_type: ClassVar[str] = "fact"

    def __init__(
        self,
        api_key: str | None = None,
        agent_id: str = "crewai-default-agent",
        pattern: str = "tool",
        auto_activate: bool = True,
        use_sdk: bool = True,
        default_memory_type: str = "fact",
    ) -> None:
        """Initialise the CrewAI-compatible Memanto memory.

        Args:
            api_key: Moorcheh API key.  Falls back to ``MOORCHEH_API_KEY``
                env var.
            agent_id: Memanto agent name.
            pattern: Agent pattern (``"support"``, ``"project"``,
                ``"tool"``).
            auto_activate: Create agent + session on first operation.
            use_sdk: Use moorcheh_sdk (True) or direct HTTP (False).
            default_memory_type: Default memory type for ``save()``.

        Raises:
            ValueError: If no API key is available.
        """
        self._adapter = MemantoCrewAdapter(
            api_key=api_key,
            agent_id=agent_id,
            pattern=pattern,
            auto_activate=auto_activate,
            use_sdk=use_sdk,
        )
        self.default_type = default_memory_type

    # -- CrewAI-compat: save / search  (CrewAI >= 0.100) -------------------

    def save(
        self,
        content: str,
        memory_type: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Save a memory (CrewAI ``save`` convention).

        Args:
            content: The memory content.
            memory_type: Memanto type (defaults to ``self.default_type``).
            title: Optional title.
            tags: Optional tags.
            **kwargs: Additional arguments forwarded to ``remember()``.

        Returns:
            Dict with ``memory_id``, ``status``, etc.
        """
        return self._adapter.remember(
            memory_type=memory_type or self.default_type,
            title=title,
            content=content,
            tags=tags,
            **kwargs,
        )

    def search(
        self,
        query: str,
        limit: int = 10,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search memories (CrewAI ``search`` convention).

        Args:
            query: Natural-language query.
            limit: Max results.
            **kwargs: Additional arguments forwarded to ``recall()``.

        Returns:
            List of matching memory dicts.
        """
        return self._adapter.recall(query=query, limit=limit, **kwargs)

    # -- CrewAI-compat: remember / recall (alternative convention) ---------

    def remember(
        self,
        content: str,
        memory_type: str | None = None,
        title: str | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Alias for ``save()``."""
        return self.save(
            content=content,
            memory_type=memory_type,
            title=title,
            tags=tags,
            **kwargs,
        )

    def recall(
        self,
        query: str,
        limit: int = 10,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Alias for ``search()``."""
        return self.search(query=query, limit=limit, **kwargs)

    # -- Direct access to adapter ------------------------------------------

    @property
    def adapter(self) -> MemantoCrewAdapter:
        """Access the underlying ``MemantoCrewAdapter`` for advanced use."""
        return self._adapter

    @property
    def agent_id(self) -> str:
        """The Memanto agent ID being used."""
        return self._adapter.agent_id

    # -- RAG convenience ---------------------------------------------------

    def answer(
        self,
        question: str,
        limit: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Generate a grounded RAG answer from stored memories.

        Args:
            question: The question.
            limit: Context size.
            temperature: LLM temperature.

        Returns:
            Generated answer.
        """
        return self._adapter.answer(
            question=question, limit=limit, temperature=temperature
        )


# ---------------------------------------------------------------------------
# Standalone usage example (run with ``python -m memanto.crewai_memanto``)
# ---------------------------------------------------------------------------

def _demo() -> None:
    """Demonstrate basic Memanto ↔ CrewAI integration.

    This is a *local* demo and will fail unless the Memanto package is
    installed **and** a valid ``MOORCHEH_API_KEY`` environment variable
    is set.

    Expected behaviour when dependencies are missing:
    - ``ImportError`` if ``memanto`` is not installed.
    - ``ValueError`` if ``MOORCHEH_API_KEY`` is not set.
    - API errors if the key is invalid or the network is unavailable.
    """
    import sys

    api_key = os.environ.get("MOORCHEH_API_KEY")
    if not api_key:
        print(
            "ERROR: MOORCHEH_API_KEY environment variable is not set.\n"
            "  Get a free key at https://console.moorcheh.ai/api-keys\n"
            "  Then run:  export MOORCHEH_API_KEY=moorch_...\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Adapter usage ---
    print("=== MemantoCrewAdapter Demo ===")
    adapter = MemantoCrewAdapter(
        api_key=api_key,
        agent_id="crewai-demo-agent",
        pattern="tool",
    )
    adapter.create_agent_if_missing()
    adapter.activate()

    print(f"Agent '{adapter.agent_id}' ready.")

    # Remember
    r1 = adapter.remember(
        memory_type="fact",
        title="CrewAI Integration",
        content="Memanto now has a CrewAI integration module.",
        tags=["crewai", "integration"],
    )
    print(f"Stored memory: {r1.get('memory_id', 'OK')}")

    r2 = adapter.remember(
        memory_type="preference",
        content="The user prefers concise, bullet-point responses.",
        tags=["style"],
    )
    print(f"Stored preference: {r2.get('memory_id', 'OK')}")

    # Recall
    results = adapter.recall("What does the user prefer?")
    print(f"\nRecall results ({len(results)}):")
    for m in results:
        t = m.get("type", "?")
        c = m.get("content", "")[:80]
        print(f"  [{t}] {c}")

    # Answer (RAG)
    ans = adapter.answer("What memory features are available?")
    print(f"\nRAG Answer: {ans[:200]}...")

    # --- CrewMemory usage ---
    print("\n=== MemantoCrewMemory Demo ===")
    memory = MemantoCrewMemory(
        api_key=api_key,
        agent_id="crewai-demo-agent",
    )

    # CrewAI save/search convention
    memory.save("The sky is blue on a clear day.", tags=["observation"])
    results2 = memory.search("sky color", limit=5)
    print(f"Search returned {len(results2)} results.")

    # RAG via memory
    ans2 = memory.answer("What do you know about the sky?")
    print(f"Answer: {ans2[:150]}...")

    print("\n✅ Demo completed successfully.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(name)s | %(message)s",
    )
    _demo()
