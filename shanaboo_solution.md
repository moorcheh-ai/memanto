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
+from memanto.client import MemantoClient
+from memanto.memory import MemoryManager
+from memanto.types import Memory, MemoryQuery, MemoryResult
+
+__all__ = [
+    "MemantoClient",
+    "MemoryManager",
+    "Memory",
+    "MemoryQuery",
+    "MemoryResult",
+]
--- /dev/null
+++ b/memanto/client.py
@@ -0,0 +1,247 @@
+"""Memanto client for interacting with the moorcheh.ai backend."""
+
+from __future__ import annotations
+
+import hashlib
+import json
+import os
+import threading
+import time
+import uuid
+from dataclasses import dataclass, field
+from typing import Any, Callable, Optional
+
+import requests
+
+from memanto.types import Memory, MemoryQuery, MemoryResult
+
+
+@dataclass
+class RetryConfig:
+    """Configuration for retry behavior."""
+    max_retries: int = 3
+    base_delay: float = 1.0
+    max_delay: float = 60.0
+    exponential_base: float = 2.0
+
+
+@dataclass
+class MemantoConfig:
+    """Configuration for the Memanto client."""
+    api_key: str = field(default_factory=lambda: os.environ.get("MOORCHEH_API_KEY", ""))
+    base_url: str = "https://api.moorcheh.ai/v1"
+    timeout: int = 30
+    retry: RetryConfig = field(default_factory=RetryConfig)
+    # Security: Input validation limits
+    max_content_length: int = 100000  # ~100KB max memory content
+    max_tags: int = 50
+    max_tag_length: int = 100
+
+
+class MemantoError(Exception):
+    """Base exception for Memanto client errors."""
+    pass
+
+
+class AuthenticationError(MemantoError):
+    """Raised when API authentication fails."""
+    pass
+
+
+class RateLimitError(MemantoError):
+    """Raised when rate limit is exceeded."""
+    pass
+
+
+class ValidationError(MemantoError):
+    """Raised when input validation fails."""
+    pass
+
+
+class MemantoClient:
+    """Client for interacting with the Memanto memory service."""
+
+    def __init__(self, config: Optional[MemantoConfig] = None):
+        self.config = config or MemantoConfig()
+        self._session = requests.Session()
+        self._lock = threading.RLock()
+        self._last_request_time: Optional[float] = None
+        self._request_count = 0
+        self._cache: dict[str, Any] = {}
+        self._cache_lock = threading.RLock()
+
+    def _validate_input(self, content: str, tags: Optional[list[str]] = None) -> None:
+        """Validate input content and tags for security and sanity.
+        
+        Prevents:
+        - Excessively large inputs that could cause memory issues
+        - Malformed tags that could affect retrieval
+        - Empty or whitespace-only content
+        """
+        if not content or not isinstance(content, str):
+            raise ValidationError("Content must be a non-empty string")
+        
+        if len(content) > self.config.max_content_length:
+            raise ValidationError(
+                f"Content exceeds maximum length of {self.config.max_content_length} characters"
+            )
+        
+        if not content.strip():
+            raise ValidationError("Content cannot be whitespace-only")
+        
+        # Check for potential prompt injection patterns
+        dangerous_patterns = [
+            "<script",
+            "javascript:",
+            "data:",
+            "vbscript:",
+        ]
+        content_lower = content.lower()
+        for pattern in dangerous_patterns:
+            if pattern in content_lower:
+                raise ValidationError(f"Content contains potentially dangerous pattern: {pattern}")
+        
+        if tags:
+            if len(tags) > self.config.max_tags:
+                raise ValidationError(f"Too many tags: maximum is {self.config.max_tags}")
+            
+            for tag in tags:
+                if not isinstance(tag, str):
+                    raise ValidationError("All tags must be strings")
+                if len(tag) > self.config.max_tag_length:
+                    raise ValidationError(f"Tag exceeds maximum length: {tag[:50]}...")
+                if not tag.strip():
+                    raise ValidationError("Tags cannot be empty or whitespace-only")
+
+    def _make_request(
+        self,
+        method: str,
+        endpoint: str,
+        data: Optional[dict] = None,
+        retries: int = 0,
+    ) -> dict:
+        """Make an HTTP request with retry logic and rate limiting."""
+        url = f"{self.config.base_url}{endpoint}"
+        headers = {
+            "Authorization": f"Bearer {self.config.api_key}",
+            "Content-Type": "application/json",
+            "X-Client-Version": "memanto/1.0.0",
+        }
+
+        try:
+            with self._lock:
+                # Simple rate limiting: ensure at least 0.1s between requests
+                if self._last_request_time is not None:
+                    elapsed = time.time() - self._last_request_time
+                    if elapsed < 0.1:
+                        time.sleep(0.1 - elapsed)
+                
+                response = self._session.request(
+                    method=method,
+                    url=url,
+                    headers=headers,
+                    json=data,
+                    timeout=self.config.timeout,
+                )
+                self._last_request_time = time.time()
+                self._request_count += 1
+
+            if response.status_code == 401:
+                raise AuthenticationError("Invalid API key")
+            elif response.status_code == 429:
+                if retries < self.config.retry.max_retries:
+                    delay = min(
+                        self.config.retry.base_delay * (self.config.retry.exponential_base ** retries),
+                        self.config.retry.max_delay,
+                    )
+                    time.sleep(delay)
+                    return self._make_request(method, endpoint, data, retries + 1)
+                raise RateLimitError("Rate limit exceeded, max retries reached")
+            
+            response.raise_for_status()
+            return response.json() if response.content else {}
+        
+        except requests.exceptions.Timeout:
+            if retries < self.config.retry.max_retries:
+                delay = min(
+                    self.config.retry.base_delay * (self.config.retry.exponential