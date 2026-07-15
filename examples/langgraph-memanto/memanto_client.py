"""
Thin Memanto REST client.

Purpose:
    - Durable semantic memory backend
    - Independent of LangGraph execution state
    - Uses only documented Memanto v2 endpoints
"""

from __future__ import annotations

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

VALID_TYPES = {
    "instruction",
    "fact",
    "decision",
    "goal",
    "commitment",
    "preference",
    "relationship",
    "context",
    "event",
    "learning",
    "observation",
    "artifact",
    "error",
}


class MeMantoClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        agent_id: str = "langgraph-agent",
    ):
        self.base_url = (
            base_url or os.getenv("MEMANTO_BASE_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY", "")
        self.agent_id = agent_id
        self._token: str | None = None

        self._http = requests.Session()
        if self.api_key:
            self._http.headers["Authorization"] = f"Bearer {self.api_key}"
        self._http.headers["Content-Type"] = "application/json"

        self._ensure_agent()
        self._activate()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _aurl(self, path: str = "") -> str:
        return self._url(f"/api/v2/agents/{self.agent_id}{path}")

    def _headers(self) -> dict:
        return {"X-Session-Token": self._token} if self._token else {}

    def _ensure_agent(self):
        try:
            r = self._http.post(
                self._url("/api/v2/agents"),
                json={
                    "agent_id": self.agent_id,
                    "description": "LangGraph integration",
                },
                timeout=10,
            )
            if r.status_code not in (200, 201, 409):
                logger.warning("Agent creation returned %s", r.status_code)
        except Exception as exc:
            logger.error("Failed to create agent: %s", exc)

    def _activate(self):
        try:
            r = self._http.post(self._aurl("/activate"), json={}, timeout=10)
            r.raise_for_status()
            token = r.json().get("session_token")
            if not token:
                raise ValueError("Activation succeeded but session_token was empty")
            self._token = token
            logger.info("Activated Memanto session for %s", self.agent_id)
        except Exception as exc:
            logger.error("Activation failed: %s", exc)
            raise

    def _request_with_retry(self, method, url, **kwargs):
        response = method(url, **kwargs)
        if response.status_code == 401:
            logger.info("Session expired — reactivating Memanto session")
            self._activate()
            kwargs["headers"] = self._headers()
            response = method(url, **kwargs)
        return response

    def remember(
        self,
        content: str,
        memory_type: str = "observation",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> dict:
        if memory_type not in VALID_TYPES:
            memory_type = "observation"
        payload = {
            "content": content,
            "type": memory_type,
            "tags": tags or [],
            "metadata": {**(metadata or {}), "stored_at": time.time()},
        }
        try:
            r = self._request_with_retry(
                self._http.post,
                self._aurl("/remember"),
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            mem = r.json()
            if not mem.get("id") and mem.get("memory_id"):
                mem["id"] = mem["memory_id"]
            mid = mem.get("id") or mem.get("memory_id")
            if mid and "id" not in mem:
                mem["id"] = mid
            logger.info("Stored memory %s", mid)
            return mem
        except Exception as exc:
            logger.error("Remember failed: %s", exc)
            return {"id": None, "content": content, "error": str(exc)}

    def recall(
        self, query: str, limit: int = 5, memory_type: str | None = None
    ) -> list[dict]:
        payload: dict = {"query": query, "limit": limit}
        if memory_type:
            payload["type"] = memory_type
        try:
            r = self._request_with_retry(
                self._http.post,
                self._aurl("/recall"),
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get("memories", [])
        except Exception as exc:
            logger.error("Recall failed: %s", exc)
            return []

    def answer(self, question: str) -> str:
        try:
            r = self._request_with_retry(
                self._http.post,
                self._aurl("/answer"),
                json={"question": question},
                headers=self._headers(),
                timeout=20,
            )
            r.raise_for_status()
            return r.json().get("answer", "")
        except Exception as exc:
            logger.error("Answer failed: %s", exc)
            return ""

    def correct(self, old_content: str, new_content: str) -> dict:
        """
        Store a corrected fact as a new memory via POST /remember.
        The previous fact is preserved in metadata.previous_content for audit.
        Applications can inspect metadata.previous_content to resolve conflicts.
        """
        payload = {
            "content": new_content,
            "type": "fact",
            "tags": ["correction", "updated"],
            "metadata": {
                "previous_content": old_content,
                "correction": True,
                "updated_at": time.time(),
            },
        }
        try:
            r = self._request_with_retry(
                self._http.post,
                self._aurl("/remember"),
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            mem = r.json()
            logger.info("Stored correction memory %s", mem.get("id"))
            return mem
        except Exception as exc:
            logger.error("Correction failed: %s", exc)
            return {"id": None, "content": new_content, "error": str(exc)}
