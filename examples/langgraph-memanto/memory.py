"""
Memanto integration wrapper for LangGraph agents.

Provides cross-session persistent memory via Memanto's CLI commands.
Three primitives: remember (store), recall (search), answer (RAG Q&A).
"""
import json
import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)


class MemantoMemory:
    """Persistent memory via Memanto CLI — works without a running server."""

    def __init__(self, agent_id: str | None = None):
        self.agent_id = agent_id or os.getenv("MEMANTO_AGENT_ID", "langgraph-support-agent")
        self._activate()

    def _run(self, args: list[str], capture: bool = True) -> str:
        """Run a memanto CLI command."""
        try:
            result = subprocess.run(
                ["memanto", *args],
                capture_output=capture,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                logger.warning(f"memanto {' '.join(args)} exited {result.returncode}: {result.stderr}")
            return (result.stdout or "") if capture else ""
        except FileNotFoundError:
            logger.error("memanto CLI not found. Install: pip install memanto")
            return ""
        except subprocess.TimeoutExpired:
            logger.warning("memanto command timed out")
            return ""

    def _activate(self):
        """Activate or create the agent session."""
        self._run(["agent", "activate", self.agent_id], capture=False)

    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        confidence: float = 0.9,
        tags: str | None = None,
        provenance: str = "explicit_statement",
        source: str | None = None,
    ) -> bool:
        """Store a memory in the agent's semantic database.

        Args:
            content: The memory content (what to remember).
            memory_type: Type from Memanto's 13 categories.
                        (fact, preference, instruction, decision, goal,
                         commitment, relationship, context, event,
                         learning, observation, artifact, error)
            confidence: How certain we are (0.0–1.0).
            tags: Comma-separated tags for filtering.
            provenance: Source of the memory.
            source: Agent source identifier.
        """
        cmd = [
            "remember", content,
            "--type", memory_type,
            "--confidence", str(confidence),
            "--provenance", provenance,
            "--source", source or self.agent_id,
        ]
        if tags:
            cmd.extend(["--tags", tags])
        self._run(cmd, capture=False)
        return True

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Search agent memories semantically.

        Returns a list of memory dicts, each with keys like:
            content, type, confidence, tags, created_at, source
        """
        raw = self._run(["recall", query, "--limit", str(limit), "--json"])
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return data
            return data.get("memories", data.get("results", []))
        except json.JSONDecodeError:
            return []

    def ask(self, question: str, limit: int = 5) -> str:
        """Ask a grounded RAG question over the agent's memories."""
        return self._run(["answer", question, "--limit", str(limit)])

    def get_context_string(self, query: str, limit: int = 5) -> str:
        """Get memories as a formatted context string (for prompt injection)."""
        memories = self.recall(query, limit)
        if not memories:
            return ""
        lines = ["Relevant memories from previous sessions:"]
        for m in memories:
            content = m.get("content", m.get("text", ""))
            mem_type = m.get("type", m.get("memory_type", "unknown"))
            confidence = m.get("confidence", "N/A")
            lines.append(f"  [{mem_type}] (confidence: {confidence}) {content}")
        return "\n".join(lines)


class MockMemantoMemory:
    """In-memory fallback when Memanto CLI is unavailable.
    
    Useful for testing the LangGraph workflow without a Moorcheh API key.
    """

    def __init__(self, agent_id: str | None = None):
        self.agent_id = agent_id or "test-agent"
        self._store: list[dict] = []

    def remember(
        self, content: str, memory_type: str = "fact",
        confidence: float = 0.9, tags: str | None = None,
        provenance: str = "explicit_statement",
        source: str | None = None,
    ) -> bool:
        self._store.append({
            "content": content,
            "type": memory_type,
            "confidence": confidence,
            "tags": tags or "",
            "source": source or self.agent_id,
            "created_at": "now",
        })
        logger.info(f"[Mock] Remembered [{memory_type}]: {content[:60]}...")
        return True

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        import re
        scored = []
        for m in self._store:
            score = len(re.findall(re.escape(query.lower()), m["content"].lower())) > 0
            if score:
                scored.append(m)
        return scored[:limit]

    def ask(self, question: str, limit: int = 5) -> str:
        memories = self.recall(question, limit)
        if not memories:
            return "No relevant memories found."
        return f"Based on {len(memories)} memory/memories: " + "; ".join(
            m["content"] for m in memories
        )

    def get_context_string(self, query: str, limit: int = 5) -> str:
        memories = self.recall(query, limit)
        if not memories:
            return ""
        lines = ["Relevant memories from previous sessions:"]
        for m in memories:
            lines.append(f"  [{m['type']}] (conf: {m['confidence']}) {m['content']}")
        return "\n".join(lines)


def create_memory() -> MemantoMemory | MockMemantoMemory:
    """Factory: returns MemantoMemory if CLI available, else MockMemantoMemory."""
    import shutil
    if shutil.which("memanto"):
        return MemantoMemory()
    logger.warning("memanto CLI not found — using MockMemantoMemory (in-memory, no persistence)")
    return MockMemantoMemory()
