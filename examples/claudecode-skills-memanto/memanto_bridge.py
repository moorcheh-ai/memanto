"""
memanto_bridge.py
=================
Thin, dependency-free wrapper around Memanto's v2 REST API.

Used as the sole memory backend for the skills memory companion.
Uses ONLY documented endpoints — no undocumented PATCH or filter flags.

Documented endpoints used:
  POST /api/v2/agents                     – create agent namespace
  POST /api/v2/agents/{id}/activate       – get session token
  POST /api/v2/agents/{id}/remember       – store memory
  GET  /api/v2/agents/{id}/recall         – semantic search
  POST /api/v2/agents/{id}/answer         – RAG answer

Auth headers:
  Authorization: Bearer {moorcheh_api_key}
  X-Session-Token: {session_token}
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

VALID_MEMORY_TYPES = {
    "instruction", "fact", "decision", "goal", "commitment",
    "preference", "relationship", "context", "event", "learning",
    "observation", "artifact", "error",
}


class MeMantoClient:
    """
    Direct Memanto v2 REST client for the skills memory companion.

    Environment variables:
        MEMANTO_BASE_URL  – e.g. http://127.0.0.1:8000  (default)
        MOORCHEH_API_KEY  – required; bearer token from moorcheh.ai
        MEMANTO_AGENT_ID  – agent namespace (default: skills-companion)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        agent_id: str = "skills-companion",
    ):
        self.base_url = (
            base_url or os.getenv("MEMANTO_BASE_URL", "http://127.0.0.1:8000")
        ).rstrip("/")

        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "MOORCHEH_API_KEY is required.\n"
                "Set it: export MOORCHEH_API_KEY=mk-...\n"
                "Get a free key at https://moorcheh.ai"
            )

        self.agent_id = agent_id
        self._token: Optional[str] = None

        self._http = requests.Session()
        self._http.headers["Authorization"] = f"Bearer {self.api_key}"
        self._http.headers["Content-Type"] = "application/json"

        self._ensure_agent()
        self._activate()

    # ── Internal ──────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _aurl(self, path: str = "") -> str:
        return self._url(f"/api/v2/agents/{self.agent_id}{path}")

    def _headers(self) -> Dict:
        return {"X-Session-Token": self._token} if self._token else {}

    def _ensure_agent(self) -> None:
        """Create agent namespace if it does not exist (idempotent)."""
        try:
            r = self._http.post(
                self._url("/api/v2/agents"),
                json={
                    "agent_id": self.agent_id,
                    "description": "Skills memory companion — stores engineering decisions across skill executions",
                },
                timeout=10,
            )
            if r.status_code not in (200, 201, 409):
                logger.warning("agent create: status=%s", r.status_code)
        except requests.RequestException as exc:
            logger.error("_ensure_agent failed: %s", exc)

    def _activate(self) -> None:
        """Activate session and cache token. Raises on failure."""
        try:
            r = self._http.post(self._aurl("/activate"), json={}, timeout=10)
            r.raise_for_status()
            token = r.json().get("session_token")
            if not token:
                raise ValueError("session_token missing from activation response")
            self._token = token
            logger.info("Memanto session activated: agent_id=%s", self.agent_id)
        except Exception as exc:
            logger.error("_activate failed: %s", exc)
            raise

    def _request(self, method, url, **kwargs):
        """Execute request, retry once on 401 (expired session)."""
        response = method(url, **kwargs)
        if response.status_code == 401:
            logger.info("Session expired — reactivating")
            self._activate()
            kwargs["headers"] = self._headers()
            response = method(url, **kwargs)
        return response

    # ── Public API ────────────────────────────────────────────────────────

    def remember(
        self,
        content: str,
        memory_type: str = "observation",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """
        Store a memory via POST /remember.
        Returns dict with 'id'. Returns error dict (id=None) on failure —
        caller must check for id=None to detect write failures.
        """
        if memory_type not in VALID_MEMORY_TYPES:
            memory_type = "observation"

        payload = {
            "content": content,
            "type": memory_type,
            "tags": tags or [],
            "metadata": {**(metadata or {}), "stored_at": time.time()},
        }
        try:
            r = self._request(
                self._http.post,
                self._aurl("/remember"),
                json=payload,
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            mem = r.json()
            logger.info("stored id=%s type=%s", mem.get("id"), memory_type)
            return mem
        except Exception as exc:
            logger.error("remember failed: %s", exc)
            return {"id": None, "content": content, "error": str(exc)}

    def recall(
        self,
        query: str,
        limit: int = 5,
        memory_type: Optional[str] = None,
    ) -> List[Dict]:
        """
        Semantic search via GET /recall.
        Returns list of memory dicts ordered by relevance.
        """
        params: Dict = {"q": query, "limit": limit}
        if memory_type:
            params["type"] = memory_type
        try:
            r = self._request(
                self._http.get,
                self._aurl("/recall"),
                params=params,
                headers=self._headers(),
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get("memories", [])
        except Exception as exc:
            logger.error("recall failed: %s", exc)
            return []

    def answer(self, question: str) -> str:
        """RAG answer grounded in stored memories via POST /answer."""
        try:
            r = self._request(
                self._http.post,
                self._aurl("/answer"),
                json={"question": question},
                headers=self._headers(),
                timeout=20,
            )
            r.raise_for_status()
            return r.json().get("answer", "")
        except Exception as exc:
            logger.error("answer failed: %s", exc)
            return ""

    def correct(self, old_content: str, new_content: str) -> Dict:
        """
        Store a corrected fact as a NEW memory via POST /remember.
        Uses only the documented /remember endpoint — no undocumented PATCH.
        Old content is preserved in metadata.previous_content for audit.
        Caller must check id=None for failure.
        """
        return self.remember(
            content=new_content,
            memory_type="fact",
            tags=["correction", "updated"],
            metadata={
                "previous_content": old_content,
                "correction": True,
                "updated_at": time.time(),
            },
        )
