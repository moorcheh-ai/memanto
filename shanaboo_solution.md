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
+from memanto.errors import MemantoError, AuthenticationError, RateLimitError
+
+__all__ = ["MemantoClient", "MemoryManager", "MemantoError", "AuthenticationError", "RateLimitError"]
+
+
+--- /dev/null
+++ b/memanto/client.py
@@ -0,0 +1,156 @@
+"""Memanto API client with secure credential handling and connection management."""
+
+from __future__ import annotations
+
+import os
+import re
+import time
+import urllib.parse
+from typing import Any
+
+import requests
+
+from memanto.errors import AuthenticationError, MemantoError, RateLimitError
+
+
+def _mask_key(key: str | None) -> str:
+    """Mask an API key for safe logging."""
+    if not key:
+        return "<not set>"
+    if len(key) <= 8:
+        return "***"
+    return key[:4] + "..." + key[-4:]
+
+
+class MemantoClient:
+    """Secure client for the moorcheh.ai memory backend.
+
+    Features:
+    - API key validation at initialization
+    - Secure header handling (no key leakage in logs/exceptions)
+    - Connection pooling via requests.Session
+    - Automatic retry with exponential backoff on 429/5xx
+    - Timeout enforcement to prevent hanging
+    """
+
+    DEFAULT_BASE_URL = "https://api.moorcheh.ai"
+    MAX_RETRIES = 3
+    BACKOFF_BASE = 1.0  # seconds
+
+    def __init__(
+        self,
+        api_key: str | None = None,
+        base_url: str | None = None,
+        timeout: float = 30.0,
+    ) -> None:
+        self._api_key = self._resolve_api_key(api_key)
+        self._base_url = self._resolve_base_url(base_url)
+        self._timeout = timeout
+        self._session = requests.Session()
+        self._session.headers.update(self._auth_headers())
+
+    def _resolve_api_key(self, api_key: str | None) -> str:
+        """Resolve API key from parameter or environment, with validation."""
+        key = api_key or os.environ.get("MOORCHEH_API_KEY")
+        if not key:
+            raise AuthenticationError(
+                "MOORCHEH_API_KEY not provided. Set it as an environment variable "
+                "or pass it to the MemantoClient constructor."
+            )
+        # Basic format validation to catch copy-paste errors early
+        if not re.match(r"^mch_[a-zA-Z0-9]{32,}$", key):
+            raise AuthenticationError(
+                f"Invalid API key format: {_mask_key(key)}. "
+                "Expected format: mch_<alphanumeric> (at least 32 chars after prefix)."
+            )
+        return key
+
+    def _resolve_base_url(self, base_url: str | None) -> str:
+        """Validate and normalize the base URL."""
+        url = base_url or os.environ.get("MOORCHEH_BASE_URL", self.DEFAULT_BASE_URL)
+        parsed = urllib.parse.urlparse(url)
+        if parsed.scheme not in ("https", "http"):
+            raise MemantoError(f"Invalid base URL scheme: {url}. Must be http or https.")
+        return url.rstrip("/")
+
+    def _auth_headers(self) -> dict[str, str]:
+        """Generate authorization headers."""
+        return {
+            "Authorization": f"Bearer {self._api_key}",
+            "Content-Type": "application/json",
+            "User-Agent": "memanto-python/0.1.0",
+        }
+
+    def _request(
+        self,
+        method: str,
+        path: str,
+        *,
+        retries: int = 0,
+        **kwargs: Any,
+    ) -> requests.Response:
+        """Make an HTTP request with retry logic and timeout."""
+        url = f"{self._base_url}{path}"
+        # Inject timeout if not already present
+        if "timeout" not in kwargs:
+            kwargs["timeout"] = self._timeout
+
+        try:
+            response = self._session.request(method, url, **kwargs)
+            response.raise_for_status()
+            return response
+        except requests.exceptions.HTTPError as exc:
+            if exc.response.status_code == 401:
+                raise AuthenticationError("Invalid API key. Please check your credentials.") from exc
+            if exc.response.status_code == 429:
+                if retries < self.MAX_RETRIES:
+                    wait = self.BACKOFF_BASE * (2 ** retries)
+                    time.sleep(wait)
+                    return self._request(method, path, retries=retries + 1, **kwargs)
+                to_raise = RateLimitError("Rate limit exceeded. Max retries reached.")
+                raise to_raise from exc
+            if 500 <= exc.response.status_code < 600 and retries < self.MAX_RETRIES:
+                wait = self.BACKOFF_BASE * (2 ** retries)
+                time.sleep(wait)
+                return self._request(method, path, retries=retries + 1, **kwargs)
+            raise MemantoError(f"API request failed: {exc}") from exc
+        except requests.exceptions.Timeout as exc:
+            raise MemantoError(f"Request to {url} timed out after {self._timeout}s") from exc
+        except requests.exceptions.RequestException as exc:
+            raise MemantoError(f"Network error: {exc}") from exc
+
+    def get(self, path: str, **kwargs: Any) -> requests.Response:
+        return self._request("GET", path, **kwargs)
+
+    def post(self, path: str, **kwargs: Any) -> requests.Response:
+        return self._request("POST", path, **kwargs)
+
+    def put(self, path: str, **kwargs: Any) -> requests.Response:
+        return self._request("PUT", path, **kwargs)
+
+    def delete(self, path: str, **kwargs: Any) -> requests.Response:
+        return self._request("DELETE", path, **kwargs)
+
+    def close(self) -> None:
+        """Close the underlying session to free connections."""
+        self._session.close()
+
+    def __enter__(self) -> MemantoClient