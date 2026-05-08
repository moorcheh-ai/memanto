"""
CrewAI + Memanto Integration Example

Demonstrates how to use Memanto as the persistent memory layer for a CrewAI Crew,
enabling agents to recall information from previous sessions and share context.

Use Case: A "Research Agent" stores findings in Memanto, and a "Writer Agent"
retrieves them later — even across different runs or sessions.

Requirements:
    pip install crewai memanto moorcheh-sdk

Environment:
    export MOORCHEH_API_KEY="your-moorcheh-api-key"
"""

import os
import uuid
from datetime import datetime
from typing import Any

from crewai.memory.long_term.long_term_memory import LongTermMemory
from crewai.memory.long_term.long_term_memory_item import LongTermMemoryItem
from crewai.memory.short_term.short_term_memory import ShortTermMemory
from crewai.memory.short_term.short_term_memory_item import ShortTermMemoryItem

from memanto.app.core import MemoryRecord, MemoryScope
from memanto.app.constants import MemoryType, ScopeType, SourceType
from memanto.app.clients.moorcheh import moorcheh_client


# ---------------------------------------------------------------------------
# Memanto-backed Long-Term Memory for CrewAI
# ---------------------------------------------------------------------------

class MemantoLongTermMemory(LongTermMemory):
    """
    CrewAI LongTermMemory backed by Memanto.

    Stores and retrieves memories using Memanto's Moorcheh-powered
    semantic search, enabling cross-session and cross-agent memory sharing.

    Usage:
        memory = MemantoLongTermMemory(scope_type="agent", scope_id="my-crew")
    """

    def __init__(self, scope_type: str = "agent", scope_id: str = "crewai-crew"):
        super().__init__(storage=self._build_storage(scope_type, scope_id))
        self.scope_type = scope_type
        self.scope_id = scope_id
        self._client = moorcheh_client.get_client()

    def _build_storage(self, scope_type: str, scope_id: str):
        """Build an in-memory storage that syncs with Memanto on search."""
        from crewai.memory.storage.storage import Storage

        class MemantoStorage(Storage):
            def __init__(inner_self, st, sid):
                inner_self.scope_type = st
                inner_self.scope_id = sid
                inner_self._client = moorcheh_client.get_client()

            def save(self, value: Any, metadata: dict[str, Any]) -> None:
                """Save a memory item to Memanto."""
                memory = MemoryRecord(
                    type=metadata.get("memory_type", "fact"),
                    title=metadata.get("score", "CrewAI Memory"),
                    content=str(value),
                    scope_type=inner_self.scope_type,
                    scope_id=inner_self.scope_id,
                    actor_id=metadata.get("agent", "crewai"),
                    source="agent",
                    tags=metadata.get("tags", []),
                )
                from memanto.app.services.memory_write_service import MemoryWriteService
                write_svc = MemoryWriteService(inner_self._client)
                write_svc.store_memory(memory)

            def search(
                inner_self, query: str, limit: int = 5, score_threshold: float = 0.6
            ) -> list[Any]:
                """Search memories in Memanto."""
                from memanto.app.services.memory_read_service import MemoryReadService
                read_svc = MemoryReadService(inner_self._client)
                results = read_svc.search_memories(
                    query=query,
                    scope_type=inner_self.scope_type,
                    scope_id=inner_self.scope_id,
                    min_similarity_score=score_threshold,
                    limit=limit,
                )
                return [
                    {"content": r.get("content", r.get("text", "")), "metadata": r}
                    for r in results.get("results", [])
                ]

            def reset(self) -> None:
                """Reset is a no-op for safety (Memanto persists data)."""
                pass

        return MemantoStorage(scope_type, scope_id)

    def search(self, query: str, score_threshold: float = 0.6) -> list[Any]:
        """Override search to use Memanto's semantic search."""
        return self.storage.search(query, limit=5, score_threshold=score_threshold)

    def save(self, item: LongTermMemoryItem) -> None:
        """Save a long-term memory item to Memanto."""
        self.storage.save(
            value=item.data if hasattr(item, "data") else str(item),
            metadata={
                "agent": getattr(item, "agent", "unknown"),
                "memory_type": "learning",
            },
        )


# ---------------------------------------------------------------------------
# Memanto-backed Short-Term Memory for CrewAI
# ---------------------------------------------------------------------------

