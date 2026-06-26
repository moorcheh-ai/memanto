"""Memanto client for memory management."""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from memanto.config import MemantoConfig
from memanto.types import Memory, MemoryQuery, MemoryResult


class MemantoClient:
    """Client for interacting with the Memanto memory service."""
    
    def __init__(self, config: MemantoConfig | None = None) -> None:
        self.config = config or MemantoConfig()
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        })
        self._last_request_time: float = 0.0
    
    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        if self.config.rate_limit_seconds > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.config.rate_limit_seconds:
                time.sleep(self.config.rate_limit_seconds - elapsed)
            self._last_request_time = time.time()
    
    def store_memory(
        self,
        content: str,
        memory_type: str = "general",
        metadata: dict[str, Any] | None = None,
    ) -> Memory:
        """Store a new memory.
        
        Args:
            content: The memory content to store.
            memory_type: Category/type of memory.
            metadata: Optional additional metadata.
            
        Returns:
            The stored Memory object.
            
        Raises:
            ValueError: If content is empty or too long.
            requests.HTTPError: On API errors.
        """
        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty")
        if len(content) > self.config.max_content_length:
            raise ValueError(
                f"Content exceeds maximum length of {self.config.max_content_length}"
            )
        
        self._rate_limit()
        
        payload = {
            "content": content.strip(),
            "type": memory_type,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        
        response = self._session.post(
            f"{self.config.base_url}/memories",
            json=payload,
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        return Memory(**response.json())
    
    def query_memories(
        self,
        query: str,
        limit: int = 10,
        memory_type: str | None = None,
    ) -> list[MemoryResult]:
        """Query stored memories.
        
        Args:
            query: The search query.
            limit: Maximum number of results.
            memory_type: Optional filter by memory type.
            
        Returns:
            List of matching memory results.
        """
        self._rate_limit()
        
        params: dict[str, Any] = {"q": query, "limit": limit}
        if memory_type:
            params["type"] = memory_type
        
        response = self._session.get(
            f"{self.config.base_url}/memories/search",
            params=params,
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        return [MemoryResult(**item) for item in response.json()]