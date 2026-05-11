import os
from typing import Optional

from memanto.cli.client.sdk_client import SdkClient


class MemantoMemory:
    """Wrapper around Memanto for cross-session persistent memory."""

    def __init__(self, api_key: Optional[str] = None, agent_id: str = "langgraph-agent"):
        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY", "")
        self.agent_id = agent_id
        self.client = SdkClient(api_key=self.api_key)
        self._ensure_agent()

    def _ensure_agent(self):
        try:
            self.client.create_agent(
                agent_id=self.agent_id,
                pattern="tool",
                description="LangGraph integration agent"
            )
        except Exception:
            pass
        self.client.activate_agent(self.agent_id, duration_hours=6)

    def close(self):
        try:
            self.client.deactivate_agent(self.agent_id)
        except Exception:
            pass

    def remember_conversation(self, user_id: str, message: str, role: str = "user"):
        self.client.remember(
            agent_id=self.agent_id,
            memory_type="event",
            title=f"Conversation with {user_id}",
            content=message,
            tags=[user_id, role, "conversation"],
            source=role,
            provenance="explicit_statement",
        )

    def remember_preference(self, user_id: str, preference: str):
        self.client.remember(
            agent_id=self.agent_id,
            memory_type="preference",
            title=f"User {user_id} preference",
            content=preference,
            tags=[user_id, "preference"],
            source="user",
            provenance="explicit_statement",
        )

    def recall_user_context(self, user_id: str, query: str, limit: int = 5):
        result = self.client.recall(
            agent_id=self.agent_id,
            query=query,
            limit=limit,
            tags=[user_id],
        )
        return result.get("memories", [])

    def recall_preferences(self, user_id: str):
        result = self.client.recall(
            agent_id=self.agent_id,
            query="user preferences and settings",
            limit=5,
            type=["preference"],
            tags=[user_id],
        )
        return result.get("memories", [])

    def answer_from_memory(self, question: str, user_id: str) -> str:
        result = self.client.answer(
            agent_id=self.agent_id,
            question=question,
            limit=5,
            temperature=0.3,
        )
        return result.get("answer", "")
