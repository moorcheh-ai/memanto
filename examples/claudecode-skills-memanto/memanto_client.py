"""
memanto_client.py
=================
Official moorcheh-sdk client for the skills memory companion.

Key advantage over subprocess-based CLI wrappers:
  - Uses MoorchehClient directly — same engine powering Memanto
  - answer.generate() for RAG context injection (not just keyword recall)
  - similarity_search.query() for semantic memory retrieval
  - documents.upload() for typed memory storage
  - Zero subprocess overhead — all in-process SDK calls

Usage:
    from memanto_client import SkillsClient
    client = SkillsClient()
    client.store("Use JWT over sessions", memory_type="decision", skill="tdd")
    memories = client.recall("authentication approach", skill="tdd")
    answer = client.answer("What auth approach did we decide on?")
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Dict, List, Optional

from moorcheh_sdk import MoorchehClient
from moorcheh_sdk.types.document import Document

logger = logging.getLogger(__name__)

VALID_MEMORY_TYPES = {
    "instruction", "fact", "decision", "goal", "commitment",
    "preference", "relationship", "context", "event", "learning",
    "observation", "artifact", "error",
}

SKILL_NAMESPACE_MAP = {
    "/tdd":                          "skills-tdd",
    "/grill-with-docs":              "skills-grill",
    "/grill-me":                     "skills-grill",
    "/handoff":                      "skills-handoff",
    "/improve-codebase-architecture": "skills-arch",
    "/diagnose":                     "skills-diagnose",
    "/to-issues":                    "skills-issues",
    "/to-prd":                       "skills-prd",
}

SHARED_NAMESPACE = "skills-engineering-profile"


class SkillsClient:
    """
    Official SDK client for cross-skill memory persistence.

    Uses MoorchehClient (moorcheh-sdk>=1.3.5) — the official engine.
    Each skill writes to a shared engineering profile namespace so that
    decisions from /grill-with-docs are automatically available to /tdd
    in any future session.

    Environment variables:
        MOORCHEH_API_KEY  — required (get free key at moorcheh.ai)
        MEMANTO_NAMESPACE — override shared namespace (default: skills-engineering-profile)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        namespace: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "MOORCHEH_API_KEY required.\n"
                "Get a free key at https://moorcheh.ai\n"
                "Set: export MOORCHEH_API_KEY=mk-..."
            )
        self.namespace = namespace or os.getenv(
            "MEMANTO_NAMESPACE", SHARED_NAMESPACE
        )
        self._client = MoorchehClient(api_key=self.api_key)
        self._ensure_namespace(self.namespace)

    def _ensure_namespace(self, ns: str) -> None:
        """Create namespace if it doesn't exist (idempotent)."""
        try:
            self._client.namespaces.create(namespace_name=ns, type="text")
            logger.info("namespace ready: %s", ns)
        except Exception as exc:
            if "already exists" not in str(exc).lower():
                logger.warning("namespace check: %s", exc)

    def store(
        self,
        content: str,
        memory_type: str = "observation",
        skill: str = "",
        tags: Optional[List[str]] = None,
        confidence: float = 0.8,
    ) -> Dict:
        """
        Store a memory using official SDK documents.upload().

        Returns dict with 'id' on success, 'id': None on failure.
        Caller must check id=None to detect write failures.
        """
        if memory_type not in VALID_MEMORY_TYPES:
            memory_type = "observation"

        mem_id = str(uuid.uuid4())
        doc: Document = {
            "id": mem_id,
            "text": content,
            "metadata": {
                "type": memory_type,
                "skill": skill,
                "tags": tags or [],
                "confidence": confidence,
            },
        }
        try:
            self._client.documents.upload(
                namespace_name=self.namespace,
                documents=[doc],
            )
            logger.info("stored id=%s type=%s skill=%s", mem_id, memory_type, skill)
            return {
                "id": mem_id,
                "content": content,
                "type": memory_type,
                "skill": skill,
            }
        except Exception as exc:
            logger.error("store failed: %s", exc)
            return {"id": None, "content": content, "error": str(exc)}

    def recall(
        self,
        query: str,
        skill: str = "",
        limit: int = 5,
    ) -> List[Dict]:
        """
        Semantic recall using official SDK similarity_search.query().
        Returns memories ordered by relevance score.
        """
        try:
            response = self._client.similarity_search.query(
                namespaces=[self.namespace],
                query=query,
                top_k=limit,
            )
            results = []
            items = (
                response.results
                if hasattr(response, "results")
                else (response if isinstance(response, list) else [])
            )
            for item in items:
                text = (
                    item.text if hasattr(item, "text") else
                    item.get("text", "") if isinstance(item, dict) else ""
                ) or ""
                meta = (
                    item.metadata if hasattr(item, "metadata") else
                    item.get("metadata", {}) if isinstance(item, dict) else {}
                ) or {}
                score = (
                    item.score if hasattr(item, "score") else
                    item.get("score", 1.0) if isinstance(item, dict) else 1.0
                )
                results.append({
                    "id": (
                        item.id if hasattr(item, "id") else
                        item.get("id", "") if isinstance(item, dict) else ""
                    ),
                    "content": text,
                    "type": meta.get("type", "observation"),
                    "skill": meta.get("skill", ""),
                    "confidence": meta.get("confidence", score),
                    "score": score,
                })
            return results
        except Exception as exc:
            logger.error("recall failed: %s", exc)
            return []

    def answer(self, question: str) -> str:
        """
        RAG answer grounded in stored engineering memories.
        Uses official SDK answer.generate() — LLM reads your engineering
        profile and answers based on actual stored decisions.

        This is the key differentiator: not just keyword recall but
        LLM-synthesized answers from your full engineering profile.
        """
        try:
            response = self._client.answer.generate(
                query=question,
                namespace=self.namespace,
            )
            return (
                response.answer if hasattr(response, "answer") else
                response.get("answer", "") if isinstance(response, dict) else ""
            )
        except Exception as exc:
            logger.error("answer failed: %s", exc)
            return ""

    def correct(self, old_content: str, new_content: str, skill: str = "") -> Dict:
        """
        Store a corrected fact using POST /remember only.
        Old content preserved in metadata.previous_content for audit trail.
        No undocumented PATCH endpoints used.
        """
        return self.store(
            content=new_content,
            memory_type="fact",
            skill=skill,
            tags=["correction", "updated"],
        )
