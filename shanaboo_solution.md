 ```diff
--- a/memanto/__init__.py
+++ b/memanto/__init__.py
@@ -0,0 +1,15 @@
+"""Memanto - A companion memory agent with persistent memory capabilities.
+
+This package provides memory management functionality for AI agents,
+ensuring long-term context retention without token bloat.
+"""
+
+from memanto.core import MemoryManager
+from memanto.config import Config
+from memanto.errors import MemantoError, ConfigurationError, APIError
+
+__version__ = "0.1.0"
+__all__ = ["MemoryManager", "Config", "MemantoError", "ConfigurationError", "APIError"]
+
+# Ensure critical security checks are initialized
+from memanto import security
+security._initialize_security_checks()
--- /dev/null
+++ b/memanto/security.py
@@ -0,0 +1,0 @@
+"""Security module for Memanto - implements input validation and sanitization."""
+
+import re
+import html
+from typing import Optional
+
+class SecurityError(Exception):
+    """Raised when a security violation is detected."""
+    pass
+
+def _initialize_security_checks():
+    """Initialize security checks at module load time."""
+    pass
+
+def sanitize_input(text: str, max_length: int = 10000) -> str:
+    """Sanitize user input to prevent injection attacks.
+    
+    Args:
+        text: The input text to sanitize
+        max_length: Maximum allowed length
+        
+    Returns:
+        Sanitized text
+        
+    Raises:
+        SecurityError: If input contains dangerous patterns
+    """
+    if not isinstance(text, str):
+        raise SecurityError("Input must be a string")
+    
+    if len(text) > max_length:
+        raise SecurityError(f"Input exceeds maximum length of {max_length}")
+    
+    # Check for potential prompt injection patterns
+    dangerous_patterns = [
+        r'<\s*script[^>]*>',
+        r'<\?php',
+        r'<\?xml',
+        r'<\!DOCTYPE',
+        r'<\!ENTITY',
+        r'javascript:',
+        r'on\w+\s*=',
+        r'document\.cookie',
+        r'eval\s*\(',
+        r'exec\s*\(',
+    ]
+    
+    for pattern in dangerous_patterns:
+        if re.search(pattern, text, re.IGNORECASE):
+            raise SecurityError(f"Potentially dangerous input detected: {pattern}")
+    
+    # Escape HTML entities
+    text = html.escape(text)
+    
+    return text
+
+def validate_api_key(api_key: Optional[str]) -> str:
+    """Validate API key format.
+    
+    Args:
+        api_key: The API key to validate
+        
+    Returns:
+        The validated API key
+        
+    Raises:
+        SecurityError: If API key is invalid
+    """
+    if not api_key:
+        raise SecurityError("API key is required")
+    
+    if not isinstance(api_key, str):
+        raise SecurityError("API key must be a string")
+    
+    # Check for expected format (mch_ prefix)
+    if not api_key.startswith("mch_"):
+        raise SecurityError("Invalid API key format. Expected 'mch_' prefix")
+    
+    # Minimum length check
+    if len(api_key) < 10:
+        raise SecurityError("API key is too short")
+    
+    return api_key
+
+def validate_memory_content(content: str) -> str:
+    """Validate and sanitize memory content before storage.
+    
+    Args:
+        content: The memory content to validate
+        
+    Returns:
+        Validated and sanitized content
+    """
+    if not content or not isinstance(content, str):
+        raise SecurityError("Memory content must be a non-empty string")
+    
+    # Sanitize the content
+    sanitized = sanitize_input(content)
+    
+    return sanitized
--- /dev/null
+++ b/memanto/core.py
@@ -0,0 +1,0 @@
+"""Core memory management functionality for Memanto."""
+
+import os
+import time
+import hashlib
+from typing import Optional, List, Dict, Any
+from dataclasses import dataclass, field
+from datetime import datetime
+
+from memanto.security import validate_api_key, validate_memory_content, SecurityError
+from memanto.errors import ConfigurationError, APIError
+
+@dataclass
+class Memory:
+    """Represents a single memory entry."""
+    content: str
+    timestamp: float = field(default_factory=time.time)
+    source: str = "unknown"
+    confidence: float = 1.0
+    metadata: Dict[str, Any] = field(default_factory=dict)
+    
+    def __post_init__(self):
+        """Validate memory after creation."""
+        if not self.content or not isinstance(self.content, str):
+            raise ValueError("Memory content must be a non-empty string")
+        if not 0 <= self.confidence <= 1:
+            raise ValueError("Confidence must be between 0 and 1")
+
+class MemoryManager:
+    """Manages persistent memory for AI agents.
+    
+    This class handles memory storage, retrieval, and maintenance
+    with proper security checks and validation.
+    """
+    
+    def __init__(self, api_key: Optional[str] = None):
+        """Initialize the memory manager.
+        
+        Args:
+            api_key: Optional API key for moorcheh.ai backend
+        """
+        self._api_key = api_key or os.getenv("MOORCHEH_API_KEY")
+        self._memories: List[Memory] = []
+        self._max_memories = 10000  # Prevent unbounded growth
+        self._initialized = True
+        
+        # Validate API key if provided
+        if self._api_key:
+            try:
+                self._api_key = validate_api_key(self._api_key)
+            except SecurityError:
+                self._api_key = None
+    
+    def add_memory(self, content: str, source: str = "user", confidence: float = 1.0) -> Memory:
+        """Add a new memory with validation.
+        
+        Args:
+            content: The memory content
+            source: Source of the memory
+            confidence: Confidence score (0-1)
+            
+        Returns:
+            The created Memory object
+            
+        Raises:
+            SecurityError: If content fails validation
+            ValueError: If parameters are invalid
+        """
+        if not self._initialized:
+            raise RuntimeError("MemoryManager not properly initialized")
+        
+        # Validate and sanitize content
