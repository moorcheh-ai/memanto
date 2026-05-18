"""
memanto_client.py
=================
Thin wrapper around Memanto's v2 REST API.
Used as the sole memory backend — LangGraph state is NOT used for memory.

Pattern: Memanto as TOOLS only. LangGraph manages flow; Memanto manages memory.
"""
from __future__ import annotations
import logging, os, time, uuid
from typing import Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

VALID_TYPES = {
    "instruction","fact","decision","goal","commitment",
    "preference","relationship","context","event","learning",
    "observation","artifact","error",
}

class MeMantoClient:
    """
    Direct Memanto v2 REST client.
    All LangGraph nodes call this — no CrewAI / LangChain memory layers involved.
    """
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        agent_id: str = "langgraph-agent",
    ):
                self.base_url = (base_url or os.getenv("MEMANTO_BASE_URL","http://127.0.0.1:8000")).rstrip("/")
        self.api_key  = api_key or os.getenv("MOORCHEH_API_KEY","")
        if not self.api_key:
            raise ValueError(
                "MOORCHEH_API_KEY is required. "
                "Set the MOORCHEH_API_KEY environment variable or pass api_key= explicitly.\n"
                "Get your key at https://moorcheh.ai"
            )
        self.agent_id = agent_id
        self._token: Optional[str] = None

        self._http = requests.Session()
        self._http.headers["Authorization"] = f"Bearer {self.api_key}"
        self._http.headers["Content-Type"] = "application/json"

        self._ensure_agent()
        self._activate()

    # ── internal ──────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _aurl(self, path: str = "") -> str:
        return self._url(f"/api/v2/agents/{self.agent_id}{path}")

    def _h(self) -> Dict:
        return {"X-Session-Token": self._token} if self._token else {}

    def _ensure_agent(self):
        try:
            r = self._http.post(self._url("/api/v2/agents"),
                json={"agent_id": self.agent_id, "description": "LangGraph integration"},
                timeout=10)
            if r.status_code not in (200,201,409):
                logger.warning("agent create: %s", r.status_code)
        except Exception as e:
            logger.error("ensure_agent: %s", e)

    def _activate(self):
        try:
            r = self._http.post(self._aurl("/activate"), json={}, timeout=10)
            if r.ok:
                self._token = r.json().get("session_token")
                logger.info("Memanto session activated: %s", self.agent_id)
        except Exception as e:
            logger.error("activate: %s", e)

    # ── public API ────────────────────────────────────────────────────────

    def remember(
        self,
        content: str,
        memory_type: str = "observation",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """Store a memory. Returns dict with 'id'."""
        if memory_type not in VALID_TYPES:
            memory_type = "observation"
        payload = {
            "content": content,
            "type": memory_type,
            "tags": tags or [],
            "metadata": {**(metadata or {}), "stored_at": time.time()},
        }
        try:
            r = self._http.post(self._aurl("/remember"),
                json=payload, headers=self._h(), timeout=15)
            r.raise_for_status()
            mem = r.json()
            logger.info("stored id=%s type=%s", mem.get("id"), memory_type)
            return mem
        except Exception as e:
            logger.error("remember: %s", e)
            return {"id": None, "content": content, "error": str(e)}

    def recall(self, query: str, limit: int = 5, memory_type: Optional[str] = None) -> List[Dict]:
        """Semantic search. Returns list of memory dicts."""
        params = {"q": query, "limit": limit}
        if memory_type:
            params["type"] = memory_type
        try:
            r = self._http.get(self._aurl("/recall"),
                params=params, headers=self._h(), timeout=15)
            r.raise_for_status()
            return r.json().get("memories", [])
        except Exception as e:
            logger.error("recall: %s", e)
            return []

    def answer(self, question: str) -> str:
        """RAG answer grounded in stored memories."""
        try:
            r = self._http.post(self._aurl("/answer"),
                json={"question": question}, headers=self._h(), timeout=20)
            r.raise_for_status()
            return r.json().get("answer","")
        except Exception as e:
            logger.error("answer: %s", e)
            return ""

    def correct(self, old_content: str, new_content: str) -> Dict:
        """
        Handle contradictory memories by storing the corrected fact as a new memory.
        Uses only the documented POST /remember endpoint — no undocumented PATCH.
        The previous_content is preserved in metadata for audit.
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
            r = self._http.post(
                self._aurl("/remember"),
                json=payload, headers=self._h(), timeout=15)
            r.raise_for_status()
            mem = r.json()
            logger.info("correction stored id=%s", mem.get("id"))
            return mem
        except Exception as e:
            logger.error("correct: %s", e)
            return {"id": None, "content": new_content, "error": str(e)}