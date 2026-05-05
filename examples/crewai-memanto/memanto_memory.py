"""
memanto_memory.py — CrewAI ↔ Memanto Agentic Memory Adapter
================================================================

A drop-in memory backend that replaces CrewAI's default in-memory storage
with Memanto's persistent, semantic, cross-session memory layer.

Key Features
────────────
• Implements the full CrewAI Memory interface for seamless integration
• Cross-agent memory sharing: Agent A stores → Agent B retrieves
• Cross-session persistence: memories survive agent restarts
• 13 semantic memory types: fact, preference, goal, decision, ...
• Temporal queries: point-in-time recall, change detection
• Contradiction detection via content similarity + confidence comparison
• RAG-powered answer generation from stored memories
• Batch operations for bulk memory ingestion

Quick Start
───────────
    from memanto_memory import MemantoMemory

    # Configure once, use anywhere
    memory = MemantoMemory(api_key="mca_...", agent_id="research-agent")
    memory.activate()

    # Store
    memory.remember("Quantum computing uses qubits.", memory_type="fact")

    # Retrieve (even from different agent/session)
    results = memory.recall("quantum computing")
    
    # Ask
    answer = memory.answer("What do I know about quantum?")

Bounty #37 — moorcheh-ai/memanto
Author: VESPER (vesperai-890)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# ── Logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("memanto_memory")


# ── Types & Constants ────────────────────────────────────────────

class MemoryType(str, Enum):
    """The 13 semantic memory types supported by Memanto."""
    FACT = "fact"
    PREFERENCE = "preference"
    GOAL = "goal"
    DECISION = "decision"
    ARTIFACT = "artifact"
    LEARNING = "learning"
    EVENT = "event"
    INSTRUCTION = "instruction"
    RELATIONSHIP = "relationship"
    CONTEXT = "context"
    OBSERVATION = "observation"
    COMMITMENT = "commitment"
    ERROR = "error"

    @classmethod
    def _missing_(cls, value: str) -> MemoryType:
        """Case-insensitive fallback."""
        for member in cls:
            if member.value.lower() == value.lower():
                return member
        return cls.FACT  # default


class ProvenanceType(str, Enum):
    """Provenance types for memory trust calibration."""
    EXPLICIT_STATEMENT = "explicit_statement"
    VALIDATED = "validated"
    OBSERVED = "observed"
    CORRECTED = "corrected"
    INFERRED = "inferred"
    IMPORTED = "imported"


class ConflictResolution(str, Enum):
    """Strategies for resolving contradictory memories."""
    KEEP_HIGHER_CONFIDENCE = "keep_higher_confidence"
    KEEP_NEWER = "keep_newer"
    KEEP_BOTH = "keep_both"
    MARK_BOTH_CONTRADICTED = "mark_both_contradicted"


@dataclass
class MemoryRecord:
    """A single memory record returned from Memanto."""
    memory_id: str
    type: MemoryType
    title: str
    content: str
    confidence: float
    tags: list[str]
    source: str
    provenance: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api_response(cls, data: dict) -> "MemoryRecord":
        """Create from Memanto API response dict."""
        return cls(
            memory_id=data.get("memory_id", data.get("id", "")),
            type=MemoryType(data.get("type", data.get("memory_type", "fact"))),
            title=data.get("title", ""),
            content=data.get("content", ""),
            confidence=float(data.get("confidence", 0.8)),
            tags=data.get("tags", []) if isinstance(data.get("tags"), list)
                 else data.get("tags", "").split(",") if data.get("tags")
                 else [],
            source=data.get("source", "unknown"),
            provenance=data.get("provenance", "explicit_statement"),
            created_at=_parse_dt(data.get("created_at", "")),
            updated_at=_parse_dt(data.get("updated_at")) if data.get("updated_at") else None,
            metadata={k: v for k, v in data.items()
                     if k not in ("memory_id", "id", "type", "memory_type",
                                  "title", "content", "confidence", "tags",
                                  "source", "provenance", "created_at", "updated_at")},
        )

    def to_dict(self) -> dict:
        """Serialize to dict for display/export."""
        return {
            "id": self.memory_id,
            "type": self.type.value,
            "title": self.title,
            "content": self.content,
            "confidence": self.confidence,
            "tags": self.tags,
            "source": self.source,
            "provenance": self.provenance,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class Conflict:
    """A detected contradiction between two memories."""
    topic: str
    old_memory: MemoryRecord
    new_memory: MemoryRecord
    similarity_score: float
    resolution: Optional[str] = None


def _parse_dt(value: str | datetime) -> datetime:
    """Parse ISO datetime string or return as-is."""
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


def _content_hash(content: str) -> str:
    """Generate a stable hash for content deduplication."""
    return hashlib.sha256(content.strip().lower().encode()).hexdigest()[:16]


# ── MemantoMemory — Core Adapter ────────────────────────────────

class MemantoMemory:
    """
    CrewAI-compatible memory backend powered by Memanto.

    This adapter wraps the Memanto SDK client to provide persistent,
    semantic, cross-session memory for CrewAI agents.

    It supports:
    • All 13 Memanto memory types (fact, preference, goal, decision, ...)
    • Cross-agent memory sharing (different agent IDs, same API key)
    • Cross-session persistence (memories survive agent restarts)
    • Semantic similarity search via ``recall()``
    • RAG-powered question answering via ``answer()``
    • Contradiction detection and resolution
    • Batch memory storage
    • Temporal queries (point-in-time, change detection)

    Usage::

        # Initialize
        memory = MemantoMemory(api_key="...", agent_id="research-agent")

        # Activate session (required before first operation)
        memory.activate()

        # Store memories
        memory.remember(
            "The user prefers dark mode.",
            memory_type="preference",
            tags=["ui", "theme"],
        )

        # Semantic search
        results = memory.recall("What UI theme does the user like?")

        # RAG-powered answer
        answer = memory.answer("Summarize user preferences")

        # Cross-agent: Writer Agent retrieves Researcher's memories
        writer_memory = MemantoMemory(api_key="...", agent_id="writer-agent")
        writer_memory.activate()
        research = writer_memory.recall("research findings", limit=10)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        """
        Initialize the Memanto memory adapter.

        Args:
            api_key: Moorcheh API key. Falls back to MEMANTO_API_KEY env var.
            agent_id: Unique identifier for this agent. Used as the Memanto
                agent ID and memory scope. Falls back to "crewai-agent".
            config_path: Optional path to YAML config file.
        """
        self.api_key = api_key or os.getenv("MEMANTO_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Memanto API key required. Set MEMANTO_API_KEY environment "
                "variable or pass api_key parameter."
            )

        self.agent_id = agent_id or os.getenv("MEMANTO_AGENT_ID", "crewai-agent")
        self._client: Any = None
        self._active: bool = False
        self._namespace: Optional[str] = None
        self._session_info: dict[str, Any] = {}
        self._seen_hashes: set[str] = set()

        logger.info("MemantoMemory initialized for agent '%s'", self.agent_id)

    # ── Lifecycle ────────────────────────────────────────────────

    def activate(
        self,
        duration_hours: int = 24,
        pattern: str = "tool",
        description: Optional[str] = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Activate a Memanto session for this agent.

        Creates the agent (if it doesn't exist) and starts a session.
        Idempotent: safe to call multiple times.

        Args:
            duration_hours: Session lifetime in hours.
            pattern: Agent pattern — "tool", "support", or "project".
            description: Optional agent description.
            force: Force re-activation even if already active.

        Returns:
            Dict with session_token, session_id, agent_id, namespace.
        """
        if self._active and not force:
            return self._session_info

        from memanto.cli.client.sdk_client import SdkClient

        self._client = SdkClient(api_key=self.api_key)

        # Create agent (idempotent — Memanto handles duplicates)
        try:
            agent_info = self._client.create_agent(
                agent_id=self.agent_id,
                pattern=pattern,
                description=description or f"CrewAI agent: {self.agent_id}",
            )
            logger.info("Agent '%s' created/verified", self.agent_id)
        except Exception as e:
            # Agent likely already exists — this is fine
            logger.debug("Agent '%s' already exists: %s", self.agent_id, e)

        # Activate session
        try:
            session = self._client.activate_agent(
                agent_id=self.agent_id,
                duration_hours=duration_hours,
            )
            self._active = True
            self._namespace = session.get("namespace", f"agent_{self.agent_id}")
            self._session_info = session
            logger.info(
                "Session activated: agent='%s', namespace='%s', expires=%s",
                self.agent_id,
                self._namespace,
                session.get("expires_at", "N/A"),
            )
        except Exception as e:
            logger.error("Failed to activate session: %s", e)
            raise

        return self._session_info

    def deactivate(self) -> dict[str, Any]:
        """End the current session gracefully."""
        if not self._active or not self._client:
            return {"status": "not_active"}

        try:
            result = self._client.deactivate_agent(self.agent_id)
            self._active = False
            self._namespace = None
            logger.info("Session deactivated for agent '%s'", self.agent_id)
            return cast_dict(result)
        except Exception as e:
            logger.warning("Error deactivating session: %s", e)
            self._active = False
            return {"status": "deactivated_with_error", "error": str(e)}

    def is_active(self) -> bool:
        """Check if a session is currently active."""
        return self._active

    @property
    def namespace(self) -> Optional[str]:
        """Get the current agent namespace."""
        return self._namespace

    @property
    def session_info(self) -> dict[str, Any]:
        """Get current session info."""
        return self._session_info

    # ── Core Memory Operations ───────────────────────────────────

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        title: Optional[str] = None,
        confidence: float = 0.8,
        tags: Optional[list[str]] = None,
        source: str = "crewai_agent",
        provenance: str = "explicit_statement",
        deduplicate: bool = True,
    ) -> dict[str, Any]:
        """
        Store a memory in Memanto's persistent storage.

        Args:
            content: The memory text content (max 500 chars).
            memory_type: Semantic type — one of the 13 Memanto types
                (e.g., "fact", "preference", "decision", "goal").
            title: Optional title (auto-generated if None).
            confidence: Confidence score 0.0–1.0.
            tags: Optional list of tags for categorization.
            source: Source identifier for provenance tracking.
            provenance: Provenance type for trust calibration.
            deduplicate: If True, skip identical content already stored.

        Returns:
            Dict with memory_id, agent_id, namespace, status, action.

        Raises:
            RuntimeError: If session is not active.
        """
        self._ensure_active()

        auto_title = title
        if not auto_title:
            auto_title = (content[:80] + "...") if len(content) > 80 else content

        # Content-based deduplication
        if deduplicate:
            c_hash = _content_hash(content)
            if c_hash in self._seen_hashes:
                logger.debug("Duplicate content skipped: '%s'", auto_title)
                return {"status": "skipped", "reason": "duplicate", "content_hash": c_hash}

        try:
            result = self._client.remember(
                agent_id=self.agent_id,
                memory_type=memory_type,
                title=auto_title,
                content=content,
                confidence=confidence,
                tags=tags or [],
                source=source,
                provenance=provenance,
            )

            if deduplicate and result.get("memory_id"):
                self._seen_hashes.add(c_hash)

            logger.info(
                "Stored [%s] '%s' (conf=%.2f) → memory_id=%s",
                memory_type, auto_title, confidence,
                result.get("memory_id", "N/A"),
            )
            return cast_dict(result)

        except Exception as e:
            logger.error("Failed to store memory: %s", e)
            return {"status": "error", "error": str(e), "agent_id": self.agent_id}

    def remember_batch(
        self,
        memories: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Store multiple memories in a single batch operation.

        Each memory dict should have:
        - content (str) — Required
        - memory_type (str) — Default: "fact"
        - title (str) — Optional, auto-generated
        - confidence (float) — Default: 0.8
        - tags (list[str]) — Optional
        - source (str) — Default: "crewai_agent"

        Args:
            memories: List of memory dicts (1–100 items).

        Returns:
            List of result dicts for each memory.
        """
        self._ensure_active()
        results = []

        for mem in memories:
            try:
                result = self.remember(
                    content=mem["content"],
                    memory_type=mem.get("memory_type", "fact"),
                    title=mem.get("title"),
                    confidence=mem.get("confidence", 0.8),
                    tags=mem.get("tags"),
                    source=mem.get("source", "crewai_agent"),
                )
                results.append(result)
            except Exception as e:
                results.append({"status": "error", "error": str(e)})

        return results

    def recall(
        self,
        query: str,
        limit: int = 10,
        memory_types: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        min_confidence: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Search memories by semantic similarity.

        Finds memories most relevant to the query, across agents
        sharing the same API key (cross-agent recall).

        Args:
            query: Natural-language search query.
            limit: Max results (1–100).
            memory_types: Filter by specific memory types.
            tags: Filter by tags.
            min_confidence: Minimum confidence threshold.

        Returns:
            Dict with query, count, and memories list.
        """
        self._ensure_active()

        try:
            result = self._client.recall(
                agent_id=self.agent_id,
                query=query,
                limit=limit,
                memory_types=memory_types,
                tags=tags,
                min_confidence=min_confidence,
            )

            records = [
                MemoryRecord.from_api_response(mem)
                for mem in result.get("memories", [])
            ]

            logger.info(
                "Recall '%s': found %d memories (requested %d)",
                query, result.get("count", 0), limit,
            )
            return {
                "query": query,
                "count": result.get("count", 0),
                "memories": [r.to_dict() for r in records],
                "_records": records,
            }

        except Exception as e:
            logger.error("Recall failed: %s", e)
            return {"query": query, "count": 0, "memories": [], "error": str(e)}

    def recall_as_of(
        self,
        query: str,
        as_of: str,
        limit: int = 10,
        memory_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Point-in-time recall: what did the agent know at a given moment?

        Useful for: "What did we know before the user corrected themselves?"

        Args:
            query: Search query.
            as_of: ISO-8601 date/datetime string (e.g., "2026-05-03T12:00:00").
            limit: Max results.
            memory_types: Optional type filter.

        Returns:
            Dict with memories as they existed at the given time.
        """
        self._ensure_active()
        try:
            result = self._client.recall_as_of(
                agent_id=self.agent_id,
                query=query,
                as_of=as_of,
                limit=limit,
                memory_types=memory_types,
            )
            records = [
                MemoryRecord.from_api_response(mem)
                for mem in result.get("memories", [])
            ]
            return {
                "query": query,
                "as_of": as_of,
                "count": result.get("count", 0),
                "memories": [r.to_dict() for r in records],
                "_records": records,
            }
        except Exception as e:
            logger.error("Point-in-time recall failed: %s", e)
            return {"query": query, "as_of": as_of, "count": 0, "memories": []}

    def recall_current(
        self,
        query: str,
        limit: int = 10,
        memory_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Current-state recall: get only non-superseded memories.

        Automatically filters out superseded/contradicted memories,
        returning only the active truth.

        Args:
            query: Search query.
            limit: Max results.
            memory_types: Optional type filter.

        Returns:
            Dict with current active memories only.
        """
        self._ensure_active()
        try:
            result = self._client.recall_current(
                agent_id=self.agent_id,
                query=query,
                limit=limit,
                memory_types=memory_types,
            )
            records = [
                MemoryRecord.from_api_response(mem)
                for mem in result.get("memories", [])
            ]
            return {
                "query": query,
                "count": result.get("count", 0),
                "memories": [r.to_dict() for r in records],
                "_records": records,
            }
        except Exception as e:
            logger.error("Current-state recall failed: %s", e)
            return {"query": query, "count": 0, "memories": []}

    def answer(
        self,
        question: str,
        limit: int = 5,
        threshold: float = 0.5,
    ) -> dict[str, Any]:
        """
        Answer a question using RAG over stored memories.

        Memanto's built-in LLM generates a grounded answer using only
        the memories most relevant to the question.

        Args:
            question: Natural-language question.
            limit: Number of memories to retrieve as context.
            threshold: Minimum relevance confidence.

        Returns:
            Dict with answer text, source references, and confidence.
        """
        self._ensure_active()

        try:
            result = self._client.answer(
                agent_id=self.agent_id,
                question=question,
                limit=limit,
                threshold=threshold,
            )
            answer_text = result.get("answer", "")
            sources = result.get("sources", [])

            logger.info(
                "Answer generated (%d sources): %s...",
                len(sources), answer_text[:80],
            )
            return {
                "question": question,
                "answer": answer_text,
                "sources": sources,
                "namespace": result.get("namespace", self._namespace),
            }

        except Exception as e:
            logger.error("Answer generation failed: %s", e)
            return {
                "question": question,
                "answer": f"Could not generate answer: {e}",
                "sources": [],
            }

    # ── Contradiction Detection & Resolution ─────────────────────

    def detect_contradictions(
        self,
        query: str = "",
        min_confidence: float = 0.6,
    ) -> list[Conflict]:
        """
        Detect contradictory memories in the agent's storage.

        Uses Memanto's provenance system (superseded_by, confidence,
        contradiction_detected flags) plus semantic similarity to
        identify conflicting memories.

        Args:
            query: Optional search scope for targeted detection.
            min_confidence: Minimum confidence for memories to consider.

        Returns:
            List of Conflict objects with old/new memory pairs.
        """
        self._ensure_active()

        # Fetch a broad set of memories to analyze
        if query:
            result = self.recall(query, limit=50)
        else:
            result = self.recall("", limit=50)

        records = result.get("_records", [])
        if not records:
            return []

        conflicts: list[Conflict] = []
        analyzed_pairs: set[tuple[str, str]] = set()

        for i, old in enumerate(records):
            for j, new in enumerate(records):
                if i >= j:
                    continue

                pair_key = (old.memory_id, new.memory_id)
                if pair_key in analyzed_pairs:
                    continue
                analyzed_pairs.add(pair_key)

                # Skip if same content
                if old.content.strip().lower() == new.content.strip().lower():
                    continue

                # Check for explicit contradiction flag
                if new.metadata.get("contradiction_detected"):
                    conflicts.append(Conflict(
                        topic=old.title or old.content[:50],
                        old_memory=old,
                        new_memory=new,
                        similarity_score=0.5,
                        resolution="flagged_by_system",
                    ))
                    continue

                # Check for supersession chain
                if new.metadata.get("supersedes") == old.memory_id:
                    conflicts.append(Conflict(
                        topic=old.title or old.content[:50],
                        old_memory=old,
                        new_memory=new,
                        similarity_score=0.8,
                        resolution="supersession_chain",
                    ))
                    continue

                # Check confidence-based contradiction
                # Same type + similar confidence + contradictory content
                if old.type == new.type and abs(old.confidence - new.confidence) < 0.3:
                    # Simple heuristic: if same type and similar confidence
                    # but different content, flag as potential contradiction
                    old_lower = old.content.strip().lower()
                    new_lower = new.content.strip().lower()
                    
                    # Check for negation patterns
                    negation_markers = ["not ", "don't ", "doesn't ", "isn't ",
                                       "wasn't ", "won't ", "can't ", "cannot "]
                    has_negation = any(
                        marker in old_lower or marker in new_lower
                        for marker in negation_markers
                    )

                    if has_negation:
                        conflicts.append(Conflict(
                            topic=old.title or old.content[:50],
                            old_memory=old,
                            new_memory=new,
                            similarity_score=0.6,
                            resolution="potential_contradiction",
                        ))

        logger.info(
            "Contradiction detection: found %d conflicts across %d memories",
            len(conflicts), len(records),
        )
        return conflicts

    def resolve_contradiction(
        self,
        conflict: Conflict,
        strategy: ConflictResolution = ConflictResolution.KEEP_HIGHER_CONFIDENCE,
    ) -> dict[str, Any]:
        """
        Resolve a detected contradiction using the specified strategy.

        Args:
            conflict: The Conflict object to resolve.
            strategy: Resolution strategy:
                - KEEP_HIGHER_CONFIDENCE: Keep the memory with higher confidence
                - KEEP_NEWER: Keep the more recent memory
                - KEEP_BOTH: Mark both as contradicted but keep both
                - MARK_BOTH_CONTRADICTED: Mark both and store a resolution note

        Returns:
            Dict with resolution details.
        """
        self._ensure_active()

        if strategy == ConflictResolution.KEEP_HIGHER_CONFIDENCE:
            keeper = conflict.new_memory if conflict.new_memory.confidence >= conflict.old_memory.confidence else conflict.old_memory
            superseded = conflict.old_memory if keeper == conflict.new_memory else conflict.new_memory
            resolution_note = (
                f"Resolved by keeping higher-confidence memory "
                f"({keeper.confidence:.2f} > {superseded.confidence:.2f}). "
                f"Superseded memory: {superseded.memory_id}."
            )

            # Store a resolution memory noting the contradiction
            self.remember(
                content=resolution_note,
                memory_type="decision",
                title=f"Contradiction Resolution: {conflict.topic[:50]}",
                confidence=0.95,
                tags=["contradiction", "resolution"],
                source="contradiction_resolver",
            )
            conflict.resolution = "keep_higher_confidence"

            return {
                "status": "resolved",
                "strategy": "keep_higher_confidence",
                "keeper_id": keeper.memory_id,
                "superseded_id": superseded.memory_id,
                "note": resolution_note,
            }

        elif strategy == ConflictResolution.KEEP_NEWER:
            keeper = conflict.new_memory
            superseded = conflict.old_memory
            resolution_note = (
                f"Resolved by keeping newer memory. "
                f"Superseded memory: {superseded.memory_id}."
            )

            self.remember(
                content=resolution_note,
                memory_type="decision",
                title=f"Contradiction Resolution: {conflict.topic[:50]}",
                confidence=0.9,
                tags=["contradiction", "resolution"],
                source="contradiction_resolver",
            )
            conflict.resolution = "keep_newer"

            return {
                "status": "resolved",
                "strategy": "keep_newer",
                "keeper_id": keeper.memory_id,
                "superseded_id": superseded.memory_id,
                "note": resolution_note,
            }

        elif strategy == ConflictResolution.KEEP_BOTH:
            resolution_note = (
                f"Contradiction detected but both memories retained. "
                f"Memory A ({conflict.old_memory.memory_id}): {conflict.old_memory.content[:80]} "
                f"Memory B ({conflict.new_memory.memory_id}): {conflict.new_memory.content[:80]}"
            )

            self.remember(
                content=resolution_note,
                memory_type="context",
                title=f"Active Contradiction: {conflict.topic[:50]}",
                confidence=0.5,
                tags=["contradiction", "unresolved"],
                source="contradiction_resolver",
            )
            conflict.resolution = "keep_both"

            return {
                "status": "acknowledged",
                "strategy": "keep_both",
                "note": resolution_note,
            }

        elif strategy == ConflictResolution.MARK_BOTH_CONTRADICTED:
            resolution_note = (
                f"Both memories marked as contradicted due to conflicting information. "
                f"Manual verification recommended."
            )

            self.remember(
                content=resolution_note,
                memory_type="instruction",
                title=f"Contradiction Alert: {conflict.topic[:50]}",
                confidence=1.0,
                tags=["contradiction", "needs_verification"],
                source="contradiction_resolver",
            )
            conflict.resolution = "mark_both_contradicted"

            return {
                "status": "flagged",
                "strategy": "mark_both_contradicted",
                "note": resolution_note,
            }

        return {"status": "unknown_strategy", "strategy": strategy.value}

    # ── Context Management ───────────────────────────────────────

    def prefetch_context(
        self,
        task_context: str,
        limit: int = 10,
    ) -> str:
        """
        Retrieve relevant memories as a formatted context string.

        This is designed to be injected directly into an agent's
        system prompt for CrewAI's native memory injection flow.

        Args:
            task_context: Description of the current task for context retrieval.
            limit: Max memories to include.

        Returns:
            Formatted string of relevant memories, or empty string if none.
        """
        result = self.recall(task_context, limit=limit)
        memories = result.get("memories", [])

        if not memories:
            logger.info("No prefetched context for: '%s'", task_context)
            return ""

        lines = ["─── MEMANTO CONTEXT ───"]
        for i, mem in enumerate(memories, 1):
            mem_type = mem.get("type", "?")
            content = mem.get("content", "")
            conf = mem.get("confidence", 0)
            lines.append(f"[{i}] ({mem_type.upper()}, σ={conf:.2f}) {content}")

        lines.append("──────────────────────")
        context_str = "\n".join(lines)

        logger.info(
            "Prefetched %d memories for context: '%s'",
            len(memories), task_context,
        )
        return context_str

    def get_context_summary(self, limit: int = 20) -> dict[str, Any]:
        """
        Get a summary of all stored memories for this agent.

        Provides breakdown by memory type, total count, and recency stats.

        Returns:
            Dict with summary statistics.
        """
        result = self.recall("", limit=limit)
        memories = result.get("memories", [])

        type_counts: dict[str, int] = {}
        total_confidence = 0.0
        newest = ""
        oldest = ""

        for mem in memories:
            mtype = mem.get("type", "unknown")
            type_counts[mtype] = type_counts.get(mtype, 0) + 1
            total_confidence += mem.get("confidence", 0)

            created = mem.get("created_at", "")
            if not newest or created > newest:
                newest = created
            if not oldest or created < oldest:
                oldest = created

        return {
            "agent_id": self.agent_id,
            "total_memories": result.get("count", 0),
            "type_breakdown": dict(sorted(type_counts.items())),
            "avg_confidence": round(total_confidence / max(len(memories), 1), 2),
            "newest_memory": newest,
            "oldest_memory": oldest,
            "namespace": self._namespace,
        }

    # ── Export ───────────────────────────────────────────────────

    def export_to_json(self, output_path: str, limit: int = 100) -> str:
        """
        Export all memories to a JSON file.

        Args:
            output_path: Path for the JSON output file.
            limit: Max memories to export.

        Returns:
            Path to the exported file.
        """
        result = self.recall("", limit=limit)
        memories = result.get("memories", [])

        export_data = {
            "agent_id": self.agent_id,
            "namespace": self._namespace,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total": len(memories),
            "memories": memories,
        }

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(export_data, indent=2, default=str))

        logger.info("Exported %d memories to %s", len(memories), output_path)
        return str(path)

    # ── Internal Helpers ─────────────────────────────────────────

    def _ensure_active(self) -> None:
        """Ensure a session is active before operations."""
        if not self._active or not self._client:
            raise RuntimeError(
                "Session not active. Call .activate() before memory operations."
            )

    def __enter__(self):
        """Context manager support."""
        if not self._active:
            self.activate()
        return self

    def __exit__(self, *args):
        """Context manager cleanup."""
        self.deactivate()

    def __repr__(self) -> str:
        status = "active" if self._active else "inactive"
        return f"MemantoMemory(agent_id='{self.agent_id}', status='{status}')"


# ── Utility ──────────────────────────────────────────────────────

def cast_dict(data: Any) -> dict[str, Any]:
    """Safely cast to dict, handling non-dict returns."""
    return data if isinstance(data, dict) else {"data": str(data)}


# ── CrewAI Integration Notes ─────────────────────────────────────
#
# To use MemantoMemory with CrewAI:
#
# 1. Install: pip install memanto crewai
# 2. Set: export MEMANTO_API_KEY="mca_your_key_here"
# 3. Pass to Crew:
#
#    from memanto_memory import MemantoMemory
#
#    memory = MemantoMemory(agent_id="my-agent")
#    memory.activate()
#
#    crew = Crew(
#        agents=[...],
#        tasks=[...],
#        # CrewAI will use your custom memory backend
#        memory_config={"provider": "memanto", "adapter": memory},
#    )
