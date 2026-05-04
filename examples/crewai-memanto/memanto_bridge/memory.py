"""
MeMantoMemory
=============
Low-level client wrapping Memanto's v2 REST API.

Endpoint map (from official docs):
  POST  /api/v2/agents                        – create agent namespace
  POST  /api/v2/agents/{id}/activate          – start session → session_token
  POST  /api/v2/agents/{id}/remember          – store one memory
  POST  /api/v2/agents/{id}/batch-remember    – store up to 100 memories
  GET   /api/v2/agents/{id}/recall            – semantic search
  POST  /api/v2/agents/{id}/answer            – RAG answer over memories
  PATCH /api/v2/agents/{id}/memories/{mem_id} – update/correct a memory

Auth headers required:
  Authorization: Bearer {moorcheh_api_key}
  X-Session-Token: {session_token}   (for memory operations)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# All 13 semantic types Memanto supports
VALID_MEMORY_TYPES = {
    "instruction", "fact", "decision", "goal", "commitment",
    "preference", "relationship", "context", "event", "learning",
    "observation", "artifact", "error",
}


class MeMantoMemory:
    """
    Thin, session-aware client over the Memanto v2 REST API.

    Environment variables (can also be passed directly):
        MEMANTO_BASE_URL  – e.g. http://127.0.0.1:8000
        MOORCHEH_API_KEY  – bearer token from the Moorcheh dashboard
        MEMANTO_AGENT_ID  – agent namespace to use
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        auto_activate: bool = True,
    ):
        self.base_url = (
            base_url or os.getenv("MEMANTO_BASE_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY", "")
        self.agent_id = agent_id or os.getenv("MEMANTO_AGENT_ID", "crewai-default")
        self._session_token: Optional[str] = None

        self._http = requests.Session()
        if self.api_key:
            self._http.headers["Authorization"] = f"Bearer {self.api_key}"
        self._http.headers["Content-Type"] = "application/json"

        if auto_activate:
            self._ensure_agent()
            self._activate_session()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _agent_url(self, path: str = "") -> str:
        return self._url(f"/api/v2/agents/{self.agent_id}{path}")

    def _auth_headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {}
        if self._session_token:
            h["X-Session-Token"] = self._session_token
        return h

    def _ensure_agent(self) -> None:
        """Create the agent namespace if it doesn't exist (idempotent)."""
        try:
            r = self._http.post(
                self._url("/api/v2/agents"),
                json={"agent_id": self.agent_id, "description": "CrewAI integration agent"},
                timeout=10,
            )
            if r.status_code not in (200, 201, 409):
                logger.warning("[Memanto] agent create status=%s", r.status_code)
            else:
                logger.info("[Memanto] agent namespace ready: %s", self.agent_id)
        except requests.RequestException as exc:
            logger.error("[Memanto] _ensure_agent failed: %s", exc)

    def _activate_session(self) -> None:
        """Activate a session and cache the 6-hour session token."""
        try:
            r = self._http.post(self._agent_url("/activate"), json={}, timeout=10)
            if r.ok:
                self._session_token = r.json().get("session_token")
                logger.info("[Memanto] session activated agent=%s", self.agent_id)
            else:
                logger.warning("[Memanto] activate status=%s", r.status_code)
        except requests.RequestException as exc:
            logger.error("[Memanto] _activate_session failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Core operations
    # ------------------------------------------------------------------ #

    def store(
        self,
        content: str,
        memory_type: str = "observation",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """
        Persist a memory.

        Args:
            content:     Text to remember.
            memory_type: One of Memanto's 13 semantic types.
            tags:        Free-form tags for later filtering.
            metadata:    Arbitrary key/value pairs.

        Returns:
            Created memory object dict (has 'id' key).
        """
        if memory_type not in VALID_MEMORY_TYPES:
            logger.warning("[Memanto] unknown type '%s' → 'observation'", memory_type)
            memory_type = "observation"

        payload: Dict[str, Any] = {
            "content": content,
            "type": memory_type,
            "tags": tags or [],
            "metadata": {**(metadata or {}), "stored_at": time.time()},
        }
        try:
            r = self._http.post(
                self._agent_url("/remember"),
                json=payload,
                headers=self._auth_headers(),
                timeout=15,
            )
            r.raise_for_status()
            mem = r.json()
            logger.info("[Memanto] stored id=%s type=%s", mem.get("id"), memory_type)
            return mem
        except requests.RequestException as exc:
            logger.error("[Memanto] store failed: %s", exc)
            return {"id": None, "content": content, "error": str(exc)}

    def batch_store(self, memories: List[Dict]) -> List[Dict]:
        """Store up to 100 memories in one API call."""
        try:
            r = self._http.post(
                self._agent_url("/batch-remember"),
                json={"memories": memories},
                headers=self._auth_headers(),
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("memories", [])
        except requests.RequestException as exc:
            logger.error("[Memanto] batch_store failed: %s", exc)
            return []

    def search(
        self,
        query: str,
        limit: int = 5,
        memory_type: Optional[str] = None,
    ) -> List[Dict]:
        """
        Semantic search over stored memories.

        Returns list of memory dicts ordered by relevance.
        """
        params: Dict[str, Any] = {"q": query, "limit": limit}
        if memory_type:
            params["type"] = memory_type
        try:
            r = self._http.get(
                self._agent_url("/recall"),
                params=params,
                headers=self._auth_headers(),
                timeout=15,
            )
            r.raise_for_status()
            results = r.json().get("memories", [])
            logger.info("[Memanto] search '%s' → %d results", query, len(results))
            return results
        except requests.RequestException as exc:
            logger.error("[Memanto] search failed: %s", exc)
            return []

    def answer(self, question: str) -> str:
        """Generate a grounded RAG answer using the agent's stored memories."""
        try:
            r = self._http.post(
                self._agent_url("/answer"),
                json={"question": question},
                headers=self._auth_headers(),
                timeout=20,
            )
            r.raise_for_status()
            return r.json().get("answer", "")
        except requests.RequestException as exc:
            logger.error("[Memanto] answer failed: %s", exc)
            return ""

    def update(self, memory_id: str, new_content: str, metadata: Optional[Dict] = None) -> Dict:
        """
        Correct/overwrite an existing memory.
        Old content is preserved in metadata for audit trail.
        This is the key mechanism for handling contradictory memories.
        """
        # Fetch current content to preserve as audit trail
        old_content = ""
        try:
            r = self._http.get(
                self._agent_url(f"/memories/{memory_id}"),
                headers=self._auth_headers(),
                timeout=10,
            )
            if r.ok:
                old_content = r.json().get("content", "")
        except Exception:
            pass

        payload = {
            "content": new_content,
            "metadata": {
                **(metadata or {}),
                "previous_content": old_content,
                "updated_at": time.time(),
                "correction": True,
            },
        }
        try:
            r = self._http.patch(
                self._agent_url(f"/memories/{memory_id}"),
                json=payload,
                headers=self._auth_headers(),
                timeout=15,
            )
            r.raise_for_status()
            logger.info("[Memanto] updated (corrected) memory id=%s", memory_id)
            return r.json()
        except requests.RequestException as exc:
            logger.error("[Memanto] update failed: %s", exc)
            return {"id": memory_id, "content": new_content, "error": str(exc)}
