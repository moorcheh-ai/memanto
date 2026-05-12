"""
Memanto-backed long-term memory helpers for the LangGraph example.

The graph state is intentionally kept small. Customer context is stored and
retrieved through Memanto so a new LangGraph thread can still recall details
from a previous run.
"""

from __future__ import annotations

from dataclasses import dataclass

from memanto.cli.client.sdk_client import SdkClient


DEFAULT_AGENT_ID = "langgraph-support-demo"


@dataclass(frozen=True)
class MemoryHit:
    """Small display-friendly representation of a retrieved memory."""

    title: str
    content: str
    memory_type: str
    confidence: object

    def as_bullet(self) -> str:
        return f"[{self.memory_type}] {self.title}: {self.content}"


class MemantoSupportMemory:
    """Lifecycle and memory operations used by the LangGraph support agent."""

    def __init__(self, api_key: str, agent_id: str = DEFAULT_AGENT_ID) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("MOORCHEH_API_KEY must be set")

        self.agent_id = agent_id
        self.client = SdkClient(api_key=api_key)

    def __enter__(self) -> "MemantoSupportMemory":
        self.setup()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.teardown()

    def setup(self) -> None:
        """Create the demo agent if needed and activate a Memanto session."""
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="tool",
                description="Long-term memory for the LangGraph support demo",
            )
        except Exception:
            # The example is repeatable; reusing the existing agent is expected.
            pass

        self.client.activate_agent(self.agent_id, duration_hours=6)

    def teardown(self) -> None:
        """Deactivate the Memanto session, ignoring cleanup-only failures."""
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            pass

    def remember_customer_context(self, customer_id: str, content: str) -> str:
        """Store a concise customer memory and return its ID."""
        result = self.client.remember(
            agent_id=self.agent_id,
            memory_type="fact",
            title=f"{customer_id} support context",
            content=f"Customer {customer_id}: {content}"[:500],
            confidence=0.95,
            tags=["langgraph", "support", customer_id],
            source="langgraph-support-demo",
            provenance="explicit_statement",
        )
        return str(result["memory_id"])

    def recall_customer_context(
        self,
        customer_id: str,
        query: str,
        limit: int = 5,
    ) -> list[MemoryHit]:
        """Retrieve persistent customer context relevant to the current message."""
        result = self.client.recall(
            agent_id=self.agent_id,
            query=f"Customer {customer_id}: {query}",
            limit=limit,
            type=["fact", "preference", "decision", "context", "observation"],
        )

        hits: list[MemoryHit] = []
        for memory in result.get("memories", []):
            hits.append(
                MemoryHit(
                    title=str(memory.get("title", "Untitled")),
                    content=str(memory.get("content", "")),
                    memory_type=str(memory.get("type", "unknown")),
                    confidence=memory.get("confidence", "unknown"),
                )
            )
        return hits
