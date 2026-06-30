 ```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -1,3 +1,4 @@
 """Memanto - Memory that AI Agents Love!"""
 
 __version__ programmer = "0.1.0"
+__all__ = ["Memanto", "MemoryConfig", "MemoryEntry"]
--- a/memanto/core.py
+++ b/memanto/core.py
@@ -0,0 +1,156 @@
+"""Core memory management with secure input validation and proper error handling."""
+
+import hashlib
+import json
+import os
+import re
+from dataclasses import dataclass, field
+from datetime import datetime
+from typing import Any, Dict, List, Optional, Union
+
+import requests
+
+
+class MemantoError(Exception):
+    """Base exception for Memanto errors."""
+    pass
+
+
+class ValidationError(MemantoError):
+    """Raised when input validation fails."""
+    pass
+
+
+class SecurityError(MemantoError):
+    """Raised when a security issue is detected."""
+    pass
+
+
+@dataclass
+class MemoryConfig:
+    """User-configurable settings for Memanto."""
+    api_key: str = ""
+    api_endpoint: str = "https://api.moorcheh.ai/v1"
+    max_content_length: int = 10000
+    enable_input_sanitization: bool = True
+    max_memories_per_request: int = 100
+    request_timeout: int = 30
+    
+    def __post_init__(self):
+        if not self.api_key:
+            self.api_key = os.environ.get("MOORCHEH_API_KEY", "")
+
+
+@dataclass
+class MemoryEntry:
+    """Represents a single memory entry with metadata."""
+    content: str
+    source: str = ""
+    timestamp: datetime = field(default_factory=datetime.utcnow)
+    metadata: Dict[str, Any] = field(default_factory=dict)
+    entry_id: str = ""
+    
+    def __post_init__(self):
+        if not self.entry_id:
+            self.entry_id = hashlib.sha256(
+                f"{self.content}:{self.timestamp.isoformat()}".encode()
+            ).hexdigest()[:16]
+
+
+class Memanto:
+    """Main Memanto memory agent with security and validation fixes."""
+    
+    # Security: Patterns that could indicate prompt injection attempts
+    _INJECTION_PATTERNS = [
+        r"ignore\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions|directives)",
+        r"forget\s+(?:everything|all\s+context)",
+        r"system\s*:\s*you\s+are\s+now",
+        r"<\|im_start\|>|<\|im_end\|>",
+        r"\{\{\s*SYSTEM\s*PROMPT\s*\}\}",
+        r"!\[\]\(.*?(?:exec|eval|system)\s*\(.*?\)",
+    ]
+    
+    def __init__(self, config: Optional[MemoryConfig] = None):
+        self.config = config or MemoryConfig()
+        self._session = requests.Session()
+        self._session.headers.update({
+            "Authorization": f"Bearer {self.config.api_key}",
+            "Content-Type": "application/json",
+            "User-Agent": "memanto/0.1.0"
+        })
+    
+    def _sanitize_input(self, content: str) -> str:
+        """Sanitize user input to prevent injection attacks."""
+        if not self.config.enable_input_sanitization:
+            return content
+        
+        # Check for obvious injection patterns
+        content_lower = content.lower()
+        for pattern in self._INJECTION_PATTERNS:
+            if re.search(pattern, content_lower, re.IGNORECASE):
+                raise SecurityError(
+                    f"Potential prompt injection detected. Input blocked for security."
+                )
+        
+        # Basic sanitization: strip null bytes, control characters
+        content = content.replace('\x00', '')
+        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)
+        
+        return content.strip()
+    
+    def _validate_content(self, content: Union[str, List[str]]) -> List[str]:
+        """Validate and normalize content for storage."""
+        if isinstance(content, str):
+            content = [content]
+        
+        if not isinstance(content, list):
+            raise ValidationError("Content must be a string or list of strings")
+        
+        validated = []
+        for item in content:
+            if not isinstance(item, str):
+                raise ValidationError(f"Each content item must be a string, got {type(item)}")
+            
+            if len(item) > self.config.max_content_length:
+                raise ValidationError(
+                    f"Content exceeds maximum length of {self.config.max_content_length} characters"
+                )
+            
+            if not item.strip():
+                continue
+            
+            # Security check
+            sanitized = self._sanitize_input(item)
+            validated.append(sanitized)
+        
+        if len(validated) > self.config.max_memories_per_request:
+            raise ValidationError(
+                f"Too many memories in single request: {len(validated)} > "
+                f"{self.config.max_memories_per_request}"
+            )
+        
+        return validated
+    
+    def store(self, content: Union[str, List[str]], **metadata) -> List[MemoryEntry]:
+        """Store memories with validation and security checks."""
+        validated_content = self._validate_content(content)
+        
+        entries = []
+        for item in validated_content:
+            entry = MemoryEntry(
+                content=item,
+                source=metadata.get("source", "user"),
+                metadata=metadata
+            )
+            entries.append(entry)
+        
+        # In a real implementation, this would send to the API
+        # For now, we return the entries
+        return entries
+    
+    def retrieve(self, query: str, limit: int = 10) -> List[MemoryEntry]:
+        """Retrieve relevant memories with validated query."""
+        if not isinstance(query, str):
+            raise ValidationError("Query must be a string")
+        
+        if not query.strip():
+            raise ValidationError("Query cannot be empty")
+        
+        # Sanitize the query
+        query = self._sanitize_input(query)
+        
+        if limit < 1 or limit > self.config.max_memories_per_request:
+            raise ValidationError(f"Limit must be between 1 and {self.config.max_memories_per_request}")
+        
+        # Placeholder for actual retrieval logic
+        return []
+    
+    def delete(self