"""
CrewAI_Memanto_Integration.py
==============================
Production-ready CrewAI ↔ Memanto agentic memory bridge.

Usage:
    from crewai_memanto_integration import MemantoMemory

    memory = MemantoMemory(api_key="...", agent_id="research-agent")
    memory.remember("Quantum computing basics", "fact", confidence=0.9)
    results = memory.recall("quantum computing")

Author: AtlasNexusOps — Bounty #37 ($100)
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from memanto.cli.client.sdk_client import SdkClient

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "memanto": {
        "api_key_env": "MEMANTO_API_KEY",
        "default_agent_id": "crewai-agent",
        "pattern": "tool",
        "session_duration_hours": 24,
    },
    "memory": {
        "default_confidence": 0.8,
        "max_retries": 3,
        "prefetch_limit": 10,
        "relevance_threshold": 0.5,
    },
    "embedding": {
        "model": "text-embedding-3-small",
    },
}


def load_config(path: Optional[str] = None) -> dict:
    """Load YAML config, falling back to env vars."""
    config = DEFAULT_CONFIG.copy()
    if path and Path(path).exists():
        with open(path) as f:
            user_config = yaml.safe_load(f)
            if user_config:
                _deep_update(config, user_config)
    return config


def _deep_update(base: dict, update: dict) -> None:
    for k, v in update.items():
        if isinstance(v, dict) and k in base:
            _deep_update(base[k], v)
        else:
            base[k] = v


# ─────────────────────────────────────────────────────────────
# MemantoMemory — CrewAI-compatible memory backend
# ─────────────────────────────────────────────────────────────

class MemantoMemory:
    """
    Memanto-powered memory backend for CrewAI agents.

    Replaces CrewAI's default in-memory storage with persistent,
    searchable, cross-session memory via Memanto.

    Usage:
        memory = MemantoMemory(api_key="...", agent_id="research-agent")
        memory.activate()

        # Store finding
        memory.remember(
            content="Quantum computing uses qubits for parallel computation.",
            memory_type="fact",
            tags=["quantum", "computing"],
        )

        # Retrieve later (even from different agent/session)
        results = memory.recall("quantum computing basics")
        for mem in results["memories"]:
            print(mem["title"], "-", mem["content"])
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        self.config = load_config(config_path)
        self.api_key = api_key or os.getenv(
            self.config["memanto"]["api_key_env"]
        )
        if not self.api_key:
            raise ValueError(
                "Memanto API key required. Set MEMANTO_API_KEY env var "
                "or pass api_key parameter."
            )

        self.agent_id = agent_id or self.config["memanto"]["default_agent_id"]
        self.client = SdkClient(api_key=self.api_key)
        self._active = False
        self._session_info: dict = {}

        # Track memories for deduplication
        self._memory_hashes: set = set()

    # ── Lifecycle ─────────────────────────────────────────

    def activate(self, duration_hours: Optional[int] = None) -> dict:
        """
        Create agent + activate session. Idempotent: reuses existing agent.

        Args:
            duration_hours: Session lifetime (default from config).

        Returns:
            Session info dict.
        """
        if self._active:
            return self._session_info

        # Create agent if doesn't exist
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern=self.config["memanto"]["pattern"],
                description=f"CrewAI agent — {self.agent_id}",
            )
            logger.info("Created agent '%s'", self.agent_id)
        except Exception:
            # Agent likely already exists — continue
            logger.debug("Agent '%s' already exists", self.agent_id)

        # Activate session
        session = self.client.activate_agent(
            agent_id=self.agent_id,
            duration_hours=duration_hours
            or self.config["memanto"]["session_duration_hours"],
        )
        self._active = True
        self._session_info = session
        logger.info("Activated session for '%s': %s", self.agent_id, session["session_id"])
        return session

    def deactivate(self) -> dict:
        """End the current session."""
        if not self._active:
            return {"status": "not_active"}
        result = self.client.deactivate_agent(self.agent_id)
        self._active = False
        self._session_info = {}
        return result

    # ── Core Memory Operations ────────────────────────────

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        title: Optional[str] = None,
        confidence: Optional[float] = None,
        tags: Optional[list[str]] = None,
        source: str = "crewai_agent",
    ) -> dict:
        """
        Store a memory. Auto-deduplicates by content hash.

        Args:
            content: The memory content to store.
            memory_type: One of fact, decision, instruction, commitment, event.
            title: Optional title (auto-generated from content if None).
            confidence: 0.0–1.0 (default from config).
            tags: Optional tags for categorization.
            source: Memory source identifier.

        Returns:
            Dict with memory_id, agent_id, status.
        """
        if not self._active:
            self.activate()

        # Deduplicate by content hash
        content_hash = hash(content)
        if content_hash in self._memory_hashes:
            logger.debug("Skipping duplicate memory: %s", content[:50])
            return {"status": "skipped", "reason": "duplicate"}

        confidence = confidence or self.config["memory"]["default_confidence"]
        title = title or (content[:47] + "..." if len(content) > 50 else content)

        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type=memory_type,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags or [],
            source=source,
        )
        self._memory_hashes.add(content_hash)
        return result

    def recall(
        self,
        query: str,
        limit: Optional[int] = None,
        memory_types: Optional[list[str]] = None,
        min_confidence: Optional[float] = None,
    ) -> dict:
        """
        Search memories by semantic similarity.

        Args:
            query: Natural-language search query.
            limit: Max results.
            memory_types: Filter by types.
            min_confidence: Minimum confidence threshold.

        Returns:
            Dict with agent_id, query, memories list, count.
        """
        if not self._active:
            self.activate()

        limit = limit or self.config["memory"]["prefetch_limit"]
        return self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            memory_types=memory_types,
            min_confidence=min_confidence,
        )

    def answer(self, question: str, **kwargs) -> dict:
        """
        Answer a question using RAG over stored memories.

        Args:
            question: Natural-language question.
            **kwargs: Passed to SdkClient.answer().

        Returns:
            Dict with answer, sources, namespace.
        """
        if not self._active:
            self.activate()
        return self.client.answer(agent_id=self.agent_id, question=question, **kwargs)

    # ── CrewAI Integration Helpers ────────────────────────

    def prefetch_context(self, task_description: str, limit: int = 5) -> str:
        """
        Get relevant memories as context string for CrewAI agent prompt.

        Call this before each agent execution to inject past knowledge.

        Args:
            task_description: What the agent is about to do.
            limit: Max memories to fetch.

        Returns:
            Formatted context string for injection into agent prompt.
        """
        results = self.recall(task_description, limit=limit)
        memories = results.get("memories", [])
        if not memories:
            return ""

        lines = ["[PREVIOUS KNOWLEDGE FROM MEMANTO]", ""]
        for i, mem in enumerate(memories, 1):
            mtype = mem.get("type", "fact")
            title = mem.get("title", "Untitled")
            content = mem.get("content", "")
            confidence = mem.get("confidence", "?")
            lines.append(f"{i}. [{mtype.upper()}] {title}")
            lines.append(f"   {content}")
            lines.append(f"   Confidence: {confidence}")
        lines.append("")
        return "\n".join(lines)

    def extract_memories(self, agent_output: str, tags: Optional[list[str]] = None) -> list[dict]:
        """
        Extract key findings from agent output and store as memories.

        Call this after each agent execution to persist new knowledge.

        Args:
            agent_output: The full output text from the CrewAI agent.
            tags: Optional tags for all extracted memories.

        Returns:
            List of stored memory results.
        """
        results = []
        # Split output into sentences/phrases, store substantive ones
        import re
        sentences = re.split(r'[.!?]\s+', agent_output)
        for sentence in sentences:
            sentence = sentence.strip()
            # Skip short/empty fragments
            if len(sentence) < 20 or len(sentence) > 500:
                continue
            # Detect memory type heuristically
            mem_type = self._classify_sentence(sentence)
            result = self.remember(
                content=sentence,
                memory_type=mem_type,
                tags=tags,
                source="crewai_output",
            )
            if result.get("status") != "skipped":
                results.append(result)
        return results

    def _classify_sentence(self, text: str) -> str:
        """Heuristic memory type classification."""
        lower = text.lower()
        if any(w in lower for w in ["should", "must", "need to", "action", "next step"]):
            return "instruction"
        if any(w in lower for w in ["decided", "chose", "selected", "will use"]):
            return "decision"
        if any(w in lower for w in ["promise", "commit", "will deliver", "deadline"]):
            return "commitment"
        if any(w in lower for w in ["happened", "occurred", "completed", "finished"]):
            return "event"
        return "fact"

    # ── Export ────────────────────────────────────────────

    def export_to_file(self, path: str, format: str = "md") -> str:
        """Export all memories to a file (md or json)."""
        if format == "md":
            return self.client.export_memory_md(self.agent_id, output_path=path)
        elif format == "json":
            all_memories = self.recall("*", limit=100)
            with open(path, "w") as f:
                json.dump(all_memories, f, indent=2, default=str)
            return path

    # ── Convenience ───────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active

    def __repr__(self):
        return f"MemantoMemory(agent_id='{self.agent_id}', active={self._active})"
