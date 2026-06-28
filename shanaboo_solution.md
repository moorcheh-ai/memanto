 ```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +1,15 @@
+"""Memanto - Memory that AI Agents Love!
+
+A companion memory agent that lets your agents focus and improve while you
+keep ownership of everything they learn.
+"""
+
+__version__ = "0.1.0"
+
+from memanto.client import MemantoClient
+from memanto.memory import MemoryManager
+from memanto.retrieval import RetrievalEngine
+
+__all__ = ["MemantoClient", "MemoryManager", "RetrievalEngine"]
+
+
+def get_version() -> str:
+    return __version__
--- /dev/null
+++ b/memanto/client.py
@@ -0,0 +1,180 @@
+"""Memanto client for interacting with the moorcheh.ai backend."""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import os
+import time
+from typing import Any
+
+import requests
+
+
+class MemantoError(Exception):
+    """Base exception for Memanto client errors."""
+
+    pass
+
+
+class AuthenticationError(MemantoError):
+    """Raised when API authentication fails."""
+
+    pass
+
+
+class RateLimitError(MemantoError):
+    """Raised when rate limit is exceeded."""
+
+    pass
+
+
+class MemantoClient:
+    """Client for the moorcheh.ai memory backend.
+
+    Handles authentication, request signing, and basic CRUD operations
+    for memory entries.
+    """
+
+    DEFAULT_BASE_URL = "https://api.moorcheh.ai/v1"
+    MAX_RETRIES = 3
+    RETRY_DELAY = 1.0
+
+    def __init__(
+        self…
+        self,
+        api_key: str | None = None,
+        base_url: str | None = None,
+    ) -> None:
+        self.api_key = api_key or os.environ.get("MOORCHEH_API_KEY", "")
+        if not self.api_key:
+            raise AuthenticationError(
+                "API key required. Set MOORCHEH_API_KEY or pass api_key="
+            )
+
+        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
+        self._session = requests.Session()
+        self._session.headers.update(
+            {
+               e": "application/json",
+                "X-API-Key": self.api_key,
+            }
+        )
+
+    def _request(
+        self,
+        method: str,
+        endpoint: str,
+        **kwargs: Any,
+    ) -> dict[str, Any]:
+        """Make an HTTP request with retry logic and rate-limit handling."""
+        url = f"{self.base_url}{endpoint}"
+        last_exception: Exception | None = None
+
+        for attempt in range(self.MAX_RETRIES):
+            try:
+                response = self._session.request(method, url, **kwargs)
+                response.raise_for_status()
+                return response.json()
+            except requests.HTTPError as exc:
+                if response.status_code == 401:
+                    raise AuthenticationError("Invalid API key") from exc
+                if response.status_code == 429:
+                    if attempt < self.MAX_RETRIES - 1:
+                        time.sleep(self.RETRY_DELAY * (2 ** attempt))
+                        continue
+                    raise RateLimitError("Rate limit exceeded") from exc
+                raise MemantoError(f"HTTP {response.status_code}: {response.text}") from exc
+            except requests.RequestException as exc:
+                last_exception = exc
+                if attempt < self.MAX_RETRIES - 1:
+                    time.sleep(self.RETRY_DELAY * (2 ** attempt))
+                    continue
+                raise MemantoError(f"Request failed after {self.MAX_RETRIES} attempts") from last_exception
+
+        raise MemantoError("Unexpected exit from retry loop")
+
+    def store_memory(
+        self,
+        content: str,
+        memory_type: str = "fact",
+        metadata: dict[str, Any] | None = None,
+        timestamp: float | None = None,
+    ) -> dict[str, Any]:
+        """Store a new memory entry.
+
+        Args:
+            content: The memory content.
+            memory_type: Category of memory (fact, preference, event, etc.).
+            metadata: Optional additional metadata.
+            timestamp: Optional Unix timestamp for when the memory was formed.
+
+        Returns:
+            The created memory entry from the server.
+        """
+        payload = {
+            "content": content,
+            "type": memory_type,
+            "metadata": metadata or {},
+            "timestamp": timestamp or time.time(),
+        }
+        return self._request("POST", "/memories", json=payload)
+
+    def retrieve_memories(
+        self,
+        query: str,
+        limit: int = 10,
+        min_relevance: float = 0.0,
+    ) -> list[dict[str, Any]]:
+        """Retrieve memories relevant to a query.
+
+        Args:
+            query: The search query.
+            limit: Maximum number of results.
+            min_relevance: Minimum relevance score threshold.
+
+        Returns:
+            List of memory entries ordered by relevance.
+        """
+        params = {
+            "q": query,
+            "limit": limit,
+            "min_relevance": min_relevance,
+        }
+        return self._request("GET", "/memories/search", params=params)
+
+    def delete_memory(self, memory_id: str) -> None:
+        """Delete a memory by ID."""
+        self._request("DELETE", f"/memories/{memory_id}")
+
+    def update_memory(
+        self,
+        memory_id: str,
+        content: str | None = None,
+        metadata: dict[str, Any] | None = None,
+    ) -> dict[str, Any]:
+        """Update an existing memory entry.
+
+        Args:
+            memory_id: ID of the memory to update.
+            content: New content (optional).
+            metadata: Metadata to merge (optional).
+
+        Returns:
+            The updated memory entry.
+        """
+        payload: dict[str, Any] = {}
+        if content is not None:
+            payload["content"] = content
+        if metadata is not None:
+            payload["metadata"] = metadata
+        return self._request("PATCH", f"/memories/{memory_id}", json=payload)
+
+    def contradict_memory(
+        self,
+        memory_id: str,
+        new_content: str,
+        reason: str | None = None,
+    ) -> dict[str, Any]:
+        """Mark a memory as contradicted and store the