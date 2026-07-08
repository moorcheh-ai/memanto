"""Memanto API client with secure connection handling."""

import os
import time
import hashlib
import hmac
from typing import Optional
from urllib.parse import urljoin

import requests


class MemantoClient:
    """Client for the moorcheh.ai serverless backend."""
    
    DEFAULT_BASE_URL = "https://api.moorcheh.ai/v1"
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0
    REQUEST_TIMEOUT = 30
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key required. Set MOORCHEH_API_KEY environment variable "
                "or pass api_key parameter."
            )
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "memanto-python/0.1.0",
        })
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> dict:
        """Make an HTTP request with retry logic and timeout."""
        url = urljoin(self.base_url, endpoint)
        kwargs.setdefault("timeout", self.REQUEST_TIMEOUT)
        
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._session.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json() if response.content else {}
            except requests.exceptions.Timeout:
                if attempt == self.MAX_RETRIES - 1:
                    raise
                time.sleep(self.RETRY_DELAY * (2 ** attempt))
            except requests.exceptions.ConnectionError:
                if attempt == self.MAX_RETRIES - 1:
                    raise
                time.sleep(self.RETRY_DELAY * (2 ** attempt))
            except requests.exceptions.HTTPError as exc:
                if exc.response.status_code == 429:
                    # Rate limited - use exponential backoff
                    retry_after = int(
                        exc.response.headers.get("Retry-After", self.RETRY_DELAY)
                    )
                    time.sleep(retry_after)
                    continue
                raise
        
        raise RuntimeError("Max retries exceeded")
    
    def store_memory(self, memory_data: dict) -> dict:
        """Store a memory in the backend."""
        return self._make_request("POST", "/memories", json=memory_data)
    
    def retrieve_memories(
        self,
        query: str,
        limit: int = 10,
        filters: Optional[dict] = None,
    ) -> list:
        """Retrieve memories matching a query."""
        payload = {"query": query, "limit": limit, "filters": filters or {}}
        result = self._make_request("POST", "/memories/retrieve", json=payload)
        return result.get("memories", [])
    
    def delete_memory(self, memory_id: str) -> dict:
        """Delete a memory by ID."""
        return self._make_request("DELETE", f"/memories/{memory_id}")