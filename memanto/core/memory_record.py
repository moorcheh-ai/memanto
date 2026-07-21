from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime

@dataclass
class MemoryRecord:
    id: str
    content: str
    metadata: Dict[str, Any]
    provenance: str = "explicit_statement"  # Default provenance
    created_at: datetime = datetime.now()
    updated_at: datetime = datetime.now()

    def update(self, **kwargs):
        """Update memory fields with new values"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()