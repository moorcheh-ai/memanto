 ```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +1,6 @@
+"""Memanto - Memory that AI Agents Love!"""
+
+__version__ = "0.1.0"
+
+from memanto.core import Memanto
+from memanto.types import Memory, MemoryQuery
--- NEW FILE ---
--- /dev/null
+++ b/memanto/core.py
@@ -0,0 +1,95 @@
+"""Core Memanto memory management with secure input validation and timeline tracking."""
+
+import hashlib
+import json
+import re
+from datetime import datetime, timezone
+from typing import Any
+
+from memanto.types import Memory, MemoryQuery
+
+
+class Memanto:
+    """Secure memory manager with timeline tracking and contradiction resolution."""
+
+    def __init__(self, backend_client=None):
+        self._memories: dict[str, Memory] = {}
+        self._backend = backend_client
+        self._max_content_length = 10000
+        self._allowed_content_pattern = re.compile(r'^[\w\s.,!?;:\-–—()[\]{}\"\'\n\r\t]+$')
+
+    def _sanitize_input(self, content: str) -> str:
+        """Sanitize and validate memory content to prevent injection attacks."""
+        if not isinstance(content, str):
+            raise TypeError("Memory content must be a string")
+        
+        # Length check to prevent DoS
+        if len(content) > self._max_content_length:
+            raise ValueError(f"Content exceeds maximum length of {self._max_content_length}")
+        
+        # Strip null bytes and control characters
+        content = content.replace('\x00', '').replace('\x01', '').replace('\x02', '')
+        
+        # Basic pattern validation - allow common text characters
+        # This prevents prompt injection via special characters
+        if not self._allowed_content_pattern.match(content):
+            # If it fails, still allow but escape dangerous patterns
+            content = self._escape_dangerous_patterns(content)
+        
+        return content.strip()
+
+    def _escape_dangerous_patterns(self, content: str) -> str:
+        """Escape patterns that could be used for prompt injection."""
+        # Remove or escape common injection patterns
+        dangerous = [
+            r'<\s*/\s*[a-zA-Z]+>',  # XML/HTML tags
+            r'\{\s*[\w_]+\s*:\s*',   # JSON-like injection
+            r'(?i)(system|user|assistant)\s*:',  # Role injection
+        ]
+        for pattern in dangerous:
+            content = re.sub(pattern, '[REDACTED]', content)
+        return content
+
+    def _generate_id(self, content: str) -> str:
+        """Generate deterministic ID for content deduplication."""
+        return hashlib.sha256(content.encode()).hexdigest()[:16]
+
+    def store(self, content: str, metadata: dict[str, Any] | None = None) -> Memory:
+        """Store a memory with timeline tracking and input validation."""
+        safe_content = self._sanitize_input(content)
+        
+        memory_id = self._generate_id(safe_content)
+        
+        # Check for contradictions with existing memories
+        contradictions = self._find_contradictions(safe_content)
+        
+        memory = Memory(
+            id=memory_id,
+            content=safe_content,
+            created_at=datetime.now(timezone.utc),
+            metadata=metadata or {},
+            contradictions=contradictions,
+        )
+        
+        self._memories[memory_id] = memory
+        return memory
+
+    def _find_contradictions(self, content: str) -> list[str]:
+        """Find potential contradictions with existing memories."""
+        contradictions = []
+        content_lower = content.lower()
+        
+        for memory in self._memories.values():
+            # Simple contradiction detection: negation of existing content
+            existing = memory.content.lower()
+            if self._is_negation(content_lower, existing):
+                contradictions.append(memory.id)
+        
+        return contradictions
+
+    def _is_negation(self, text1: str, text2: str) -> bool:
+        """Check if one text negates the other."""
+        negation_words = ['not', 'never', 'no longer', 'false', 'incorrect']
+        # Simple heuristic: if texts are similar but one contains negation
+        return any(word in text1 for word in negation_words) or any(word in text2 for word in negation_words)
+
+    def query(self, query: MemoryQuery) -> list[Memory]:
+        """Query memories with relevance scoring and timeline awareness."""
+        results = []
+        
+        for memory in self._memories.values():
+            score = self._calculate_relevance(memory, query)
+            if score > 0.5:  # Threshold for relevance
+                results.append((memory, score))
+        
+        # Sort by relevance score, then by recency
+        results.sort(key=lambda x: (-x[1], x[0].created_at), reverse=False)
+        return [m for m, _ in results]
+
+    def _calculate_relevance(self, memory: Memory, query: MemoryQuery) -> float:
+        """Calculate relevance score with timeline awareness."""
+        # Simple keyword matching with timeline boost
+        score = 0.0
+        query_terms = query.query.lower().split()
+        memory_content = memory.content.lower()
+        
+        for term in query_terms:
+            if term in memory_content:
+                score += 0.3
+        
+        # Timeline awareness: boost recent memories
+        if memory.created_at:
+            age = (datetime.now(timezone.utc) - memory.created_at).days
+            if age < 7:
+                score += 0.2  # Recent memory boost
+        
+        return min(score, 1.0)
+
+    def get_timeline(self, memory_id: str) -> list[dict[str, Any]]:
+        """Get timeline of updates for a memory including contradictions."""
+        memory = self._memories.get(memory_id)
+        if not memory:
+            return []
+        
+        timeline = [{
+            'event': 'created',
+            'timestamp': memory.created_at.isoformat() if memory.created_at else None,
+            'content': memory.content,
+        }]
+        
+        # Add contradiction events
+        for contradiction_id in memory.contradictions:
+            if contradiction_id in self._memories:
+                contradicted = self._memories[contradiction_id]
+                timeline.append({
+                    'event': 'contradicted_by',
+                    'timestamp': contrad