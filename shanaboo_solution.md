 ```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +1,15 @@
+"""Memanto - Memory that AI Agents Love!"""
+
+from memanto.core import Memanto
+from memanto.skills import SkillIntegration, SkillContext
+from memanto.config import MemantoConfig
+
+__version__ = "0.1.0"
+
+__all__ = [
+    "Memanto",
+    "SkillIntegration",
+    "SkillContext",
+    "MemantoConfig",
+]
+
--- /dev/null
+++ b/memanto/core.py
@@ -0,0 +1,287 @@
+"""Core Memanto memory agent implementation."""
+
+import json
+import hashlib
+import asyncio
+from datetime import datetime, timezone
+from typing import Optional, Dict, List, Any, Callable
+from dataclasses import dataclass, field, asdict
+from collections import deque
+
+from memanto.llm import LLMProvider, OpenAILLM, LLMConfig
+from memanto.storage import StorageBackend, FileStorage, MemoryRecord
+from memanto.config import MemantoConfig
+
+
+@dataclass
+class ContextSnapshot:
+    """A snapshot of context at a point in time."""
+    timestamp: str
+    skill_name: str
+    input_summary: str
+    output_summary: str
+    key_decisions: List[str]
+    architectural_patterns: List[str]
+    preferences: Dict[str, Any]
+    raw_context_hash: str
+    
+    def to_dict(self) -> Dict[str, Any]:
+        return asdict(self)
+    
+    @classmethod
+    def from_dict(cls, data: Dict[str, Any]) -> "ContextSnapshot":
+        return cls(**data)
+
+
+@dataclass 
+class EnrichedContext:
+    """Context enriched with relevant historical memory."""
+    current_input: str
+    current_skill: str
+    relevant_memories: List[Dict[str, Any]]
+    architectural_guidance: List[str]
+    style_preferences: List[str]
+    recent_decisions: List[Dict[str, Any]]
+    suggested_patterns: List[str]
+
+
+class Memanto:
+    """
+    Active memory companion that listens to skill executions,
+    distills knowledge, and injects relevant context.
+    """
+    
+    def __init__(
+        self,
+        config: Optional[MemantoConfig] = None,
+        llm_provider: Optional[LLMProvider] = None,
+        storage: Optional[StorageBackend] = None,
+    ):
+        self.config = config or MemantoConfig()
+        self.llm = llm_provider or self._default_llm()
+        self.storage = storage or self._default_storage()
+        self._recent_snapshots: deque = deque(maxlen=100)
+        self._session_id = self._generate_session_id()
+        
+    def _default_llm(self) -> LLMProvider:
+        return OpenAILLM(LLMConfig())
+    
+    def _default_storage(self) -> StorageBackend:
+        return FileStorage()
+    
+    def _generate_session_id(self) -> str:
+        return hashlib.sha256(
+            datetime.now(timezone.utc).isoformat().encode()
+        ).hexdigest()[:16]
+    
+    async def observe(
+        self,
+        skill_name: str,
+        skill_input: str,
+        skill_output: str,
+        metadata: Optional[Dict[str, Any]] = None,
+    ) -> ContextSnapshot:
+        """
+        Observe a skill execution and distill it into memory.
+        
+        This is the core 'listen' operation that captures what happened
+        and extracts the valuable context for future use.
+        """
+        # Generate raw context hash for deduplication
+        raw_context = f"{skill_name}:{skill_input}:{skill_output}"
+        context_hash = hashlib.sha256(raw_context.encode()).hexdigest()
+        
+        # Check if we've already processed this exact context
+        if self._is_duplicate(context_hash):
+            # Still record it as a reinforcement
+            await self._reinforce_memory(context_hash)
+            return self._get_existing_snapshot(context_hash)
+        
+        # Use LLM to distill the skill execution
+        distilled = await self._distill_skill_execution(
+            skill_name, skill_input, skill_output, metadata
+        )
+        
+        snapshot = ContextSnapshot(
+            timestamp=datetime.now(timezone.utc).isoformat(),
+            skill_name=skill_name,
+            input_summary=distilled["input_summary"],
+            output_summary=distilled["output_summary"],
+            key_decisions=distilled["key_decisions"],
+            architectural_patterns=distilled["architectural_patterns"],
+            preferences=distilled["preferences"],
+            raw_context_hash=context_hash,
+        )
+        
+        # Store in both hot and persistent storage
+        self._recent_snapshots.append(snapshot)
+        await self.storage.store(MemoryRecord(
+            id=context_hash,
+            timestamp=snapshot.timestamp,
+            skill_name=skill_name,
+            snapshot=snapshot.to_dict(),
+            embeddings=await self._generate_embeddings(raw_context),
+            metadata=metadata or {},
+        ))
+        
+        return snapshot
+    
+    async def recall(
+        self,
+        current_input: str,
+        current_skill: str,
+        max_memories: int = 5,
+    ) -> EnrichedContext:
+        """
+        Recall relevant memories for the current skill execution.
+        
+        This dynamically injects past engineering decisions into
+        the current context.
+        """
+        # Search for relevant memories
+        query_embedding = await self._generate_embeddings(current_input)
+        relevant = await self.storage.search_similar(
+            query_embedding, 
+            limit=max_memories * 2  # Get more, then filter
+        )
+        
+        # Filter to most relevant and recent
+        filtered = self._filter_relevant_memories(
+            relevant, current_skill, current_input
+        )
+        
+        # Extract guidance from memories
+        architectural_guidance = []
+        style_preferences = []
+        recent_decisions = []
+        suggested_patterns = []
+        
+        for memory in filtered[:max_memories]:
+            snapshot = memory.get("snapshot", {})
+            recent_decisions.extend([
+                {"decision": d, "from_skill": snapshot.get("skill_name")}
+                for d in snapshot.get("key_decisions", [])
+            ])
+            architectural_guidance.extend(
+                snapshot.get("architectural_patterns", [])
+            )
+            style_preferences.extend([
+                f"{k}: {v}" 
+                for k, v in snapshot.get("preferences", {}).items()
+            ])
+           