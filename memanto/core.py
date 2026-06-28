"""Core Memanto memory management implementation."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

from memanto.config import Config
from memanto.exceptions import APIError, ConfigurationError, MemantoError


@dataclass
class MemoryFact:
    """Represents a single memory fact with metadata."""
    content: str
    source: str
    timestamp: float = field(default_factory=time.time)
    fact_type: str = "general"
    confidence: float = 1.0
    fact_hash: str = ""
    
    def __post_init__(self):
        if not self.fact_hash:
            self.fact_hash = hashlib.sha256(
                f"{self.content}:{self.source}:{self.timestamp}".encode()
            ).hexdigest()[:16]


class Memanto:
    """Main Memanto memory agent class."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self._memories: list[MemoryFact] = []
        self._session_start = time.time()
        self._validate_setup()
    
    def _validate_setup(self) -> None:
        """Validate that Memanto is properly configured."""
        if not self.config.api_key:
            raise ConfigurationError(
                "MOORCHEH_API_KEY is required. "
                "Get yours at https://memanto.ai/dashboard"
            )
    
    def store(
        self,
        content: str,
        source: str = "user",
        fact_type: str = "general",
        confidence: float = 1.0,
    ) -> MemoryFact:
        """Store a new memory fact."""
        fact = MemoryFact(
            content=content,
            source=source,
            fact_type=fact_type,
            confidence=confidence,
        )
        self._memories.append(fact)
        self._sync_to_remote(fact)
        return fact
    
    def retrieve(
        self,
        query: str,
        limit: int = 5,
        min_confidence: float = 0.0,
    ) -> list[MemoryFact]:
        """Retrieve relevant memories based on query."""
        # Filter by confidence first
        eligible = [m for m in self._memories if m.confidence >= min_confidence]
        
        # Simple relevance scoring based on keyword overlap
        # In production, this uses the moorcheh.ai retrieval engine
        query_words = set(query.lower().split())
        scored = []
        for memory in eligible:
            memory_words = set(memory.content.lower().split())
            score = len(query_words & memory_words) / max(len(query_words), 1)
            scored.append((score, memory))
        
        # Sort by relevance score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [m for _, m in scored[:limit]]
    
    def contradict(
        self,
        old_fact_hash: str,
        new_content: str,
        reason: str = "",
    ) -> MemoryFact:
        """Handle contradiction by updating an existing fact."""
        for i, memory in enumerate(self._memories):
            if memory.fact_hash == old_fact_hash:
                # Mark old fact as contradicted
                self._memories[i] = MemoryFact(
                    content=f"[CONTRADICTED: {reason}] {memory.content}",
                    source=memory.source,
                    timestamp=memory.timestamp,
                    fact_type=f"{memory.fact_type}_contradicted",
                    confidence=memory.confidence * 0.5,  # Reduce confidence
                )
                # Store new fact
                return self.store(new_content, source="contradiction_resolution")
        
        raise MemantoError(f"No fact found with hash: {old_fact_hash}")
    
    def get_timeline(self, fact_type: Optional[str] = None) -> list[MemoryFact]:
        """Get memories ordered by timestamp."""
        memories = self._memories
        if fact_type:
            memories = [m for m in memories if m.fact_type == fact_type]
        return sorted(memories, key=lambda m: m.timestamp)
    
    def _sync_to_remote(self, fact: MemoryFact) -> None:
        """Sync a memory fact to the remote moorcheh.ai backend."""
        try:
            response = requests.post(
                f"{self.config.base_url}/v1/memories",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                json={
                    "content": fact.content,
                    "source": fact.source,
                    "timestamp": fact.timestamp,
                    "fact_type": fact.fact_type,
                    "confidence": fact.confidence,
                    "fact_hash": fact.fact_hash,
                },
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise APIError(f"Failed to sync memory to remote: {exc}") from exc
    
    def __len__(self) -> int:
        return len(self._memories)
    
    def __repr__(self) -> str:
        return f"Memanto(memories={len(self._memories)}, session={self._session_start})"