class MemantoShortTermMemory(ShortTermMemory):
    """
    CrewAI ShortTermMemory backed by Memanto with TTL support.

    Short-term memories auto-expire after a configurable TTL (default: 1 hour),
    leveraging Memanto's built-in TTL enforcement.
    """

    def __init__(
        self,
        scope_type: str = "session",
        scope_id: str | None = None,
        ttl_seconds: int = 3600,
    ):
        scope_id = scope_id or f"session-{uuid.uuid4().hex[:8]}"
        super().__init__(storage=self._build_storage(scope_type, scope_id, ttl_seconds))
        self.scope_type = scope_type
        self.scope_id = scope_id
        self.ttl_seconds = ttl_seconds
        self._client = moorcheh_client.get_client()

    def _build_storage(self, scope_type, scope_id, ttl_seconds):
        from crewai.memory.storage.storage import Storage

        class MemantoSTMStorage(Storage):
            def __init__(inner_self, st, sid, ttl):
                inner_self.scope_type = st
                inner_self.scope_id = sid
                inner_self.ttl_seconds = ttl
                inner_self._client = moorcheh_client.get_client()

            def save(self, value: Any, metadata: dict[str, Any]) -> None:
                memory = MemoryRecord(
                    type="context",
                    title=metadata.get("score", "STM Entry"),
                    content=str(value),
                    scope_type=inner_self.scope_type,
                    scope_id=inner_self.scope_id,
                    actor_id=metadata.get("agent", "crewai"),
                    source="agent",
                )
                memory.set_ttl(inner_self.ttl_seconds)

                from memanto.app.services.memory_write_service import MemoryWriteService
                write_svc = MemoryWriteService(inner_self._client)
                write_svc.store_memory(memory)

            def search(
                inner_self, query: str, limit: int = 5, score_threshold: float = 0.6
            ) -> list[Any]:
                from memanto.app.services.memory_read_service import MemoryReadService
                read_svc = MemoryReadService(inner_self._client)
                results = read_svc.search_memories(
                    query=query,
                    scope_type=inner_self.scope_type,
                    scope_id=inner_self.scope_id,
                    min_similarity_score=score_threshold,
                    limit=limit,
                )
                return [
                    {"content": r.get("content", r.get("text", "")), "metadata": r}
                    for r in results.get("results", [])
                ]

            def reset(self) -> None:
                pass

        return MemantoSTMStorage(scope_type, scope_id, ttl_seconds)


# ---------------------------------------------------------------------------
# Direct Memanto Memory Helper (simpler API for custom agents)
# ---------------------------------------------------------------------------

