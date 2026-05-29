```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +0,0 @@
--- a/memanto/core.py
+++ b/memanto/core.py
@@ -0,0 +1,0 @@
--- a/memanto/skills.py
+++ b/memanto/skills.py
@@ -0,0 +1,0 @@
--- a/integrations/__init__.py
+++ b/integrations/__init__.py
@@ -0,0 +1,0 @@
--- a/integrations/mattpocock_skills.py
+++ b/integrations/mattpocock_skills.py
@@ -0,0 +1,0 @@
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +1,5 @@
+"""Memanto - Memory that AI Agents Love!"""
+
+from memanto.core import Memanto
+
+__all__ = ["Memanto"]
--- a/memanto/core.py
+++ b/memanto/core.py
@@ -0,0 +1,0 @@
+"""Core Memanto memory agent implementation."""
+
+import json
+import hashlib
+import os
+from datetime import datetime, timezone
+from typing import Any, Optional, Dict, List
+from dataclasses import dataclass, asdict
+from pathlib import Path
+
+
+@dataclass
+class MemoryEntry:
+    """A single memory entry with metadata."""
+    content: str
+    source: str  # e.g., 'grill-with-docs', 'tdd', 'handoff'
+    timestamp: str
+    tags: List[str]
+    importance: float  # 0.0 to 1.0
+    session_id: Optional[str] = None
+    
+    def to_dict(self) -> Dict[str, Any]:
+        return asdict(self)
+    
+    @classmethod
+    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
+        return cls(**data)
+
+
+class Memanto:
+    """
+    Active memory companion that persists context across skill executions.
+    
+    Memanto listens to inputs/outputs of developer skills, distills
+    architectural decisions and preferences, and injects relevant
+    context into subsequent skill executions.
+    """
+    
+    def __init__(
+        self,
+        memory_dir: Optional[str] = None,
+        max_entries: int = 1000,
+        relevance_threshold: float = 0.6,
+    ):
+        self.max_entries = max_entries
+        self.relevance_threshold = relevance_threshold
+        
+        # Default to ~/.memanto for memory storage
+        if memory_dir is None:
+            memory_dir = os.path.expanduser("~/.memanto")
+        self.memory_dir = Path(memory_dir)
+        self.memory_dir.mkdir(parents=True, exist_ok=True)
+        
+        self.memory_file = self.memory_dir / "memories.json"
+        self.preferences_file = self.memory_dir / "preferences.json"
+        self.architecture_file = self.memory_dir / "architecture.json"
+        
+        self._memories: List[MemoryEntry] = []
+        self._preferences: Dict[str, Any] = {}
+        self._architecture: Dict[str, Any] = {}
+        
+        self._load_all()
+    
+    def _load_all(self) -> None:
+        """Load all persisted data."""
+        if self.memory_file.exists():
+            self._load_memories()
+        if self.preferences_file.exists():
+            self._load_preferences()
+        if self.architecture_file.exists():
+            self._load_architecture()
+    
+    def _load_memories(self) -> None:
+        """Load memories from disk."""
+        try:
+            data = json.loads(self.memory_file.read_text())
+            self._memories = [MemoryEntry.from_dict(m) for m in data.get("memories", [])]
+        except (json.JSONDecodeError, KeyError):
+            self._memories = []
+    
+    def _load_preferences(self) -> None:
+        """Load developer preferences from disk."""
+        try:
+            self._preferences = json.loads(self.preferences_file.read_text())
+        except (json.JSONDecodeError, KeyError):
+            self._preferences = {}
+    
+    def _load_architecture(self) -> None:
+        """Load architecture decisions from disk."""
+        try:
+            self._architecture = json.loads(self.architecture_file.read_text())
+        except (json.JSONDecodeError, KeyError):
+            self._architecture = {}
+    
+    def _save_memories(self) -> None:
+        """Persist memories to disk."""
+        data = {
+            "version": "1.0",
+            "last_updated": datetime.now(timezone.utc).isoformat(),
+            "memories": [m.to_dict() for m in self._memories],
+        }
+        self.memory_file.write_text(json.dumps(data, indent=2))
+    
+    def _save_preferences(self) -> None:
+        """Persist preferences to disk."""
+        self.preferences_file.write_text(json.dumps(self._preferences, indent=2))
+    
+    def _save_architecture(self) -> None:
+        """Persist architecture decisions to disk."""
+        self.architecture_file.write_text(json.dumps(self._architecture, indent=2))
+    
+    def remember(
+        self,
+        content: str,
+        source: str,
+        tags: Optional[List[str]] = None,
+        importance: float = 0.5,
+        session_id: Optional[str] = None,
+    ) -> MemoryEntry:
+        """
+        Store a new memory from a skill execution.
+        
+        Args:
+            content: The distilled information to remember
+            source: Which skill produced this (e.g., 'grill-with-docs')
+            tags: Optional categorization tags
+            importance: How important this memory is (0.0 to 1.0)
+            session_id: Optional session identifier
+        
+        Returns:
+            The created MemoryEntry
+        """
+        entry = MemoryEntry(
+            content=content,
+            source=source,
+            timestamp=datetime.now(timezone.utc).isoformat(),
+            tags=tags or [],
+            importance=max(0.0, min(1.0, importance)),
+            session_id=session_id,
+        )
+        
+        self._memories.append(entry)
+        
+        # Trim if exceeding max
+        if len(self._memories) > self.max_entries:
+            # Remove lowest importance oldest entries
+            self._memories.sort(key=lambda m: (m.importance, m.timestamp))
+            self._memories = self._memories[-self.max_entries:]
+        
+        self._save_memories()
+       