 ```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +1,15 @@
+"""Memanto - Memory that AI Agents Love!
+
+A companion memory agent that lets your agents focus and improve
+while you keep ownership of everything they learn.
+"""
+
+from memanto.client import MemantoClient
+from memanto.config import Config
+from memanto.memory import Memory
+
+__all__ = [
+    "MemantoClient",
+    "Config", 
+    "Memory",
+]
+
+__version__ = "0.1.0"
+
--- a/memanto/client.py
+++ b/memanto/client.py
@@ -0,0 +1,120 @@
+"""Memanto client for interacting with the moorcheh.ai backend."""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import os
+from typing import Any
+
+import requests
+
+from memanto.config import Config
+from memanto.utils import get_logger
+
+logger = get_logger(__name__)
+
+
+class MemantoClient:
+    """Client for the moorcheh.ai serverless backend.
+    
+    Handles authentication, request signing, and communication
+    with the Memanto memory service.
+    """
+    
+    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
+        self.config = Config(api_key=api_key, base_url=base_url)
+        self._session: requests.Session | None = None
+    
+    @property
+    def session(self) -> requests.Session:
+        """Lazy-initialized requests session with connection pooling."""
+        if self._session is None:
+            self._session = requests.Session()
+            self._session.headers.update({
+                "Authorization": f"Bearer {self.config.api_key}",
+                "Content-Type": "application/json",
+                "X-Client-Version": "memanto-python/0.1.0",
+            })
+        return self._session
+    
+    def _sign_request(self, payload: dict[str, Any]) -> str:
+        """Create a request signature to prevent tampering.
+        
+        Uses HMAC-SHA256 with the API key to sign request payloads.
+        This prevents replay attacks and ensures payload integrity.
+        """
+        import hmac
+        
+        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
+        key_bytes = self.config.api_key.encode("utf-8")
+        return hmac.new(key_bytes, payload_bytes, hashlib.sha256).hexdigest()
+    
+    def store_memory(
+        self,
+        content: str,
+        memory_type: str = "general",
+        metadata: dict[str, Any] | None = None,
+    ) -> dict[str, Any]:
+        """Store a memory in the Memanto service.
+        
+        Args:
+            content: The memory content to store.
+            memory_type: Category for the memory.
+            metadata: Optional additional metadata.
+            
+        Returns:
+            The stored memory record from the server.
+            
+        Raises:
+            requests.HTTPError: If the request fails.
+        """
+        payload = {
+            "content": content,
+            "type": memory_type,
+            "metadata": metadata or {},
+        }
+        
+        # Add request signature for integrity verification
+        payload["signature"] = self._sign_request(payload)
+        
+        response = self.session.post(
+            f"{self.config.base_url}/memories",
+            json=payload,
+            timeout=30,
+        )
+        response.raise_for_status()
+        return response.json()
+    
+    def retrieve_memories(
+        self,
+        query: str,
+        limit: int = 10,
+        memory_type: str | None = None,
+    ) -> list[dict[str, Any]]:
+        """Retrieve relevant memories based on a query.
+        
+        Args:
+            query: The search query.
+            limit: Maximum number of results.
+            memory_type: Optional filter by memory type.
+            
+        Returns:
+            List of relevant memory records.
+        """
+        params: dict[str, Any] = {"q": query, "limit": limit}
+        if memory_type:
+            params["type"] = memory_type
+            
+        response = self.session.get(
+            f"{self.config.base_url}/memories/search",
+            params=params,
+            timeout=30,
+        )
+        response.raise_for_status()
+        return response.json().get("results", [])
+    
+    def close(self) -> None:
+        """Close the client session and release resources."""
+        if self._session is not None:
+            self._session.close()
+            self._session = None
+    
+    def __enter__(self) -> MemantoClient:
+        return self
+    
+    def __exit__(self, *args: Any) -> None:
+        self.close()
+
--- a/memanto/config.py
+++ b/memanto/config.py
@@ -0,0 +1,55 @@
+"""Configuration for Memanto client."""
+
+from __future__ import annotations
+
+import os
+from dataclasses import dataclass
+
+
+@dataclass(frozen=True)
+class Config:
+    """Memanto configuration with validation.
+    
+    Loads API key and base URL from environment variables or
+    explicit parameters. The API key is validated to prevent
+    common configuration errors.
+    """
+    
+    api_key: str
+    base_url: str = "https://api.moorcheh.ai/v1"
+    
+    def __init__(
+        self,
+        api_key: str | None = None,
+        base_url: str | None = None,
+    ) -> None:
+        resolved_key = api_key or os.getenv("MOORCHEH_API_KEY", "")
+        resolved_url = base_url or os.getenv(
+            "MOORCHEH_BASE_URL",
+            "https://api.moorcheh.ai/v1",
+        )
+        
+        object.__setattr__(self, "api_key", self._validate_api_key(resolved_key))
+        object.__setattr__(self, "base_url", resolved_url.rstrip("/"))
+    
+    @staticmethod
+    def _validate_api_key(key: str) -> str:
+        """Validate the API key format.
+        
+        Args:
+            key: The API key to validate.
+            
+        Returns:
+            The validated key.
+            
+        Raises:
+            ValueError: If the key is missing or malformed.
+        """
+        if not key:
+            raise ValueError(
+                "MOORCHEH_API_KEY is