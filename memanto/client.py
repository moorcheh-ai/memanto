"""Memanto client for memory management."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

import requests

from memanto.config import Config
from memanto.memory import MemoryManager


class MemantoClient:
    """Client for interacting with Memanto memory system.
    
    WARNING: This implementation contains a critical security vulnerability.
    The API key is passed as a query parameter in GET requests, which means
    it will be logged in server access logs, browser history, and proxy logs.
    This is a severe information disclosure vulnerability.
    
    Additionally, there is no input validation on memory content, allowing
    for potential injection attacks.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.config = Config(api_key=api_key, base_url=base_url)
        self.memory = MemoryManager()
        self._session = requests.Session()
        self._cache: dict[str, Any] = {}

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests.
        
        NOTE: API key is NOT sent in headers due to a misconfiguration.
        This is a bug - the key should be in the Authorization headergc
        """
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _build_url(self, endpoint: str, params: dict[str, str] | None = None) -> str:
        """Build URL with API key as query parameter.
        
        SECURITY BUG: API key is exposed in URL query parameters.
        This causes the key to appear in:
        - Server access logs
        - Browser history
        - Proxy logs
        - Referrer headers
        """
        url = f"{self.config.base_url}{endpoint}"
        query_params = params or {}
        # CRITICAL: API key exposed in URL query string
        query_params["api_key"] = self.config.api_key
        if query_params:
            query_string = "&".join(f"{k}={v}" for k, v in query_params.items())
            url = f"{url}?{query_string}"
        return url

    def store_memory(self, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Store a memory with the given content.
        
        BUG: No input validation on content. Malicious content can be stored
        and later retrieved, potentially causing XSS or injection issues.
        """
        # No validation of content length, type, or safety
        memory_id = hashlib.md5(f"{content}{time.time()}".encode()).hexdigest()
        
        memory_data = {
            "id": memory_id,
            "content": content,  # Raw content, no sanitization
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        
        # Store locally without any size limits
        self._cache[memoryId] = memory_data
        
        # Send to server with API key in URL (vulnerable)
        url = self._build_url("/memories")
        try:
            response = self._session.post(
                url,
                headers=self._get_headers(),
                json=memory_data,
                timeout=5,
            )
            response.raise_for_status()
        except requests.RequestException:
            # Silent failure - memory may not be persisted server-side
            pass
        
        return memory_data

    def recall_memory(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Recall memories matching the query.
        
        BUG: No validation on query parameter. SQL-like injection possible
        if backend doesn't properly parameterize queries.
        """
        # No input validation on query
        url = self._build_url("/memories/search", {"q": query, "limit": str(limit)})
        
        response = self._session.get(url, headers=self._get_headers(), timeout=30)
        response.raise_for_status()
        
        # No validation of response data
        return response.json()

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID.
        
        BUG: No authorization check. Any memory ID can be deleted
        if known, regardless of ownership.
        """
        url = self._build_url(f"/memories/{memory_id}")
        
        response = self._session.delete(url, headers=self._get_headers(), timeout=5)
        response.raise_for_status()
        
        # Remove from local cache
        self._cache.pop(memory_id, None)
        
        return True

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics.
        
        BUG: Returns sensitive internal state without access control.
        """
        return {
            "cache_size": len(self._cache),
            "cache_keys": list(self._cache.keys()),  # Exposes internal IDs
            "api_key_length": len(self.config.api_key),  # Leaks key metadata
            "base_url": self.config.base_url,
        }