class MemantoMemoryHelper:
    """
    Simplified helper for storing and retrieving memories with Memanto.

    This is useful when you want direct control over memory operations
    without going through CrewAI's memory abstraction layer.

    Example:
        helper = MemantoMemoryHelper(scope_id="research-crew")

        # Store a finding
        helper.remember(
            "Quantum computing uses qubits that can be in superposition",
            memory_type="fact",
            tags=["quantum", "computing"]
        )

        # Recall findings
        results = helper.recall("quantum computing")
    """

    def __init__(
        self,
        scope_type: str = "agent",
        scope_id: str = "crewai-crew",
    ):
        self.scope_type = scope_type
        self.scope_id = scope_id
        self._client = moorcheh_client.get_client()

    def remember(
        self,
        content: str,
        title: str = "",
        memory_type: str = "fact",
        tags: list[str] | None = None,
        confidence: float = 0.8,
        actor_id: str = "crewai-agent",
    ) -> dict[str, Any]:
        """
        Store a memory in Memanto.

        Args:
            content: The memory content to store
            title: Optional title for the memory
            memory_type: Type of memory (fact, preference, learning, etc.)
            tags: Optional list of tags
            confidence: Confidence score (0.0-1.0)
            actor_id: ID of the agent storing the memory

        Returns:
            Dict with storage result
        """
        from memanto.app.services.memory_write_service import MemoryWriteService
        write_svc = MemoryWriteService(self._client)

        memory = MemoryRecord(
            type=memory_type,
            title=title or content[:80],
            content=content,
            scope_type=self.scope_type,
            scope_id=self.scope_id,
            actor_id=actor_id,
            source="agent",
            confidence=confidence,
            tags=tags or [],
        )

        return write_svc.store_memory(memory)

    def recall(
        self,
        query: str,
        memory_types: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int = 5,
        min_confidence: float = 0.5,
    ) -> list[dict[str, Any]]:
        """
        Retrieve memories from Memanto using semantic search.

        Args:
            query: Natural language query to search for
            memory_types: Optional filter by memory types
            tags: Optional filter by tags
            limit: Maximum number of results
            min_confidence: Minimum confidence threshold

        Returns:
            List of matching memory dicts
        """
        from memanto.app.services.memory_read_service import MemoryReadService
        read_svc = MemoryReadService(self._client)

        results = read_svc.search_memories(
            query=query,
            scope_type=self.scope_type,
            scope_id=self.scope_id,
            memory_types=memory_types,
            tags=tags,
            min_confidence=min_confidence,
            limit=limit,
        )

        return results.get("results", [])

    def recall_current(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Retrieve only current (non-superseded, non-expired) memories.

        This is useful for getting the latest state without historical noise.
        """
        from memanto.app.services.memory_read_service import MemoryReadService
        read_svc = MemoryReadService(self._client)

        results = read_svc.search_current_only(
            query=query,
            scope_type=self.scope_type,
            scope_id=self.scope_id,
            limit=limit,
        )

        return results.get("results", [])

    def supersede(
        self,
        old_content: str,
        new_content: str,
        reason: str = "updated",
    ) -> dict[str, Any]:
        """
        Replace an old memory with a new one, handling contradictions.

        This implements Memanto's contradiction/supersession system:
        1. Search for the old memory
        2. Mark it as superseded
        3. Store the new memory with a reference to the old one

        Args:
            old_content: Content to search for (the memory to supersede)
            new_content: The updated content
            reason: Reason for the update

        Returns:
            Dict with the result of the supersession
        """
        from memanto.app.services.memory_write_service import MemoryWriteService
        from memanto.app.services.memory_read_service import MemoryReadService

        read_svc = MemoryReadService(self._client)
        write_svc = MemoryWriteService(self._client)

        # Find the old memory
        old_results = read_svc.search_memories(
            query=old_content,
            scope_type=self.scope_type,
            scope_id=self.scope_id,
            limit=1,
        )

        old_memories = old_results.get("results", [])
        if not old_memories:
            # No old memory found, just store the new one
            return self.remember(new_content, tags=["supersession"])

        old_memory = old_memories[0]
        old_id = old_memory.get("id")

        # Create new memory that supersedes the old one
        new_memory = MemoryRecord(
            type=old_memory.get("type", "fact"),
            title=old_memory.get("title", ""),
            content=new_content,
            scope_type=self.scope_type,
            scope_id=self.scope_id,
            actor_id="crewai-agent",
            source="agent",
            provenance="corrected",
            tags=old_memory.get("tags", []) + [f"supersedes:{old_id}"],
        )

        result = write_svc.store_memory(new_memory)

        # Mark old memory as superseded
        namespace = f"memanto_{self.scope_type}_{self.scope_id}"
        if old_id:
            write_svc.update_memory(
                memory_id=old_id,
                namespace=namespace,
                updates={"status": "superseded"},
            )

        return result


# ---------------------------------------------------------------------------
# CrewAI Crew with Memanto Memory
# ---------------------------------------------------------------------------

def create_research_writer_crew():
    """
    Create a CrewAI Crew with Memanto-backed memory.

    This crew has two agents:
    1. Research Agent: Researches topics and stores findings in Memanto
    2. Writer Agent: Retrieves findings from Memanto and writes a summary

    The key insight: The Writer Agent can recall the Research Agent's findings
    even in a completely different session, because Memanto persists the data.
    """
    try:
        from crewai import Agent, Crew, Task
    except ImportError:
        print("ERROR: crewai is not installed. Run: pip install crewai")
        return None

    # Shared Memanto memory scope for cross-agent communication
    scope_id = f"research-writer-{uuid.uuid4().hex[:8]}"
    helper = MemantoMemoryHelper(scope_id=scope_id)

    # Research Agent - stores findings in Memanto
    researcher = Agent(
        role="Senior Research Analyst",
        goal="Research topics thoroughly and store key findings for future reference",
        backstory="""You are an expert research analyst. You investigate topics deeply
        and always store your key findings in Memanto so that other agents can access
        them later. You focus on accuracy and cite your sources.""",
        verbose=True,
    )

    # Writer Agent - retrieves findings from Memanto
    writer = Agent(
        role="Technical Writer",
        goal="Retrieve research findings from memory and write clear, comprehensive summaries",
        backstory="""You are a skilled technical writer. You retrieve research findings
        from Memanto's memory layer and synthesize them into clear, well-structured
        summaries. You can access findings from previous research sessions.""",
        verbose=True,
    )

    # Create tasks
    research_task = Task(
        description="""Research the given topic and store your key findings in memory.
        Focus on the most important and actionable insights.
        Use the MemantoMemoryHelper to store your findings.""",
        agent=researcher,
        expected_output="A list of key research findings stored in Memanto memory",
    )

    writing_task = Task(
        description="""Retrieve research findings from Memanto memory and write
        a comprehensive summary. Use MemantoMemoryHelper to recall findings that
        were stored by the research agent.""",
        agent=writer,
        expected_output="A well-structured summary based on recalled research findings",
    )

    # Create crew with Memanto-backed memory
    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, writing_task],
        verbose=True,
        memory=True,
        long_term_memory=MemantoLongTermMemory(scope_id=scope_id),
        short_term_memory=MemantoShortTermMemory(scope_id=scope_id),
    )

    return crew, helper


# ---------------------------------------------------------------------------
# Demo: Cross-Session Memory Retrieval
# ---------------------------------------------------------------------------

def demo_cross_session_memory():
    """
    Demonstrates cross-session memory retrieval with Memanto.

    Session 1: A Research Agent stores findings about AI safety.
    Session 2: A Writer Agent retrieves those findings and writes a summary.

    This proves that Memanto enables "long-term amnesia" prevention
    across different CrewAI sessions.
    """
    print("=" * 60)
    print("CrewAI + Memanto: Cross-Session Memory Demo")
    print("=" * 60)

    # Ensure API key is set
    if not os.environ.get("MOORCHEH_API_KEY"):
        print("\nERROR: MOORCHEH_API_KEY environment variable not set.")
        print("Set it with: export MOORCHEH_API_KEY='your-key-here'")
        return

    scope_id = f"demo-ai-safety-{uuid.uuid4().hex[:8]}"
    helper = MemantoMemoryHelper(scope_id=scope_id)

    # ── Session 1: Research Agent stores findings ──
    print("\n📝 Session 1: Research Agent stores findings...")
    print("-" * 40)

    findings = [
        (
            "AI alignment research focuses on ensuring AI systems pursue intended goals. "
            "Key approaches include RLHF (Reinforcement Learning from Human Feedback), "
            "constitutional AI, and interpretability research.",
            "AI Alignment Overview",
        ),
        (
            "Scalable oversight is a key challenge: as AI systems become more capable, "
            "humans may struggle to evaluate their outputs. Debate and recursive reward "
            "modeling are proposed solutions.",
            "Scalable Oversight Challenge",
        ),
        (
            "The alignment tax refers to the cost of making AI systems safe compared to "
            "building capable but potentially unsafe systems. Reducing this tax is crucial "
            "for competitive safety.",
            "Alignment Tax Concept",
        ),
    ]

    for content, title in findings:
        result = helper.remember(
            content=content,
            title=title,
            memory_type="fact",
            tags=["ai-safety", "alignment"],
            actor_id="research-agent",
        )
        print(f"  ✅ Stored: {title}")
        print(f"     ID: {result.get('id', 'N/A')}")

    # ── Session 2: Writer Agent retrieves findings ──
    print("\n\n🔍 Session 2: Writer Agent retrieves findings...")
    print("-" * 40)

    results = helper.recall("AI alignment safety research", limit=5)

    print(f"  Found {len(results)} memories:\n")
    for i, memory in enumerate(results, 1):
        print(f"  {i}. {memory.get('title', 'Untitled')}")
        print(f"     Type: {memory.get('type', 'N/A')}")
        print(f"     Confidence: {memory.get('confidence', 'N/A')}")
        content = memory.get("content", memory.get("text", ""))
        print(f"     Content: {content[:120]}...")
        print()

    # ── Bonus: Handle contradictory memories ──
    print("\n🔄 Bonus: Handling contradictory memories...")
    print("-" * 40)

    # Store an initial belief
    helper.remember(
        content="GPT-4 is the most capable language model as of 2024.",
        title="Current best LLM",
        memory_type="fact",
        tags=["llm", "gpt-4"],
        actor_id="research-agent",
    )
    print("  ✅ Stored initial belief: GPT-4 is the most capable LLM")

    # Supersede with updated information
    helper.supersede(
        old_content="most capable language model",
        new_content="Claude 3.5 Sonnet and GPT-4o are the most capable language models as of 2025, "
        "with Claude excelling at coding and GPT-4o at multimodal tasks.",
        reason="Updated with newer information",
    )
    print("  ✅ Superseded with updated information: Claude 3.5 and GPT-4o")

    # Verify: only current (non-superseded) memories returned
    current = helper.recall_current("most capable language model", limit=3)
    print(f"\n  Current (non-superseded) results: {len(current)}")

    print("\n" + "=" * 60)
    print("Demo complete! ✨")
    print("=" * 60)


if __name__ == "__main__":
    demo_cross_session_memory()
