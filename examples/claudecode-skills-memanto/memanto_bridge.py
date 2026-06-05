"""
memanto_bridge.py
=================
Skills memory companion using the official moorcheh-sdk.

Uses MoorchehClient (moorcheh-sdk) — the underlying engine of Memanto.
This is the correct pattern: use the official SDK, not raw HTTP wrappers.

SDK pattern:
  - Namespace = agent memory bucket (one per project/agent)
  - Document  = one memory (id, text, metadata)
  - similarity_search.query() = semantic recall
  - answer.generate() = RAG answer over namespace
"""
from __future__ import annotations

import logging
import os
import time
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


class SkillsMemoryBridge:
    """
    Official SDK-backed memory bridge for the skills companion.

    Uses moorcheh-sdk.MoorchehClient — the same engine powering Memanto.
    Each namespace corresponds to one agent/project memory bucket.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        namespace: str = "skills-companion",
    ):
        self.api_key = api_key or os.getenv("MOORCHEH_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "MOORCHEH_API_KEY required.\n"
                "Get a free key at https://moorcheh.ai\n"
                "Then: export MOORCHEH_API_KEY=mk-..."
            )
        self.namespace = namespace
        self._client = MoorchehClient(api_key=self.api_key)
        self._ensure_namespace()

    def _ensure_namespace(self) -> None:
        """Create namespace if it doesn't exist (idempotent)."""
        try:
            existing = self._client.namespaces.list()
            names = [n.get("name", n) if isinstance(n, dict) else str(n)
                     for n in (existing if isinstance(existing, list) else [])]
            if self.namespace not in names:
                self._client.namespaces.create(
                    namespace_name=self.namespace,
                    type="text",
                )
                logger.info("Created namespace: %s", self.namespace)
        except Exception as exc:
            logger.warning("namespace check failed (may already exist): %s", exc)

    def remember(
        self,
        content: str,
        memory_type: str = "observation",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """
        Store a memory using the official SDK's documents.upload().
        Returns dict with 'id' key.
        """
        if memory_type not in VALID_MEMORY_TYPES:
            memory_type = "observation"

        mem_id = str(uuid.uuid4())
        doc: Document = {
            "id": mem_id,
            "text": content,
            "metadata": {
                **(metadata or {}),
                "type": memory_type,
                "tags": tags or [],
                "stored_at": time.time(),
            },
        }
        try:
            self._client.documents.upload(
                namespace_name=self.namespace,
                documents=[doc],
            )
            logger.info("stored id=%s type=%s", mem_id, memory_type)
            return {"id": mem_id, "content": content, "type": memory_type}
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
        Semantic search using official SDK's similarity_search.query().
        Returns list of memory dicts.
        """
        try:
            response = self._client.similarity_search.query(
                namespaces=[self.namespace],
                query=query,
                top_k=limit,
            )
            results = []
            items = response if isinstance(response, list) else getattr(response, "results", [])
            for item in items:
                content = (item.get("text") or item.get("content", "")
                           if isinstance(item, dict) else
                           getattr(item, "text", "") or getattr(item, "content", ""))
                meta = (item.get("metadata", {})
                        if isinstance(item, dict) else
                        getattr(item, "metadata", {})) or {}
                # Filter by type if requested
                if memory_type and meta.get("type") != memory_type:
                    continue
                results.append({
                    "id": (item.get("id") if isinstance(item, dict)
                           else getattr(item, "id", "")),
                    "content": content,
                    "metadata": meta,
                    "score": (item.get("score", 1.0) if isinstance(item, dict)
                              else getattr(item, "score", 1.0)),
                })
            return results
        except Exception as exc:
            logger.error("recall failed: %s", exc)
            return []

    def answer(self, question: str) -> str:
        """RAG answer using official SDK's answer.generate()."""
        try:
            response = self._client.answer.generate(
                query=question,
                namespace=self.namespace,
            )
            return (response.get("answer", "") if isinstance(response, dict)
                    else getattr(response, "answer", ""))
        except Exception as exc:
            logger.error("answer failed: %s", exc)
            return ""

    def correct(self, old_content: str, new_content: str) -> Dict:
        """
        Store corrected fact as a new document.
        Old content preserved in metadata.previous_content for audit.
        Uses only documents.upload() — no undocumented endpoints.
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
