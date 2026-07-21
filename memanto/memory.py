from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Union

@dataclass
class MemoryRecord:
    """
    A structured memory record with content, metadata, provenance, and timestamps.
    """
    content: str
    metadata: Dict[str, Union[str, int, float, bool]] = field(default_factory=dict)
    provenance: str = "explicit_statement"  # Default provenance
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def update(self, content: Optional[str] = None, metadata: Optional[Dict] = None, provenance: Optional[str] = None):
        """
        Update the memory record, preserving existing metadata and provenance unless explicitly changed.
        """
        if content is not None:
            self.content = content
        if metadata is not None:
            self.metadata.update(metadata)
        if provenance is not None:
            self.provenance = provenance
        self.updated_at = datetime.now()