"""
Memory Read Service
"""
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.utils.errors import MemoryError


class MemoryReadService:
    def __init__(self, moorcheh_client: "MoorchehClient"):
        self.client = moorcheh_client

    def search_memories(
        self,
        query: str,
        agent_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search memories by query string."""
        params: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "offset": offset,
        }
        if agent_id:
            params["agent_id"] = agent_id
        try:
            result = self.client.search(json=params)
            return result.get("results", [])
        except Exception as e:
            raise MemoryError(f"Search failed: {e}") from e

    def search_as_of(
        self,
        as_of_date: str,
        agent_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search memories as of a specific date."""
        params: dict[str, Any] = {
            "as_of": as_of_date,
            "limit": limit,
        }
        if agent_id:
            params["agent_id"] = agent_id
        try:
            result = self.client.search(json=params)
            return result.get("results", [])
        except Exception as e:
            raise MemoryError(f"Search as_of failed: {e}") from e

    def search_changed_since(
        self,
        since_date: str,
        agent_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search memories changed since a specific date."""
        params: dict[str, Any] = {
            "since": since_date,
            "limit": limit,
        }
        if agent_id:
            params["agent_id"] = agent_id
        try:
            result = self.client.search(json=params)
            return result.get("results", [])
        except Exception as e:
            raise MemoryError(f"Search changed_since failed: {e}") from e

    def search_recent(
        self,
        agent_id: str | None = None,
        type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search recent memories."""
        params: dict[str, Any] = {
            "limit": limit,
        }
        if agent_id:
            params["agent_id"] = agent_id
        if type:
            params["type"] = type
        try:
            result = self.client.search(json=params)
            return result.get("results", [])
        except Exception as e:
            raise MemoryError(f"Search recent failed: {e}") from e
